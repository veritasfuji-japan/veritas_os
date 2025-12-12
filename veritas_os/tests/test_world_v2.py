# tests/test_world_v2.py
import json
import importlib

import pytest


def setup_tmp_world(tmp_path, monkeypatch):
    """
    VERITAS_DATA_DIR を一時ディレクトリに向けて、
    veritas_os.core.world をリロードしたモジュールを返すヘルパー。
    """
    monkeypatch.setenv("VERITAS_DATA_DIR", str(tmp_path))

    import veritas_os.core.world as world_module  # noqa: WPS433 (local import OK for reload)
    importlib.reload(world_module)
    return world_module


def test_load_world_creates_default(tmp_path, monkeypatch):
    world = setup_tmp_world(tmp_path, monkeypatch)
    world_path = world.WORLD_PATH

    # ファイルはまだ存在しない前提
    assert not world_path.exists()

    st = world.load_state("userA")

    # デフォルトプロジェクトが作られているはず
    assert st.user_id == "userA"
    assert st.decisions == 0
    assert st.avg_value == 0.5

    # load_state() はまだディスクには書かない実装なので、
    # ファイルの存在は期待せず、get_state() のスキーマだけ検証する
    data = world.get_state()
    assert isinstance(data, dict)
    assert "projects" in data
    assert data["schema_version"] == "2.0.0"


def test_save_state_roundtrip(tmp_path, monkeypatch):
    world = setup_tmp_world(tmp_path, monkeypatch)

    st = world.load_state("userB")
    st.decisions = 10
    st.avg_risk = 0.3
    st.avg_value = 0.8
    st.last_query = "hello"
    st.last_chosen_title = "chosen"
    st.last_decision_status = "ok"

    world.save_state(st)

    st2 = world.load_state("userB")
    assert st2.decisions == 10
    assert st2.avg_risk == 0.3
    assert st2.avg_value == 0.8
    assert st2.last_query == "hello"
    assert st2.last_chosen_title == "chosen"
    assert st2.last_decision_status == "ok"


def test_load_world_migrates_legacy_format(tmp_path, monkeypatch):
    world = setup_tmp_world(tmp_path, monkeypatch)
    world_path = world.WORLD_PATH

    # v1形式: user_id -> state dict
    legacy = {
        "userX": {
            "decisions": 3,
            "avg_latency_ms": 100.0,
            "avg_risk": 0.2,
            "avg_value": 0.7,
            "last_query": "legacy",
            "last_chosen_title": "old",
            "last_decision_status": "ok",
            "last_updated": "2024-01-01T00:00:00Z",
        }
    }
    world_path.write_text(json.dumps(legacy), encoding="utf-8")

    st = world.load_state("userX")

    # マイグレーション後でも値がそれなりに反映されているか
    assert st.decisions == 3
    assert st.avg_risk == 0.2
    assert st.avg_value == 0.7
    assert st.last_query == "legacy"
    assert st.last_chosen_title == "old"
    assert st.last_decision_status == "ok"


def test_update_from_decision_updates_metrics(tmp_path, monkeypatch):
    world = setup_tmp_world(tmp_path, monkeypatch)

    st_before = world.load_state("userC")
    assert st_before.decisions == 0

    chosen = {"id": "opt1", "title": "Test Option"}
    gate = {"risk": 0.4, "decision_status": "ok", "status": "ok"}
    values = {"total": 0.9, "request_id": "req-1"}

    st_after = world.update_from_decision(
        user_id="userC",
        query="Do something",
        chosen=chosen,
        gate=gate,
        values=values,
        planner={"steps": [{"done": True}, {"done": False}]},
        latency_ms=123.0,
    )

    assert st_after.decisions == 1
    # 移動平均なので「0〜0.4」「0.5〜0.9」のどこかに入る
    assert 0.0 <= st_after.avg_risk <= 0.4
    assert 0.5 <= st_after.avg_value <= 0.9
    assert st_after.last_query == "Do something"
    assert "Test Option" in st_after.last_chosen_title
    assert st_after.last_decision_status == "ok"


def test_inject_state_into_context_and_snapshot(tmp_path, monkeypatch):
    world = setup_tmp_world(tmp_path, monkeypatch)

    # 適当に一回 decision を流して world を埋める
    world.update_from_decision(
        user_id="userD",
        query="Q",
        chosen={"id": "1", "title": "T"},
        gate={"risk": 0.1, "status": "ok", "decision_status": "ok"},
        values={},  # 空dictでも動くことを確認したい
    )

    ctx = {}
    ctx2 = world.inject_state_into_context(ctx, user_id="userD")

    assert "world_state" in ctx2
    assert "world" in ctx2
    assert "projects" in ctx2["world"]
    assert "veritas_agi" in ctx2["world"]["projects"]

    snap = world.snapshot("veritas_agi")
    assert "progress" in snap
    assert "decision_count" in snap
    assert isinstance(snap["progress"], float)
    assert isinstance(snap["decision_count"], int)


def test_simulate_uses_world_state(tmp_path, monkeypatch):
    world = setup_tmp_world(tmp_path, monkeypatch)

    ctx = {
        "world_state": {
            "avg_value": 0.8,
            "avg_risk": 0.1,
            "plan_progress": 0.5,
            "decisions": 20,
        }
    }
    opt = {"score": 1.0}

    result = world.simulate(option=opt, context=ctx)
    assert 0.0 <= result["utility"] <= 1.0
    # decisions=20 なので confidence は 0 よりは大きいはず
    assert result["confidence"] > 0.0
    assert result["avg_value"] == 0.8
    assert result["avg_risk"] == 0.1


def test_simulate_decision_wraps_simulate(tmp_path, monkeypatch):
    world = setup_tmp_world(tmp_path, monkeypatch)

    res = world.simulate_decision(
        option={"score": 0.5},
        context={},
        user_id="userE",
    )
    assert "utility" in res
    assert "confidence" in res
    assert 0.0 <= res["utility"] <= 1.0
    assert 0.0 <= res["confidence"] <= 1.0


def test_next_hint_for_veritas_agi_initial_stage(tmp_path, monkeypatch):
    world = setup_tmp_world(tmp_path, monkeypatch)

    hint = world.next_hint_for_veritas_agi(user_id="userF")

    # 返り値の形をチェック
    assert hint["user_id"] == "userF"
    assert "decisions_user" in hint
    assert "progress" in hint
    assert "avg_value" in hint
    assert "avg_risk" in hint
    assert "focus" in hint
    assert "hint" in hint

    # focus は定義済みのどれかになっているはず
    assert hint["focus"] in {
        "collect_decisions",
        "stabilize_pipeline",
        "seed_agi_research",
        "design_benchmarks",
        "external_review",
    }

