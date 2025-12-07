from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from veritas_os.core import pipeline as api_pipeline



# =========================================================
# helper 関数のテスト
# =========================================================

def test_to_bool():
    tb = api_pipeline._to_bool
    assert tb(True) is True
    assert tb(False) is False
    assert tb(1) is True
    assert tb(0) is False
    assert tb("true") is True
    assert tb("TrUe") is True
    assert tb("yes") is True
    assert tb("on") is True
    assert tb("false") is False
    assert tb("no") is False
    assert tb(None) is False


def test_to_float_or():
    tf = api_pipeline._to_float_or
    assert tf("1.5", 0.0) == 1.5
    assert tf(2, 0.0) == 2.0
    assert tf("bad", 3.0) == 3.0
    assert tf(None, 4.0) == 4.0
    assert tf("null", 5.0) == 5.0
    assert tf("None", 6.0) == 6.0


def test_norm_alt():
    # text から title/description を補完
    d = api_pipeline._norm_alt({"text": "hello world", "score": "2.0"})
    assert d["title"] == "hello world"
    assert d["description"] == "hello world"
    assert d["score"] == 2.0
    assert d["score_raw"] == 2.0
    assert "id" in d and d["id"]

    # title あり / text なし
    d2 = api_pipeline._norm_alt({"title": "T", "description": "D"})
    assert d2["title"] == "T"
    assert d2["description"] == "D"
    assert d2["score"] == 1.0
    assert d2["score_raw"] == 1.0


def test_clip01_and_allow_prob(monkeypatch):
    c01 = api_pipeline._clip01
    assert c01(-1.0) == 0.0
    assert c01(0.5) == 0.5
    assert c01(2.0) == 1.0
    # 例外 → 0.0
    assert c01("bad") == 0.0

    # _allow_prob は predict_gate_label のラッパ
    monkeypatch.setattr(
        api_pipeline, "predict_gate_label", lambda text: {"allow": 0.8}
    )
    assert api_pipeline._allow_prob("foo") == 0.8


# =========================================================
# call_core_decide のテスト
# =========================================================

@pytest.mark.anyio
async def test_call_core_decide_sync_and_async():
    calls: List[Dict[str, Any]] = []

    # sync バージョン
    def core_sync(ctx=None, options=None, min_evidence=None, query=None):
        calls.append(
            {
                "kind": "sync",
                "ctx": ctx,
                "options": options,
                "min_evidence": min_evidence,
                "query": query,
            }
        )
        return {"ok": True}

    res_sync = await api_pipeline.call_core_decide(
        core_fn=core_sync,
        context={"foo": "bar"},
        query="Q",
        alternatives=[{"title": "alt1"}],
        min_evidence=3,
    )
    assert res_sync == {"ok": True}
    assert calls[0]["kind"] == "sync"
    assert calls[0]["ctx"]["query"] == "Q"
    assert calls[0]["options"][0]["title"] == "alt1"
    assert calls[0]["min_evidence"] == 3
    assert calls[0]["query"] == "Q"

    # async バージョン
    async def core_async(ctx=None, options=None, min_evidence=None, query=None):
        calls.append(
            {
                "kind": "async",
                "ctx": ctx,
                "options": options,
                "min_evidence": min_evidence,
                "query": query,
            }
        )
        return {"ok": "async"}

    res_async = await api_pipeline.call_core_decide(
        core_fn=core_async,
        context={"foo": "baz"},
        query="Q2",
        alternatives=[{"title": "alt2"}],
        min_evidence=4,
    )
    assert res_async == {"ok": "async"}
    assert calls[1]["kind"] == "async"
    assert calls[1]["ctx"]["query"] == "Q2"
    assert calls[1]["options"][0]["title"] == "alt2"
    assert calls[1]["min_evidence"] == 4
    assert calls[1]["query"] == "Q2"


# =========================================================
# run_decide_pipeline のメインテスト
# =========================================================

class DummyRequest:
    """request.query_params.get(...) だけ持つ簡易リクエスト。"""

    def __init__(self, params: Dict[str, Any] | None = None) -> None:
        self.query_params = params or {}


class DummyReqModel:
    """DecideRequest の代わりに使う簡易モデル（model_dump だけ実装）。"""

    def __init__(self, body: Dict[str, Any]) -> None:
        self._body = body

    def model_dump(self) -> Dict[str, Any]:
        return self._body


