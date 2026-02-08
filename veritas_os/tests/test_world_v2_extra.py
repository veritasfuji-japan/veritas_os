# tests/test_world_v2_extra.py
import json
from veritas_os.core import world as world_core

WorldState = world_core.WorldState


# ───────────────────────────────
# 1. _load_world のレガシーマイグレーション
# ───────────────────────────────

def test_load_world_migrates_legacy_user_dict(tmp_path, monkeypatch):
    """v1 形式 {user_id: {...}} から v2 schema への移行をカバー"""
    legacy_path = tmp_path / "world_state_legacy.json"
    legacy_data = {
        "alice": {
            "decisions": 3,
            "avg_latency_ms": 123.0,
            "avg_risk": 0.4,
            "avg_value": 0.8,
            "active_plan_steps": 2,
            "active_plan_done": 1,
            "last_query": "hello",
            "last_chosen_title": "title",
            "last_decision_status": "ok",
            "last_updated": "2025-01-01T00:00:00Z",
        }
    }
    legacy_path.write_text(json.dumps(legacy_data), encoding="utf-8")
    monkeypatch.setattr(world_core, "WORLD_PATH", legacy_path)

    world = world_core._load_world()

    assert world["schema_version"] == "2.0.0"
    assert isinstance(world["projects"], list)
    proj = world["projects"][0]
    assert proj["owner_user_id"] == "alice"
    assert proj["metrics"]["decisions"] == 3
    assert proj["last"]["query"] == "hello"


# ───────────────────────────────
# 2. _get_or_create_default_project のレア分岐
# ───────────────────────────────

def test_get_or_create_default_project_normalizes_dict_projects():
    """projects が dict のときに list に正規化されるパス"""
    world = {
        "projects": {
            "u:default": {
                "project_id": "u:default",
                "owner_user_id": "u",
                "title": "Existing",
            },
            "broken": "ignore_me",
        }
    }
    proj = world_core._get_or_create_default_project(world, "u")

    assert proj["project_id"] == "u:default"
    assert isinstance(world["projects"], list)
    assert proj in world["projects"]


def test_get_or_create_default_project_handles_non_list_projects():
    """projects が文字列など壊れている場合の新規作成パス"""
    world = {"projects": "broken"}
    proj = world_core._get_or_create_default_project(world, "bob")

    assert proj["project_id"] == "bob:default"
    assert isinstance(world["projects"], list)
    assert proj in world["projects"]


# ───────────────────────────────
# 3. _ensure_project の dict / 変な値パス
# ───────────────────────────────

def test_ensure_project_with_dict_projects():
    """projects が dict のときの後方互換パス"""
    state = {"projects": {}}
    proj = world_core._ensure_project(state, "p1", "P1")

    assert "p1" in state["projects"]
    assert state["projects"]["p1"]["status"] == "active"

    # 2 回目は既存を返す
    proj2 = world_core._ensure_project(state, "p1", "SHOULD_BE_IGNORED")
    assert proj2 is state["projects"]["p1"]


def test_ensure_project_with_non_collection_projects():
    """projects が変な値のとき list に作り直すパス"""
    state = {"projects": "broken"}
    proj = world_core._ensure_project(state, "p2", "P2")

    assert proj["project_id"] == "p2"
    assert isinstance(state["projects"], list)
    assert proj in state["projects"]


# ───────────────────────────────
# 4. snapshot のフォールバックパス
# ───────────────────────────────

def test_snapshot_prefers_named_project_direct_key(monkeypatch):
    """state[project] が dict の場合、そのまま返すパス"""
    def fake_get_state(user_id=world_core.DEFAULT_USER_ID):
        return {"myproj": {"progress": 0.3, "decision_count": 7}}

    monkeypatch.setattr(world_core, "get_state", fake_get_state)
    snap = world_core.snapshot("myproj")

    assert snap == {"progress": 0.3, "decision_count": 7}


def test_snapshot_uses_veritas_root(monkeypatch):
    """veritas ルートを拾うフォールバック"""
    def fake_get_state(user_id=world_core.DEFAULT_USER_ID):
        return {"veritas": {"progress": 0.4, "decision_count": 9}}

    monkeypatch.setattr(world_core, "get_state", fake_get_state)
    snap = world_core.snapshot("anything")

    assert snap["progress"] == 0.4
    assert snap["decision_count"] == 9


