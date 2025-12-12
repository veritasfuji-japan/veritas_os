import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from veritas_os.core import pipeline


"""
test_decide_pipeline_run.py（完全版）

目的:
- veritas_os.core.pipeline.run_decide_pipeline の
  1) ハッピーパス（AGI系・フル機能）
  2) 主要エラーパス（try/except の except 側）
  3) 非AGI + options 指定 + MLゲート無しパス
  を網羅的に踏む統合テスト。

方針:
- FastAPI 層を通さず、run_decide_pipeline に直接 DummyReq / DummyRequest を渡す。
- monkeypatch で MemoryOS / WorldModel / FUJI / ValueCore / DebateOS / ReasonOS /
  WebSearch / TrustLog / DatasetWriter / PersonaLoad などを STUB 化。
- ファイル I/O（valstats, meta.log, logs, dataset）は tmp_path に全差し替え。
"""


class DummyReq:
    """pipeline.run_decide_pipeline が必要とする最低限のインターフェイス"""

    def __init__(self, body: Dict[str, Any]) -> None:
        self._body = body

    def model_dump(self) -> Dict[str, Any]:
        return self._body


class DummyRequest:
    """FastAPI Request の代わりに query_params だけ持つダミー"""

    def __init__(self, query_params=None) -> None:
        self.query_params = query_params or {}