class DummyResponseModel:
    """
    DecideResponse のスタブ。
    model_validate -> インスタンス化 -> model_dump で dict を返すだけ。
    """

    def __init__(self, **data: Any) -> None:
        self._data = data

    @classmethod
    def model_validate(cls, data: Dict[str, Any]) -> "DummyResponseModel":
        return cls(**data)

    def model_dump(self) -> Dict[str, Any]:
        return self._data


@pytest.mark.anyio
async def test_run_decide_pipeline_happy_path(monkeypatch, tmp_path):
    # --- Path 系の差し替え（ログ・メタ・VAL_JSON） ---
    val_json = tmp_path / "val.json"
    meta_log = tmp_path / "meta.log"
    log_dir = tmp_path / "logs"
    dataset_dir = tmp_path / "dataset"

    monkeypatch.setattr(api_pipeline, "VAL_JSON", val_json, raising=False)
    monkeypatch.setattr(api_pipeline, "META_LOG", meta_log, raising=False)
    monkeypatch.setattr(api_pipeline, "LOG_DIR", log_dir, raising=False)
    monkeypatch.setattr(api_pipeline, "DATASET_DIR", dataset_dir, raising=False)

    # DecideResponse をスタブに差し替え（pydantic 依存を回避）
    monkeypatch.setattr(api_pipeline, "DecideResponse", DummyResponseModel, raising=False)

    # --- planner.plan_for_veritas_agi スタブ ---
    import veritas_os.core.planner as planner_mod
    monkeypatch.setattr(
        planner_mod,
        "plan_for_veritas_agi",
        lambda context, query: {"steps": [], "raw": None, "source": "test"},
        raising=False,
    )

    # --- MemoryOS スタブ ---
    class DummyMem:
        def __init__(self) -> None:
            self.put_calls: List[tuple] = []
            self.add_usage_calls: List[tuple] = []

        def recent(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
            # 今回は prior plan などは空でよい
            return []

        def search(
            self,
            query: str,
            k: int,
            kinds: List[str],
            min_sim: float = 0.3,
            user_id: str | None = None,
        ):
            # kinds ごとに1件ずつヒットさせる
            hits: List[Dict[str, Any]] = []
            for kind in kinds:
                hits.append(
                    {
                        "id": f"{kind}-1",
                        "kind": kind,
                        "text": f"{kind} memory text",
                        "score": 0.9,
                    }
                )
            return hits

        def put(self, user_id: str, key: str, value: Dict[str, Any]) -> None:
            self.put_calls.append((user_id, key, value))

        def add_usage(self, user_id: str, ids: List[str]) -> None:
            self.add_usage_calls.append((user_id, ids))

    dummy_mem = DummyMem()
    monkeypatch.setattr(api_pipeline, "mem", dummy_mem, raising=False)

    # --- WorldModel スタブ ---
    class DummyWorldModel:
        def __init__(self) -> None:
            self.updated = False

        def inject_state_into_context(self, context: Dict[str, Any], user_id: str) -> Dict[str, Any]:
            ctx = dict(context or {})
            ctx["world_state"] = {"user": user_id}
            ctx["user_id"] = user_id
            return ctx

        def simulate(self, user_id: str, query: str, chosen: Dict[str, Any]) -> Dict[str, Any]:
            return {"utility": 0.5, "confidence": 0.8}

        def update_from_decision(self, **kwargs: Any) -> None:
            self.updated = True

        def next_hint_for_veritas_agi(self) -> Dict[str, Any]:
            return {"hint": "do more tests"}

    dummy_world = DummyWorldModel()
    monkeypatch.setattr(api_pipeline, "world_model", dummy_world, raising=False)

    # --- veritas_core.decide スタブ ---
    def dummy_decide(
        ctx=None,
        context=None,
        options=None,
        alternatives=None,
        min_evidence=None,
        query=None,
        k=None,
        top_k=None,
    ):
        alts = alternatives or options or [
            {"title": "A", "description": "descA", "score": 1.0},
            {"title": "B", "description": "descB", "score": 0.5},
        ]
        return {
            "evidence": [
                {
                    "source": "core",
                    "uri": None,
                    "snippet": "core evidence",
                    "confidence": 0.9,
                }
            ],
            "critique": [{"text": "crit"}],
            "debate": [{"candidate": "A"}],
            "telos_score": 0.6,
            "fuji": {
                "status": "allow",
                "risk": 0.2,
                "reasons": ["ok"],
                "violations": [],
            },
            "alternatives": alts,
            "extras": {"metrics": {"foo": 1}},
            "chosen": alts[0],
            "rsi_note": "note",
            "evo": {"next": "evo"},
        }

    monkeypatch.setattr(api_pipeline.veritas_core, "decide", dummy_decide, raising=False)

    # --- FUJI スタブ ---
    monkeypatch.setattr(
        api_pipeline.fuji_core,
        "validate_action",
        lambda query, context: {
            "status": "allow",
            "risk": 0.2,
            "reasons": ["ok"],
            "violations": [],
        },
        raising=False,
    )

    # --- ValueCore スタブ ---
    class DummyVCResult:
        def __init__(self) -> None:
            self.scores = {"prudence": 0.7}
            self.total = 0.7
            self.top_factors = ["prudence"]
            self.rationale = "ok"

    monkeypatch.setattr(
        api_pipeline.value_core,
        "evaluate",
        lambda query, ctx: DummyVCResult(),
        raising=False,
    )

    # --- DebateOS スタブ ---
    def dummy_run_debate(query: str, options: List[Dict[str, Any]], context: Dict[str, Any]):
        return {
            "options": options,
            "chosen": options[0] if options else {},
            "source": "test",
            "raw": {"dummy": True},
        }

    monkeypatch.setattr(api_pipeline.debate_core, "run_debate", dummy_run_debate, raising=False)

    # --- WebSearch スタブ ---
    monkeypatch.setattr(
        api_pipeline,
        "web_search",
        lambda query, max_results=5: {
            "ok": True,
            "results": [
                {
                    "url": "https://example.com",
                    "snippet": "web snippet",
                    "title": "Web",
                }
            ],
        },
        raising=False,
    )

    # --- TrustLog / ShadowDecide / DatasetWriter スタブ ---
    monkeypatch.setattr(api_pipeline, "append_trust_log", lambda entry: None, raising=False)
    monkeypatch.setattr(
        api_pipeline,
        "write_shadow_decide",
        lambda request_id, body, chosen, telos, fuji: None,
        raising=False,
    )
    monkeypatch.setattr(
        api_pipeline,
        "build_dataset_record",
        lambda req_payload, res_payload, meta, eval_meta: {"req": req_payload},
        raising=False,
    )
    monkeypatch.setattr(
        api_pipeline,
        "append_dataset_record",
        lambda record: None,
        raising=False,
    )

    # --- ReasonOS スタブ ---
    monkeypatch.setattr(
        api_pipeline.reason_core,
        "reflect",
        lambda payload: {"next_value_boost": 0.0, "improvement_tips": ["tip"]},
        raising=False,
    )

    async def dummy_gen_tmpl(query, chosen, gate, values, planner):
        return {"template": True}

    monkeypatch.setattr(
        api_pipeline.reason_core,
        "generate_reflection_template",
        dummy_gen_tmpl,
        raising=False,
    )

    monkeypatch.setattr(
        api_pipeline.reason_core,
        "generate_reason",
        lambda **kwargs: {"text": "reason text"},
        raising=False,
    )

    # --- Persona ローダースタブ ---
    monkeypatch.setattr(
        api_pipeline,
        "load_persona",
        lambda: {"name": "default"},
        raising=False,
    )

    # --- DecideRequest 代わりの DummyReqModel を使う ---
    body = {
        "query": "Test veritas agi research",
        "context": {"user_id": "u1"},
        "options": [],
    }
    req_obj = DummyReqModel(body)

    request = DummyRequest()

    # ===== 実行 =====
    payload = await api_pipeline.run_decide_pipeline(req_obj, request)

    # ===== ざっくり検証 =====
    assert payload["query"] == "Test veritas agi research"
    assert payload["chosen"]  # 何かしら選ばれている
    assert isinstance(payload["alternatives"], list) and payload["alternatives"]
    assert isinstance(payload["evidence"], list) and payload["evidence"]
    assert "values" in payload and payload["values"]["scores"]
    assert payload["persona"]["name"] == "default"

    # metrics / extras
    extras = payload.get("extras") or {}
    metrics = extras.get("metrics") or {}
    assert "latency_ms" in metrics
    assert metrics["alts_count"] >= 1
    assert "mem_hits" in metrics

    # ReasonOS が note を付与していること
    assert "reason" in payload
    assert "note" in payload["reason"]
    assert payload["reason"]["note"]

    # WorldModel が更新されたこと
    assert dummy_world.updated is True

    # value-learning により VAL_JSON が作られているはず
    assert val_json.exists()
    data = json.loads(val_json.read_text(encoding="utf-8"))
    assert "ema" in data

    # veritas_agi ヒントが extras に入っていること
    assert "veritas_agi" in payload.get("extras", {})