def test_snapshot_uses_root_progress(monkeypatch):
    """state 自体に progress / decision_count があるフォールバック"""
    def fake_get_state(user_id=world_core.DEFAULT_USER_ID):
        return {"progress": 0.8, "decision_count": 12}

    monkeypatch.setattr(world_core, "get_state", fake_get_state)
    snap = world_core.snapshot("missing")

    assert snap["progress"] == 0.8
    assert snap["decision_count"] == 12


def test_snapshot_returns_empty_when_nothing(monkeypatch):
    """どのキーも無い場合は空 dict"""
    def fake_get_state(user_id=world_core.DEFAULT_USER_ID):
        return {"something": "else"}

    monkeypatch.setattr(world_core, "get_state", fake_get_state)
    snap = world_core.snapshot("missing")

    assert snap == {}


# ───────────────────────────────
# 5. inject_state_into_context の projects(list/dict) 分岐
# ───────────────────────────────

def test_inject_state_into_context_with_list_projects(monkeypatch):
    """projects が list で veritas_agi が存在するパス"""
    fake_world = {
        "meta": {"last_users": {}},
        "projects": [
            {
                "project_id": "u:default",
                "owner_user_id": "u",
                "title": "Default Project for u",
                "status": "active",
                "metrics": {
                    "decisions": 10,
                    "avg_latency_ms": 100.0,
                    "avg_risk": 0.1,
                    "avg_value": 0.9,
                    "active_plan_steps": 4,
                    "active_plan_done": 2,
                },
                "last": {
                    "query": "q",
                    "chosen_title": "c",
                    "decision_status": "ok",
                },
                "active_plan_title": "Plan",
            },
            {
                "project_id": "veritas_agi",
                "owner_user_id": "u",
                "title": "AGI Project",
                "status": "active",
                "progress": 0.5,
                "last_decision_at": "2025-01-01T00:00:00Z",
                "notes": "",
                "decision_count": 3,
                "last_risk": 0.2,
            },
        ],
        "external_knowledge": {
            "agi_research_events": [
                {
                    "kind": "agi_research",
                    "ts": "2025-01-02T00:00:00Z",
                    "query": "test",
                    "papers": [{"title": "Paper1", "url": "https://example.com"}],
                    "summary": "summary",
                }
            ]
        },
    }

    monkeypatch.setattr(world_core, "_load_world", lambda: fake_world)
    monkeypatch.setattr(world_core, "_save_world", lambda state: None)

    ctx = world_core.inject_state_into_context({"foo": "bar"}, user_id="u")

    assert ctx["foo"] == "bar"
    ws = ctx["world_state"]
    assert ws["decisions"] == 10
    assert ctx["world"]["projects"]["veritas_agi"]["status"] == "active"
    assert ctx["world"]["external_knowledge"]["last_titles"][0] == "Paper1"


def test_inject_state_into_context_with_dict_projects(monkeypatch):
    """projects が dict のときの veritas_agi パス"""
    fake_world = {
        "meta": {"last_users": {}},
        "projects": {
            "veritas_agi": {
                "title": "AGI Dict",
                "status": "paused",
                "progress": 0.1,
                "last_decision_at": None,
                "notes": "note",
                "decision_count": 1,
                "last_risk": 0.3,
            }
        },
        "external_knowledge": {},
    }

    monkeypatch.setattr(world_core, "_load_world", lambda: fake_world)
    monkeypatch.setattr(world_core, "_save_world", lambda state: None)
    monkeypatch.setattr(world_core, "load_state", lambda user_id="global": WorldState())

    ctx = world_core.inject_state_into_context({}, user_id="global")

    ver = ctx["world"]["projects"]["veritas_agi"]
    assert ver["name"].startswith("AGI Dict")
    assert ver["status"] == "paused"


# ───────────────────────────────
# 6. simulate / simulate_decision のフォールバックパス
# ───────────────────────────────