# -------------------------------------------------------------------
# 1. ハッピーパス: できるだけ多くの分岐を「正常系」で踏みにいく
# -------------------------------------------------------------------
@pytest.mark.anyio
async def test_run_decide_pipeline_happy_path(monkeypatch, tmp_path):
    # ---- ファイルパス系を tmp に差し替え ----
    val_json: Path = tmp_path / "valstats.json"
    meta_log: Path = tmp_path / "meta.log"
    log_dir: Path = tmp_path / "logs"
    dataset_dir: Path = tmp_path / "dataset"

    monkeypatch.setattr(pipeline, "VAL_JSON", val_json, raising=False)
    monkeypatch.setattr(pipeline, "META_LOG", meta_log, raising=False)
    monkeypatch.setattr(pipeline, "LOG_DIR", log_dir, raising=False)
    monkeypatch.setattr(pipeline, "DATASET_DIR", dataset_dir, raising=False)

    # ---- MemoryOS を stub ----

    def fake_recent(user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        # plan→alternatives 用 (過去プランから alts を作る分岐)
        return [
            {
                "value": {
                    "kind": "plan",
                    "query": "Test AGI research plan for VERITAS",
                    "planner": {
                        "steps": [
                            {"title": "過去プランの最初のステップ"},
                        ]
                    },
                }
            },
        ]

    def fake_search(**kwargs) -> Dict[str, Any]:
        # episodic / doc 両方を返して memory_evidence & episodic→alts を踏む
        return {
            "episodic": [
                {
                    "id": "ep1",
                    "kind": "episodic",
                    "score": 0.9,
                    "text": "[query] Test AGI\n[chosen] episodic option title",
                }
            ],
            "doc": [
                {
                    "id": "doc1",
                    "kind": "doc",
                    "score": 0.8,
                    "text": "VERITAS OS proto-AGI paper snippet",
                }
            ],
        }

    put_calls: List[Any] = []
    add_usage_calls: List[Any] = []

    def fake_put(user_id: str, key: str, value: Dict[str, Any]) -> None:
        put_calls.append((user_id, key, value))

    def fake_add_usage(user_id: str, ids) -> None:
        add_usage_calls.append((user_id, list(ids)))

    monkeypatch.setattr(pipeline.mem, "recent", fake_recent, raising=False)
    monkeypatch.setattr(pipeline.mem, "search", fake_search, raising=False)
    monkeypatch.setattr(pipeline.mem, "put", fake_put, raising=False)
    monkeypatch.setattr(pipeline.mem, "add_usage", fake_add_usage, raising=False)

    # ---- PlannerOS: plan_for_veritas_agi を stub ----
    # import は run_decide_pipeline の中で行われるので module を直接 patch
    import veritas_os.core.planner as planner_mod

    def fake_plan_for_veritas_agi(context: Dict[str, Any], query: str) -> Dict[str, Any]:
        return {
            "steps": [
                {
                    "id": "s1",
                    "title": "MVPデモを作る",
                    "detail": "Swagger/CLI で /v1/decide を叩くデモを作成",
                    "why": "VERITAS を第三者に見せるため",
                }
            ],
            "raw": {"llm": "stubbed"},
            "source": "fake_planner",
        }

    monkeypatch.setattr(
        planner_mod, "plan_for_veritas_agi", fake_plan_for_veritas_agi, raising=False
    )

    # ---- veritas_core.decide を stub ----

    def fake_core_decide() -> Dict[str, Any]:
        # call_core_decide は signature を見て kwargs を渡す。
        # ここでは **kwargs 無しのシンプル版にして、kwargs 未使用パスを踏む。
        return {
            "evidence": [
                {
                    "source": "core",
                    "uri": None,
                    "snippet": "core decide evidence",
                    "confidence": 0.9,
                }
            ],
            "critique": ["looks good"],
            "debate": [],
            "telos_score": 0.6,
            "fuji": {
                "status": "allow",
                "reasons": [],
                "violations": [],
                "risk": 0.2,
            },
            "alternatives": [
                {
                    "id": "core_alt",
                    "title": "Core Alternative",
                    "description": "from core decide",
                    "score": 1.0,
                }
            ],
            "extras": {
                "metrics": {"from_core": True},
            },
        }

    monkeypatch.setattr(pipeline.veritas_core, "decide", fake_core_decide, raising=False)

    # ---- world_model を stub ----

    def fake_inject_state_into_context(context: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        ctx = dict(context or {})
        ctx["world"] = {"user": user_id, "state": "injected"}
        return ctx

    def fake_simulate(user_id: str, query: str, chosen: Dict[str, Any]) -> Dict[str, Any]:
        # world.utility 用
        return {"utility": 0.7, "confidence": 0.8}

    def fake_update_from_decision(
        user_id: str,
        query: str,
        chosen: Dict[str, Any],
        gate: Dict[str, Any],
        values: Dict[str, Any],
        planner=None,
        latency_ms: float | None = None,
    ) -> None:
        # 何もしないが呼ばせる (例外にならないことだけ確認)
        return None

    def fake_next_hint_for_veritas_agi() -> Dict[str, Any]:
        return {"hint": "next-step-for-agi"}

    monkeypatch.setattr(
        pipeline.world_model, "inject_state_into_context", fake_inject_state_into_context
    )
    monkeypatch.setattr(pipeline.world_model, "simulate", fake_simulate, raising=False)
    monkeypatch.setattr(
        pipeline.world_model, "update_from_decision", fake_update_from_decision, raising=False
    )
    monkeypatch.setattr(
        pipeline.world_model,
        "next_hint_for_veritas_agi",
        fake_next_hint_for_veritas_agi,
        raising=False,
    )

    # ---- FUJI gate を stub ----

    def fake_validate_action(query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "allow",
            "reasons": ["ok"],
            "violations": [],
            "risk": 0.3,
            "modifications": [],
        }

    monkeypatch.setattr(
        pipeline.fuji_core, "validate_action", fake_validate_action, raising=False
    )

    # ---- ValueCore を stub ----

    class DummyVC:
        def __init__(self) -> None:
            self.scores = {"safety": 0.7, "value": 0.8}
            self.total = 0.75
            self.top_factors = ["safety", "value"]
            self.rationale = "stubbed value_core"

    def fake_value_evaluate(query: str, context: Dict[str, Any]) -> DummyVC:
        return DummyVC()

    monkeypatch.setattr(
        pipeline.value_core, "evaluate", fake_value_evaluate, raising=False
    )

    # ---- MemoryModel (MEM_VEC / MEM_CLF / predict_gate_label) を stub ----

    class DummyClasses(list):
        def tolist(self) -> list:
            return list(self)

    class DummyClf:
        def __init__(self) -> None:
            self.classes_ = DummyClasses(["allow", "deny"])

    monkeypatch.setattr(pipeline, "MEM_VEC", object(), raising=False)
    monkeypatch.setattr(pipeline, "MEM_CLF", DummyClf(), raising=False)

    def fake_predict_gate_label(text: str) -> Dict[str, float]:
        # allow を高めにして score ブーストを踏む
        return {"allow": 0.9}

    monkeypatch.setattr(pipeline, "predict_gate_label", fake_predict_gate_label, raising=False)

    # ---- DebateOS を stub ----

    def fake_run_debate(query: str, options: list, context: Dict[str, Any]) -> Dict[str, Any]:
        # 1件だけ reject にして risk_delta のロジックも踏む
        enriched = []
        for i, o in enumerate(options):
            d = dict(o)
            if i == 0:
                d["verdict"] = "reject"
            else:
                d["verdict"] = "ok"
            enriched.append(d)
        return {
            "options": enriched,
            "chosen": enriched[0],
            "source": "fake_debate",
            "raw": {"llm": "debate-stub"},
        }

    monkeypatch.setattr(
        pipeline.debate_core, "run_debate", fake_run_debate, raising=False
    )

    # ---- ReasonOS を stub ----

    def fake_reflect(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "next_value_boost": 0.01,
            "improvement_tips": ["tip1", "tip2"],
        }

    async def fake_generate_reflection_template(**kwargs) -> Dict[str, Any]:
        return {
            "kind": "reflection_template",
            "text": "stub template",
        }

    def fake_generate_reason(**kwargs) -> Dict[str, Any]:
        return {"text": "LLM reason stub"}

    monkeypatch.setattr(pipeline.reason_core, "reflect", fake_reflect, raising=False)
    monkeypatch.setattr(
        pipeline.reason_core,
        "generate_reflection_template",
        fake_generate_reflection_template,
        raising=False,
    )
    monkeypatch.setattr(
        pipeline.reason_core, "generate_reason", fake_generate_reason, raising=False
    )

    # ---- web_search / TrustLog / dataset_writer / persona を stub ----

    def fake_web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
        return {
            "ok": True,
            "results": [
                {
                    "url": "https://example.com/veritas",
                    "snippet": "VERITAS proto-AGI article",
                    "title": "VERITAS",
                }
            ],
        }

    monkeypatch.setattr(pipeline, "web_search", fake_web_search, raising=False)

    def fake_append_trust_log(entry: Dict[str, Any]) -> None:
        return None

    def fake_write_shadow_decide(
        request_id: str,
        body: Dict[str, Any],
        chosen: Dict[str, Any],
        telos: float,
        fuji_dict: Dict[str, Any],
    ) -> None:
        return None

    monkeypatch.setattr(pipeline, "append_trust_log", fake_append_trust_log, raising=False)
    monkeypatch.setattr(
        pipeline, "write_shadow_decide", fake_write_shadow_decide, raising=False
    )

    def fake_build_dataset_record(
        req_payload: Dict[str, Any],
        res_payload: Dict[str, Any],
        meta: Dict[str, Any],
        eval_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {"ok": True}

    def fake_append_dataset_record(record: Dict[str, Any]) -> None:
        return None

    monkeypatch.setattr(
        pipeline, "build_dataset_record", fake_build_dataset_record, raising=False
    )
    monkeypatch.setattr(
        pipeline, "append_dataset_record", fake_append_dataset_record, raising=False
    )

    def fake_load_persona() -> Dict[str, Any]:
        return {"name": "test-persona"}

    monkeypatch.setattr(pipeline, "load_persona", fake_load_persona, raising=False)

    # ---- DecideRequest / Request を組み立てて実行 ----
    body = {
        "query": "Test AGI research paper about VERITAS OS",
        "context": {
            "user_id": "user-123",
            "fast": False,
        },
        # options は空にして、plan / episodic から alternatives 生成分岐を踏む
    }
    req = DummyReq(body)
    request = DummyRequest(query_params={"fast": "1"})  # fast モード分岐も踏む

    payload = await pipeline.run_decide_pipeline(req, request)

    # ---- ざっくりとしたアサーション（副作用の確認も兼ねる） ----
    assert payload["decision_status"] == "allow"
    assert payload["gate"]["risk"] >= 0.0
    assert "veritas_agi" in payload["extras"]
    assert payload["extras"]["metrics"]["latency_ms"] > 0
    assert payload["memory_used_count"] >= 1
    assert payload["extras"]["metrics"]["mem_hits"] >= 0
    assert "planner" in payload
    assert payload["persona"]["name"] == "test-persona"

    # episodic / decision の mem.put が呼ばれていること
    keys = [k for _, k, _ in put_calls]
    assert any(k.startswith("decision_") for k in keys)
    assert any(k.startswith("episode_") for k in keys)

    # Value EMA が保存されていること（ファイルが作成されている）
    assert val_json.exists()
    data = json.loads(val_json.read_text(encoding="utf-8"))
    assert "ema" in data


# -------------------------------------------------------------------
# 2. エラーパス: 各種 try/except の except 側をなるべく踏みにいく
# -------------------------------------------------------------------
@pytest.mark.anyio
async def test_run_decide_pipeline_error_paths(monkeypatch, tmp_path):
    # パスはまた tmp に差し替え
    val_json: Path = tmp_path / "valstats.json"
    meta_log: Path = tmp_path / "meta.log"
    log_dir: Path = tmp_path / "logs"
    dataset_dir: Path = tmp_path / "dataset"

    monkeypatch.setattr(pipeline, "VAL_JSON", val_json, raising=False)
    monkeypatch.setattr(pipeline, "META_LOG", meta_log, raising=False)
    monkeypatch.setattr(pipeline, "LOG_DIR", log_dir, raising=False)
    monkeypatch.setattr(pipeline, "DATASET_DIR", dataset_dir, raising=False)

    # WorldOS: inject_state_into_context に例外を投げさせる
    def inject_raises(context: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        raise RuntimeError("world inject error")

    monkeypatch.setattr(
        pipeline.world_model,
        "inject_state_into_context",
        inject_raises,
        raising=False,
    )

    # MemoryOS: search で例外を投げる（memory retrieval error ブロック）
    def search_raises(**kwargs) -> Dict[str, Any]:
        raise RuntimeError("mem search error")

    monkeypatch.setattr(pipeline.mem, "search", search_raises, raising=False)

    def recent_empty(user_id: str, limit: int = 20) -> list:
        return []

    monkeypatch.setattr(pipeline.mem, "recent", recent_empty, raising=False)

    def put_noop(user_id: str, key: str, value: Dict[str, Any]) -> None:
        return None

    def add_usage_noop(user_id: str, ids) -> None:
        return None

    monkeypatch.setattr(pipeline.mem, "put", put_noop, raising=False)
    monkeypatch.setattr(pipeline.mem, "add_usage", add_usage_noop, raising=False)

    # web_search も例外を投げさせて [WebSearch] skipped ブロックを踏む
    def web_search_raises(query: str, max_results: int = 5) -> Dict[str, Any]:
        raise RuntimeError("web search error")

    monkeypatch.setattr(pipeline, "web_search", web_search_raises, raising=False)

    # veritas_core.decide 自体にも例外を投げさせて [decide] core error
    def decide_raises() -> Dict[str, Any]:
        raise RuntimeError("core decide error")

    monkeypatch.setattr(pipeline.veritas_core, "decide", decide_raises, raising=False)

    # WorldModel simulate でも例外を投げて [WorldModelOS] skip
    def simulate_raises(*args, **kwargs) -> Dict[str, Any]:
        raise RuntimeError("simulate error")

    monkeypatch.setattr(pipeline.world_model, "simulate", simulate_raises, raising=False)

    # FUJI validate_action でも例外 → デフォルトの allow にフォールバック
    def fuji_raises(query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        raise RuntimeError("fuji error")

    monkeypatch.setattr(pipeline.fuji_core, "validate_action", fuji_raises, raising=False)

    # ValueCore evaluate も例外 → evaluation failed
    def value_raises(query: str, context: Dict[str, Any]) -> Any:
        raise RuntimeError("value error")

    monkeypatch.setattr(pipeline.value_core, "evaluate", value_raises, raising=False)

    # ReasonOS reflect も例外 → 最終 fallback 系に入る
    def reflect_raises(payload: Dict[str, Any]) -> Dict[str, Any]:
        raise RuntimeError("reflect error")

    monkeypatch.setattr(pipeline.reason_core, "reflect", reflect_raises, raising=False)

    async def tmpl_raises(**kwargs) -> Dict[str, Any]:
        raise RuntimeError("template error")

    monkeypatch.setattr(
        pipeline.reason_core,
        "generate_reflection_template",
        tmpl_raises,
        raising=False,
    )

    def reason_raises(**kwargs) -> Dict[str, Any]:
        raise RuntimeError("llm reason error")

    monkeypatch.setattr(
        pipeline.reason_core,
        "generate_reason",
        reason_raises,
        raising=False,
    )

    # TrustLog / dataset / persist / world.update / hint も例外を投げて except を踏む
    def append_trust_log_raises(entry: Dict[str, Any]) -> None:
        raise RuntimeError("trust log error")

    def write_shadow_raises(*args, **kwargs) -> None:
        raise RuntimeError("shadow error")

    monkeypatch.setattr(pipeline, "append_trust_log", append_trust_log_raises, raising=False)
    monkeypatch.setattr(pipeline, "write_shadow_decide", write_shadow_raises, raising=False)

    def build_dataset_raises(*args, **kwargs) -> Dict[str, Any]:
        raise RuntimeError("dataset build error")

    def append_dataset_raises(record: Dict[str, Any]) -> None:
        raise RuntimeError("dataset append error")

    monkeypatch.setattr(
        pipeline, "build_dataset_record", build_dataset_raises, raising=False
    )
    monkeypatch.setattr(
        pipeline, "append_dataset_record", append_dataset_raises, raising=False
    )

    def update_from_decision_raises(*args, **kwargs) -> None:
        raise RuntimeError("world update error")

    def hint_raises() -> Dict[str, Any]:
        raise RuntimeError("hint error")

    monkeypatch.setattr(
        pipeline.world_model,
        "update_from_decision",
        update_from_decision_raises,
        raising=False,
    )
    monkeypatch.setattr(
        pipeline.world_model,
        "next_hint_for_veritas_agi",
        hint_raises,
        raising=False,
    )

    def fake_load_persona() -> Dict[str, Any]:
        return {}

    monkeypatch.setattr(pipeline, "load_persona", fake_load_persona, raising=False)

    body = {
        # "AGI" キーワードを含めて web_search ブランチも通し、
        # そこで例外を投げて [WebSearch] skipped ブロックも踏みにいく
        "query": "AGI safety test query to trigger web search",
        "context": {
            "user_id": "user-error",
        },
    }
    req = DummyReq(body)
    request = DummyRequest(query_params={})

    payload = await pipeline.run_decide_pipeline(req, request)

    # どれだけエラーが出ても run_decide_pipeline 自体は落ちないこと
    assert "decision_status" in payload
    assert "reason" in payload  # ReasonOS fallback が何らか入っている想定
    # 最終 fallback 文言の確認（実装に応じたいずれか）
    assert payload["reason"]["note"] in (
        "reflection/LLM both failed",
        "reflection only.",
        "自動反省メモはありません。",
    )


# -------------------------------------------------------------------
# 3. 非AGI + options 指定 + MLゲート無しパス
#    - "AGI" を含まない query → web_search は呼ばれないはず
#    - context.fast=True かつ query_params に fast 無し
#    - options を明示的に渡す → plan/memory からの options 生成をスキップ
#    - MEM_VEC / MEM_CLF = None → MLゲートのフォールバック分岐
# -------------------------------------------------------------------
@pytest.mark.anyio
async def test_run_decide_pipeline_with_explicit_options_and_no_ml_gate(
    monkeypatch, tmp_path
):
    # パスはまた tmp に差し替え
    val_json: Path = tmp_path / "valstats.json"
    meta_log: Path = tmp_path / "meta.log"
    log_dir: Path = tmp_path / "logs"
    dataset_dir: Path = tmp_path / "dataset"

    monkeypatch.setattr(pipeline, "VAL_JSON", val_json, raising=False)
    monkeypatch.setattr(pipeline, "META_LOG", meta_log, raising=False)
    monkeypatch.setattr(pipeline, "LOG_DIR", log_dir, raising=False)
    monkeypatch.setattr(pipeline, "DATASET_DIR", dataset_dir, raising=False)

    # MemoryOS: options を明示的に渡すので recent/search は "呼ばれても安全" な軽い stub
    def fake_recent(user_id: str, limit: int = 20) -> list:
        return []

    def fake_search(**kwargs) -> Dict[str, Any]:
        return {"episodic": [], "doc": []}

    monkeypatch.setattr(pipeline.mem, "recent", fake_recent, raising=False)
    monkeypatch.setattr(pipeline.mem, "search", fake_search, raising=False)

    def put_noop(user_id: str, key: str, value: Dict[str, Any]) -> None:
        return None

    def add_usage_noop(user_id: str, ids) -> None:
        return None

    monkeypatch.setattr(pipeline.mem, "put", put_noop, raising=False)
    monkeypatch.setattr(pipeline.mem, "add_usage", add_usage_noop, raising=False)

    # Planner は今回ほぼ使われないはずだが、念のため stub
    import veritas_os.core.planner as planner_mod

    def fake_plan_for_veritas_agi(context: Dict[str, Any], query: str) -> Dict[str, Any]:
        return {"steps": [], "raw": {}, "source": "unused_in_this_test"}

    monkeypatch.setattr(
        planner_mod, "plan_for_veritas_agi", fake_plan_for_veritas_agi, raising=False
    )

    # veritas_core.decide は、渡された options をベースに alternatives を返す想定の stub
    def fake_core_decide_with_options() -> Dict[str, Any]:
        return {
            "evidence": [],
            "critique": [],
            "debate": [],
            "telos_score": 0.5,
            "fuji": {
                "status": "allow",
                "reasons": [],
                "violations": [],
                "risk": 0.1,
            },
            "alternatives": [
                {
                    "id": "core_alt",
                    "title": "Core Alt",
                    "description": "core alt",
                    "score": 0.5,
                }
            ],
            "extras": {"metrics": {}},
        }

    monkeypatch.setattr(
        pipeline.veritas_core, "decide", fake_core_decide_with_options, raising=False
    )

    # world_model: inject は通すが、simulate / update / hint は全て no-op
    def fake_inject_state_into_context(context: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        ctx = dict(context or {})
        ctx["world"] = {"user": user_id}
        return ctx

    def fake_simulate(user_id: str, query: str, chosen: Dict[str, Any]) -> Dict[str, Any]:
        return {"utility": 0.0, "confidence": 0.0}

    def fake_update_from_decision(
        user_id: str,
        query: str,
        chosen: Dict[str, Any],
        gate: Dict[str, Any],
        values: Dict[str, Any],
        planner=None,
        latency_ms: float | None = None,
    ) -> None:
        return None

    def fake_next_hint_for_veritas_agi() -> Dict[str, Any]:
        return {"hint": "no-agi-hint"}

    monkeypatch.setattr(
        pipeline.world_model, "inject_state_into_context", fake_inject_state_into_context
    )
    monkeypatch.setattr(pipeline.world_model, "simulate", fake_simulate, raising=False)
    monkeypatch.setattr(
        pipeline.world_model, "update_from_decision", fake_update_from_decision, raising=False
    )
    monkeypatch.setattr(
        pipeline.world_model,
        "next_hint_for_veritas_agi",
        fake_next_hint_for_veritas_agi,
        raising=False,
    )

    # FUJI gate: allow だけ返すシンプル stub
    def fake_validate_action(query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "allow",
            "reasons": ["ok"],
            "violations": [],
            "risk": 0.1,
            "modifications": [],
        }

    monkeypatch.setattr(
        pipeline.fuji_core, "validate_action", fake_validate_action, raising=False
    )

    # ValueCore: 単純なスコアを返す
    class DummyVC2:
        def __init__(self) -> None:
            self.scores = {"safety": 1.0}
            self.total = 1.0
            self.top_factors = ["safety"]
            self.rationale = "all good"

    def fake_value_evaluate(query: str, context: Dict[str, Any]) -> DummyVC2:
        return DummyVC2()

    monkeypatch.setattr(
        pipeline.value_core, "evaluate", fake_value_evaluate, raising=False
    )

    # MLゲート: MEM_VEC / MEM_CLF 無し → fallback パスを踏ませる
    monkeypatch.setattr(pipeline, "MEM_VEC", None, raising=False)
    monkeypatch.setattr(pipeline, "MEM_CLF", None, raising=False)

    def predict_gate_label_must_not_be_called(text: str) -> Dict[str, float]:
        # MEM_VEC / MEM_CLF が None の場合、この関数は使われない想定
        raise AssertionError("predict_gate_label should not be called when MEM_VEC/MEM_CLF is None")

    monkeypatch.setattr(
        pipeline, "predict_gate_label", predict_gate_label_must_not_be_called, raising=False
    )

    # DebateOS: options をそのまま返すだけ
    def fake_run_debate_passthrough(
        query: str, options: list, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        return {
            "options": options,
            "chosen": options[0],
            "source": "fake_debate_passthrough",
            "raw": {},
        }

    monkeypatch.setattr(
        pipeline.debate_core, "run_debate", fake_run_debate_passthrough, raising=False
    )

    # ReasonOS: ごくシンプルな成功パス
    def fake_reflect(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"next_value_boost": 0.0, "improvement_tips": []}

    async def fake_generate_reflection_template(**kwargs) -> Dict[str, Any]:
        return {"kind": "reflection_template", "text": "ok"}

    def fake_generate_reason(**kwargs) -> Dict[str, Any]:
        return {"text": "ok"}

    monkeypatch.setattr(pipeline.reason_core, "reflect", fake_reflect, raising=False)
    monkeypatch.setattr(
        pipeline.reason_core,
        "generate_reflection_template",
        fake_generate_reflection_template,
        raising=False,
    )
    monkeypatch.setattr(
        pipeline.reason_core, "generate_reason", fake_generate_reason, raising=False
    )

    # web_search: 非AGI query なので呼ばれてほしくない → 呼ばれたら即失敗
    def web_search_must_not_be_called(query: str, max_results: int = 5) -> Dict[str, Any]:
        raise AssertionError("web_search should not be called for non-AGI queries in this test")

    monkeypatch.setattr(pipeline, "web_search", web_search_must_not_be_called, raising=False)

    # TrustLog / dataset / persona stub
    def fake_append_trust_log(entry: Dict[str, Any]) -> None:
        return None

    def fake_write_shadow_decide(*args, **kwargs) -> None:
        return None

    def fake_build_dataset_record(*args, **kwargs) -> Dict[str, Any]:
        return {"ok": True}

    def fake_append_dataset_record(record: Dict[str, Any]) -> None:
        return None

    def fake_load_persona() -> Dict[str, Any]:
        return {"name": "options-persona"}

    monkeypatch.setattr(pipeline, "append_trust_log", fake_append_trust_log, raising=False)
    monkeypatch.setattr(pipeline, "write_shadow_decide", fake_write_shadow_decide, raising=False)
    monkeypatch.setattr(
        pipeline, "build_dataset_record", fake_build_dataset_record, raising=False
    )
    monkeypatch.setattr(
        pipeline, "append_dataset_record", fake_append_dataset_record, raising=False
    )
    monkeypatch.setattr(pipeline, "load_persona", fake_load_persona, raising=False)

    # ---- DecideRequest / Request を組み立てて実行 ----
    body = {
        # ★ "AGI" を含めない query → web_search ブランチの else 側を踏む
        "query": "Simple planning for VERITAS demo",
        # ★ options を明示的に渡す → plan/memory からの options 生成をスキップ
        "options": [
            {"id": "opt1", "title": "First option", "description": "explicit 1"},
            {"id": "opt2", "title": "Second option", "description": "explicit 2"},
        ],
        "context": {
            # ★ context.fast=True + query_params に fast 無し
            "user_id": "user-options",
            "fast": True,
        },
    }
    req = DummyReq(body)
    request = DummyRequest(query_params={})

    payload = await pipeline.run_decide_pipeline(req, request)

    # ---- アサーション ----
    # 基本的な形は保たれていること
    assert payload["decision_status"] == "allow"
    assert "alternatives" in payload
    assert isinstance(payload["alternatives"], list)
    assert len(payload["alternatives"]) >= 1

    # options 由来の id か core_alt のいずれかが含まれていること
    alt_ids = {alt.get("id") for alt in payload["alternatives"]}
    assert {"opt1", "opt2"} & alt_ids or "core_alt" in alt_ids

    # persona は stub が反映されていること
    assert payload["persona"]["name"] == "options-persona"

    # 非AGI query なので web_search は呼ばれていない（呼ばれていたら上で AssertionError）
    # MEM_VEC / MEM_CLF=None なので predict_gate_label は一切使われていない（呼ばれていたら AssertionError）
    # Value EMA ファイルは fast=True でも更新される想定（実装に合わせて調整）
    assert val_json.exists()
    data = json.loads(val_json.read_text(encoding="utf-8"))
    assert "ema" in data

