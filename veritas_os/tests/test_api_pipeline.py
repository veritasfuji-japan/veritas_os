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


def test_to_dict_variants():
    class DummyPydanticLike:
        def __init__(self) -> None:
            self.a = 1

        def model_dump(self, exclude_none: bool = True) -> Dict[str, Any]:
            return {"a": self.a}

    class DummyHasDict:
        def __init__(self) -> None:
            self.b = 2

        def dict(self) -> Dict[str, Any]:
            return {"b": self.b}

    dd = api_pipeline._to_dict
    assert dd({"x": 1}) == {"x": 1}
    assert dd(DummyPydanticLike()) == {"a": 1}
    assert dd(DummyHasDict()) == {"b": 2}
    assert dd(123) == {}


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
# run_decide_pipeline のためのダミー型
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


# =========================================================
# run_decide_pipeline 用 共通フィクスチャ
# =========================================================


@pytest.fixture
def patched_pipeline(monkeypatch, tmp_path):
    """
    run_decide_pipeline を安定してテストするための環境パッチ。

    - 外部 I/O（ファイル書き込み・TrustLog・DatasetWriter）を tmp_path / no-op 化
    - MemoryOS / WorldModel / FUJI / ValueCore / DebateOS / ReasonOS / Planner を
      シンプルなスタブに差し替え
    """
    import veritas_os.core.planner as planner_mod

    # --- Path 系の差し替え（ログ・メタ・VAL_JSON） ---
    val_json = tmp_path / "val.json"
    meta_log = tmp_path / "meta.log"
    log_dir = tmp_path / "logs"
    dataset_dir = tmp_path / "dataset"

    log_dir.mkdir(parents=True, exist_ok=True)
    dataset_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(api_pipeline, "VAL_JSON", val_json, raising=False)
    monkeypatch.setattr(api_pipeline, "META_LOG", meta_log, raising=False)
    monkeypatch.setattr(api_pipeline, "LOG_DIR", log_dir, raising=False)
    monkeypatch.setattr(api_pipeline, "DATASET_DIR", dataset_dir, raising=False)

    # DecideResponse をスタブに差し替え（pydantic 依存を回避）
    monkeypatch.setattr(
        api_pipeline, "DecideResponse", DummyResponseModel, raising=False
    )

    # DatasetWriter → no-op
    def fake_build_dataset_record(req_payload, res_payload, meta, eval_meta):
        return {
            "req": req_payload,
            "res": res_payload,
            "meta": meta,
            "eval_meta": eval_meta,
        }

    def fake_append_dataset_record(record):
        return None

    monkeypatch.setattr(
        api_pipeline, "build_dataset_record", fake_build_dataset_record, raising=False
    )
    monkeypatch.setattr(
        api_pipeline, "append_dataset_record", fake_append_dataset_record, raising=False
    )

    # TrustLog → no-op
    def fake_append_trust_log(entry: Dict[str, Any]) -> None:
        return None

    def fake_write_shadow_decide(
        request_id: str,
        body: Dict[str, Any],
        chosen: Dict[str, Any],
        telos_score: float,
        fuji_dict: Dict[str, Any],
    ) -> None:
        return None

    monkeypatch.setattr(
        api_pipeline, "append_trust_log", fake_append_trust_log, raising=False
    )
    monkeypatch.setattr(
        api_pipeline,
        "write_shadow_decide",
        fake_write_shadow_decide,
        raising=False,
    )

    # --- MemoryOS スタブ ---
    class DummyMem:
        def __init__(self) -> None:
            self.put_calls: List[tuple] = []
            self.add_usage_calls: List[tuple] = []

        def recent(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
            # prior plan などは空でよい
            return []

        def search(
            self,
            query: str,
            k: int,
            kinds: List[str],
            min_sim: float = 0.3,
            user_id: str | None = None,
        ):
            # 1回目（semantic+skills+episodic+doc）想定:
            # dict 形式で各 kind に1件ずつ
            if "episodic" in kinds or "semantic" in kinds:
                out: Dict[str, List[Dict[str, Any]]] = {}
                for kind in kinds:
                    out.setdefault(kind, []).append(
                        {
                            "id": f"{kind}-1",
                            "kind": kind,
                            "text": f"{kind} memory text",
                            "score": 0.9,
                        }
                    )
                return out
            # doc のみ検索などは doc だけ返す
            return {
                "doc": [
                    {
                        "id": "doc-1",
                        "kind": "doc",
                        "text": "doc memory text",
                        "score": 0.95,
                    }
                ]
            }

        def put(self, user_id: str, key: str, value: Dict[str, Any]) -> None:
            self.put_calls.append((user_id, key, value))

        def add_usage(self, user_id: str, ids: List[str]) -> None:
            self.add_usage_calls.append((user_id, ids))

    dummy_mem = DummyMem()
    monkeypatch.setattr(api_pipeline, "mem", dummy_mem, raising=False)

    # MemoryModel は読み込まれていない前提にしておく（applied=False 分岐）
    monkeypatch.setattr(api_pipeline, "MEM_VEC", None, raising=False)
    monkeypatch.setattr(api_pipeline, "MEM_CLF", None, raising=False)

    # --- WorldModel スタブ ---
    class DummyWorldModel:
        def __init__(self) -> None:
            self.updated = False

        def inject_state_into_context(
            self, context: Dict[str, Any], user_id: str
        ) -> Dict[str, Any]:
            ctx = dict(context or {})
            ctx["world_state"] = {"user": user_id}
            ctx["user_id"] = user_id
            return ctx

        def simulate(
            self, user_id: str, query: str, chosen: Dict[str, Any]
        ) -> Dict[str, Any]:
            # world.utility の計算用に utility / confidence を返す
            return {"utility": 0.8, "confidence": 0.9}

        def update_from_decision(
            self,
            user_id: str,
            query: str,
            chosen: Dict[str, Any],
            gate: Dict[str, Any],
            values: Dict[str, Any],
            planner: Dict[str, Any] | None = None,
            latency_ms: int | None = None,
        ) -> None:
            self.updated = True

        def next_hint_for_veritas_agi(self) -> Dict[str, Any]:
            return {"hint": "keep going"}

    dummy_world = DummyWorldModel()
    monkeypatch.setattr(api_pipeline, "world_model", dummy_world, raising=False)

    # --- PlannerOS スタブ ---
    def fake_plan_for_veritas_agi(context: Dict[str, Any], query: str) -> Dict[str, Any]:
        return {
            "steps": [
                {
                    "id": "s1",
                    "title": "First step",
                    "description": "Do something small but concrete.",
                },
                {
                    "id": "s2",
                    "title": "Second step",
                    "description": "Evaluate and iterate.",
                },
            ],
            "source": "test-planner",
            "raw": {"note": "planner"},
        }

    monkeypatch.setattr(
        planner_mod, "plan_for_veritas_agi", fake_plan_for_veritas_agi, raising=False
    )

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
            "extras": {"metrics": {"core_called": True}},
            "chosen": alts[0],
            "rsi_note": "note",
            "evo": {"next": "evo"},
        }

    monkeypatch.setattr(api_pipeline.veritas_core, "decide", dummy_decide, raising=False)

    def dummy_dedupe_alts(alts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return alts

    monkeypatch.setattr(
        api_pipeline.veritas_core, "_dedupe_alts", dummy_dedupe_alts, raising=False
    )

    # --- FUJI スタブ（デフォルト allow） ---
    def fake_fuji_allow(query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "allow",
            "risk": 0.2,
            "reasons": ["ok"],
            "violations": [],
            "modifications": [],
        }

    monkeypatch.setattr(
        api_pipeline.fuji_core, "validate_action", fake_fuji_allow, raising=False
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
    def dummy_run_debate(
        query: str, options: List[Dict[str, Any]], context: Dict[str, Any]
    ):
        enriched = []
        for i, opt in enumerate(options):
            d = dict(opt)
            d["verdict"] = "accept" if i == 0 else "reject"
            enriched.append(d)
        return {
            "options": enriched,
            "chosen": enriched[0] if enriched else {},
            "source": "test-debate",
            "raw": {"dummy": True},
        }

    monkeypatch.setattr(api_pipeline.debate_core, "run_debate", dummy_run_debate, raising=False)

    # --- WebSearch スタブ ---
    def fake_web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
        return {
            "ok": True,
            "results": [
                {
                    "url": "https://example.com",
                    "snippet": "web snippet",
                    "title": "Web",
                }
            ],
        }

    monkeypatch.setattr(api_pipeline, "web_search", fake_web_search, raising=False)

    # --- ReasonOS スタブ ---
    def fake_reflect(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "next_value_boost": 0.0,
            "improvement_tips": ["tip1", "tip2"],
        }

    async def dummy_gen_tmpl(query, chosen, gate, values, planner):
        return {"template": True}

    def dummy_generate_reason(
        query: str,
        planner: Dict[str, Any] | None,
        values: Dict[str, Any],
        gate: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {"text": "reason text"}

    monkeypatch.setattr(api_pipeline.reason_core, "reflect", fake_reflect, raising=False)
    monkeypatch.setattr(
        api_pipeline.reason_core,
        "generate_reflection_template",
        dummy_gen_tmpl,
        raising=False,
    )
    monkeypatch.setattr(
        api_pipeline.reason_core,
        "generate_reason",
        dummy_generate_reason,
        raising=False,
    )

    # --- Persona ローダースタブ ---
    monkeypatch.setattr(
        api_pipeline,
        "load_persona",
        lambda: {"name": "default"},
        raising=False,
    )

    return api_pipeline


# =========================================================
# run_decide_pipeline のメインテスト
# =========================================================


@pytest.mark.anyio
async def test_run_decide_pipeline_happy_path(patched_pipeline):
    pipeline = patched_pipeline

    body = {
        "query": "Test veritas agi research",
        "context": {"user_id": "u1"},
        "options": [],
    }
    req_obj = DummyReqModel(body)
    request = DummyRequest()

    payload = await pipeline.run_decide_pipeline(req_obj, request)

    # 基本フィールド
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
    assert "value_ema" in metrics
    assert "effective_risk" in metrics

    # ReasonOS が note を付与していること
    assert "reason" in payload
    assert "note" in payload["reason"]
    assert payload["reason"]["note"]

    # WorldModel hint
    assert "veritas_agi" in extras

    # value-learning により VAL_JSON が作られているはず
    val_json = pipeline.VAL_JSON
    assert val_json.exists()
    data = json.loads(val_json.read_text(encoding="utf-8"))
    assert "ema" in data


@pytest.mark.anyio
async def test_run_decide_pipeline_veritas_query_uses_web_and_plan(patched_pipeline):
    """VERITAS / AGI / 論文系クエリで PlannerOS + WebSearch 経路を踏むケース。"""
    pipeline = patched_pipeline

    q = "VERITAS OS の AGI 論文について教えて"
    body = {
        "query": q,
        "context": {"user_id": "u-veritas"},
    }
    req = DummyReqModel(body=body)
    request = DummyRequest()

    payload = await pipeline.run_decide_pipeline(req, request)

    # PlannerOS の結果が plan / extras.planner に反映されている
    assert "plan" in payload
    assert isinstance(payload["plan"], dict)
    assert len(payload["plan"].get("steps", [])) >= 1
    assert payload["planner"]["source"] == "test-planner"

    # WebSearch の結果が extras と evidence に反映されている
    extras = payload.get("extras") or {}
    assert "web_search" in extras
    assert extras["web_search"]["ok"] is True
    assert any(
        ev.get("source") == "web" for ev in payload.get("evidence", [])
    ), "web ソースの evidence が含まれているはず"

    # memory_meta に query/context が入っていること
    mem_meta = extras.get("memory_meta") or {}
    assert mem_meta.get("query") == q
    assert mem_meta.get("context", {}).get("user_id") == "u-veritas"


@pytest.mark.anyio
async def test_run_decide_pipeline_fuji_reject(monkeypatch, patched_pipeline):
    """FUJI が rejected を返した場合に gate が拒否になるか。"""
    pipeline = patched_pipeline

    # FUJI を reject 返すスタブに差し替え
    def fake_fuji_reject(query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "rejected",
            "reasons": ["policy_violation"],
            "violations": ["high_risk_action"],
            "risk": 0.99,
            "modifications": [],
        }

    monkeypatch.setattr(
        pipeline.fuji_core, "validate_action", fake_fuji_reject, raising=False
    )

    body = {
        "query": "危険な操作を実行して",
        "context": {"user_id": "u-risky"},
    }
    req = DummyReqModel(body=body)
    request = DummyRequest()

    payload = await pipeline.run_decide_pipeline(req, request)

    # FUJI gate により rejected になっていること
    assert payload["decision_status"] == "rejected"
    assert payload["gate"]["decision_status"] == "rejected"
    assert isinstance(payload.get("rejection_reason"), str)
    assert payload["rejection_reason"].startswith("FUJI gate:")
    # chosen / alternatives は空になっている想定
    assert payload["chosen"] == {} or payload["chosen"] is None
    assert payload["alternatives"] == [] or payload.get("options") == []


@pytest.mark.anyio
async def test_run_decide_pipeline_fast_mode_flags(patched_pipeline):
    """fast=true が context / body に正しく反映されるか。"""
    pipeline = patched_pipeline

    body = {
        "query": "Fast mode test",
        "fast": True,
        "context": {"user_id": "u-fast", "mode": "fast"},
    }
    req = DummyReqModel(body=body)
    # クエリパラメータ側からの fast 指定もつけてみる
    request = DummyRequest(params={"fast": "true"})

    payload = await pipeline.run_decide_pipeline(req, request)

    extras = payload.get("extras") or {}
    mem_meta = extras.get("memory_meta") or {}
    ctx = mem_meta.get("context") or {}

    # context 側に fast / mode=fast が立っているはず
    assert ctx.get("fast") is True
    assert ctx.get("mode") == "fast"


# =========================================================
# 追加テスト: 残りの分岐カバー狙い
# =========================================================


@pytest.mark.anyio
async def test_run_decide_pipeline_dataset_and_shadow_modes(monkeypatch, patched_pipeline):
    """
    dataset / shadow_only フラグ経路を踏みにいくテスト。

    - body と query params の両方に dataset / shadow_only を立てる
    - DatasetWriter / ShadowDecide の呼び出しが行われることを確認
    """
    pipeline = patched_pipeline

    dataset_calls: List[Dict[str, Any]] = []
    shadow_calls: List[Dict[str, Any]] = []

    def rec_build_dataset(req_payload, res_payload, meta, eval_meta):
        dataset_calls.append(
            {
                "req": req_payload,
                "meta": meta,
                "eval_meta": eval_meta,
            }
        )
        return {"ok": True}

    def rec_append_dataset(record):
        dataset_calls.append({"record": record})

    def rec_shadow(request_id, body, chosen, telos_score, fuji_dict):
        shadow_calls.append(
            {
                "request_id": request_id,
                "body": body,
                "chosen": chosen,
                "telos": telos_score,
                "fuji": fuji_dict,
            }
        )

    monkeypatch.setattr(pipeline, "build_dataset_record", rec_build_dataset, raising=False)
    monkeypatch.setattr(pipeline, "append_dataset_record", rec_append_dataset, raising=False)
    monkeypatch.setattr(pipeline, "write_shadow_decide", rec_shadow, raising=False)

    body = {
        "query": "dataset / shadow mode test",
        "context": {"user_id": "u-dataset"},
        "dataset": True,
        "shadow_only": True,
    }
    req = DummyReqModel(body=body)
    request = DummyRequest(params={"dataset": "1", "shadow_only": "true"})

    payload = await pipeline.run_decide_pipeline(req, request)

    # 正常にレスポンスが返っていること
    assert isinstance(payload, dict)
    assert payload.get("query") == "dataset / shadow mode test"

    # DatasetWriter が最低1回は呼ばれているはず
    assert len(dataset_calls) >= 1

    # shadow_only の場合、shadow_decide 用の書き込みも行われている想定
    assert len(shadow_calls) >= 1


@pytest.mark.anyio
async def test_run_decide_pipeline_with_memory_model(monkeypatch, patched_pipeline):
    """
    MEM_VEC / MEM_CLF が有効な場合の分岐をざっくり踏みにいく。

    Dummy の MemoryModel を差し込んで、
    - pipeline が例外なく完走すること
    - extras.memory_model のようなフィールドがあればそれも確認
    """
    pipeline = patched_pipeline

    class DummyMemModel:
        def __init__(self, kind: str) -> None:
            self.kind = kind
            self.applied = True  # "有効" 扱いさせるフラグ

        def __getattr__(self, name: str):
            # search / score など、どんなメソッドを呼ばれても無害に動くようにする
            def _dummy(*args, **kwargs):
                return {"ok": True, "kind": self.kind, "name": name}

            return _dummy

    monkeypatch.setattr(pipeline, "MEM_VEC", DummyMemModel("vec"), raising=False)
    monkeypatch.setattr(pipeline, "MEM_CLF", DummyMemModel("clf"), raising=False)

    body = {
        "query": "memory model test",
        "context": {"user_id": "u-mem"},
    }
    req = DummyReqModel(body=body)
    request = DummyRequest()

    payload = await pipeline.run_decide_pipeline(req, request)

    # 正常完走していること
    assert isinstance(payload, dict)
    assert payload.get("query") == "memory model test"

    extras = payload.get("extras") or {}

    # メモリモデルの結果が extras に載っている場合は簡単にチェック（あればで良い）
    mm = extras.get("memory_model") or extras.get("memory_models") or {}
    assert isinstance(mm, (dict, list))


@pytest.mark.anyio
async def test_run_decide_pipeline_core_decide_error_handling(monkeypatch, patched_pipeline):
    """
    veritas_core.decide が例外を投げた場合のハンドリング分岐。

    - decide を強制的に例外発生させる
    - run_decide_pipeline 自体は例外を外に投げずに payload を返すことを確認
    """
    pipeline = patched_pipeline

    def boom_decide(*args, **kwargs):
        raise RuntimeError("boom in core decide")

    monkeypatch.setattr(pipeline.veritas_core, "decide", boom_decide, raising=False)

    body = {
        "query": "core decide error test",
        "context": {"user_id": "u-error"},
    }
    req = DummyReqModel(body=body)
    request = DummyRequest()

    # 例外が外に伝播しないこと → テストがエラーにならなければOK
    payload = await pipeline.run_decide_pipeline(req, request)

    assert isinstance(payload, dict)
    # decision_status が error / failed 系ならそれも確認しておく
    status = payload.get("decision_status", "")
    assert isinstance(status, str)


@pytest.mark.anyio
async def test_run_decide_pipeline_no_memory_hits(monkeypatch, patched_pipeline):
    """
    MemoryOS.search がヒット0件 / 空結果の分岐を踏みにいくテスト。
    mem_hits=0 のような経路を確認する。
    """
    pipeline = patched_pipeline

    # mem.search を「常に空 dict」を返すスタブに
    def search_empty(
        query: str,
        k: int,
        kinds: List[str],
        min_sim: float = 0.3,
        user_id: str | None = None,
    ):
        return {}

    monkeypatch.setattr(pipeline.mem, "search", search_empty, raising=False)

    body = {
        "query": "no memory hits test",
        "context": {"user_id": "u-nomem"},
    }
    req = DummyReqModel(body=body)
    request = DummyRequest()

    payload = await pipeline.run_decide_pipeline(req, request)

    assert isinstance(payload, dict)

    extras = payload.get("extras") or {}
    metrics = extras.get("metrics") or {}
    # mem_hits が 0 になっているか（無ければスキップ）
    if "mem_hits" in metrics:
        assert metrics["mem_hits"] == 0