def test_simulate_uses_load_state_when_no_context(monkeypatch):
    """context に world_state が無い場合に load_state を使う分岐"""
    dummy_state = WorldState(
        user_id="u",
        decisions=20,
        avg_latency_ms=0.0,
        avg_risk=0.2,
        avg_value=0.8,
        active_plan_steps=5,
        active_plan_done=3,
    )
    monkeypatch.setattr(world_core, "load_state", lambda user_id: dummy_state)

    res = world_core.simulate(option={"score": 2.0}, context={}, user_id="u")

    assert 0.0 <= res["utility"] <= 1.0
    assert 0.0 < res["confidence"] <= 1.0
    assert res["avg_value"] == 0.8
    assert res["avg_risk"] == 0.2


def test_simulate_decision_injects_world_state(monkeypatch):
    """simulate_decision が world_state を context に埋めるパス"""
    captured = {}

    def fake_simulate(option=None, context=None, user_id=None, **_):
        captured["ctx"] = context
        return {
            "utility": 0.5,
            "confidence": 0.1,
            "avg_value": 0.5,
            "avg_risk": 0.0,
            "plan_progress": 0.0,
        }

    monkeypatch.setattr(world_core, "simulate", fake_simulate)

    res = world_core.simulate_decision(
        option={"score": 1.0},
        context={},
        world_state={"decisions": 1},
        user_id="u",
    )

    assert res["utility"] == 0.5
    assert captured["ctx"]["world_state"]["decisions"] == 1


# ───────────────────────────────
# 7. next_hint_for_veritas_agi の各ステージ分岐
# ───────────────────────────────

def _make_world_for_hint(events):
    return {
        "meta": {"last_users": {}},
        "veritas": {"decision_count": 100},
        "external_knowledge": {
            "agi_research_events": events,
        },
    }


def test_next_hint_stage_collect_decisions(monkeypatch):
    """decision_count < 5 の collect_decisions 分岐"""
    world = _make_world_for_hint([])
    monkeypatch.setattr(world_core, "_load_world", lambda: world)
    monkeypatch.setattr(world_core, "load_state", lambda user_id: WorldState(decisions=0))

    hint = world_core.next_hint_for_veritas_agi()

    assert hint["focus"] == "collect_decisions"


def test_next_hint_stage_stabilize_and_research_and_benchmarks_and_review(monkeypatch):
    """残り 4 ステージを順に踏ませる"""

    # 1) stabilize_pipeline: decisions>=5, progress<0.3
    world = _make_world_for_hint([])
    ws = WorldState(
        decisions=10,
        active_plan_steps=10,
        active_plan_done=2,  # progress = 0.2
    )
    monkeypatch.setattr(world_core, "_load_world", lambda: world)
    monkeypatch.setattr(world_core, "load_state", lambda user_id: ws)
    hint = world_core.next_hint_for_veritas_agi()
    assert hint["focus"] == "stabilize_pipeline"

    # 2) seed_agi_research: progress>=0.3, agi_events == 0
    world = _make_world_for_hint([])
    ws = WorldState(
        decisions=10,
        active_plan_steps=10,
        active_plan_done=5,  # progress = 0.5
    )
    monkeypatch.setattr(world_core, "_load_world", lambda: world)
    monkeypatch.setattr(world_core, "load_state", lambda user_id: ws)
    hint = world_core.next_hint_for_veritas_agi()
    assert hint["focus"] == "seed_agi_research"

    # 3) design_benchmarks: progress<0.7, agi_events>=1
    world = _make_world_for_hint(
        [{"kind": "agi_research", "ts": "t", "query": "", "papers": [], "summary": ""}]
    )
    ws = WorldState(
        decisions=10,
        active_plan_steps=10,
        active_plan_done=5,  # progress = 0.5 (<0.7)
    )
    monkeypatch.setattr(world_core, "_load_world", lambda: world)
    monkeypatch.setattr(world_core, "load_state", lambda user_id: ws)
    hint = world_core.next_hint_for_veritas_agi()
    assert hint["focus"] == "design_benchmarks"

    # 4) external_review: progress>=0.7, agi_events>=1
    world = _make_world_for_hint(
        [{"kind": "agi_research", "ts": "t", "query": "", "papers": [], "summary": ""}]
    )
    ws = WorldState(
        decisions=10,
        active_plan_steps=10,
        active_plan_done=8,  # progress = 0.8
    )
    monkeypatch.setattr(world_core, "_load_world", lambda: world)
    monkeypatch.setattr(world_core, "load_state", lambda user_id: ws)
    hint = world_core.next_hint_for_veritas_agi()
    assert hint["focus"] == "external_review"

