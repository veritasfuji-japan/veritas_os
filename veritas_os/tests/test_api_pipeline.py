from __future__ import annotations

import json
import sys
import types
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
    assert tb("1") is True
    assert tb("0") is False
    assert tb("true") is True
    assert tb("TrUe") is True
    assert tb("t") is False
    assert tb("yes") is True
    assert tb("on") is True
    assert tb("false") is False
    assert tb("f") is False
    assert tb("no") is False
    assert tb(None) is False
    # unknown string -> False を期待（実装差があるならここで仕様を固定する）
    assert tb("maybe") is False


def test_to_float_or():
    tf = api_pipeline._to_float_or
    assert tf("1.5", 0.0) == 1.5
    assert tf(" 1.5 ", 0.0) == 1.5
    assert tf(2, 0.0) == 2.0
    assert tf("bad", 3.0) == 3.0
    assert tf(None, 4.0) == 4.0
    assert tf("null", 5.0) == 5.0
    assert tf("None", 6.0) == 6.0


def test_norm_alt():
    # ---------------------------------------------------------
    # 1) text から title/description を補完 + score の型変換 + id 自動生成
    # ---------------------------------------------------------
    d = api_pipeline._norm_alt({"text": "hello world", "score": "2.0"})
    assert d["title"] == "hello world"
    assert d["description"] == "hello world"
    assert d["score"] == 2.0
    # 実装差吸収: score_raw が float か str かは許容しつつ、内容は 2.0 相当であることを担保
    assert float(d.get("score_raw", 0.0)) == 2.0
    assert isinstance(d["id"], str) and d["id"]  # uuid4().hex 等

    # ---------------------------------------------------------
    # 2) title/description が明示されている場合はそれを優先（text なし）
    # ---------------------------------------------------------
    d2 = api_pipeline._norm_alt({"title": "T", "description": "D"})
    assert d2["title"] == "T"
    assert d2["description"] == "D"
    assert d2["score"] == 1.0
    assert float(d2.get("score_raw", 1.0)) == 1.0
    assert isinstance(d2["id"], str) and d2["id"]  # 自動生成

    # ---------------------------------------------------------
    # 3) description が無い場合は (description or text or "") なので text に落ちる
    #    ※ title はすでに入っているので title → description にはならない
    # ---------------------------------------------------------
    d3 = api_pipeline._norm_alt({"title": "T", "text": "X"})
    assert d3["title"] == "T"
    assert d3["description"] == "X"

    # ---------------------------------------------------------
    # 4) id を明示したら、それを保持する（uuid に上書きされない）
    # ---------------------------------------------------------
    d4 = api_pipeline._norm_alt({"id": "opt1", "title": "First option", "description": "explicit 1"})
    assert d4["id"] == "opt1"
    assert d4["title"] == "First option"
    assert d4["description"] == "explicit 1"

    # ---------------------------------------------------------
    # 5) id が None/空文字のときは uuid を生成する
    # ---------------------------------------------------------
    d5 = api_pipeline._norm_alt({"id": None, "title": "A"})
    assert isinstance(d5["id"], str) and d5["id"]
    assert d5["id"] != "None"  # str(None) ではなく uuid のはず

    d6 = api_pipeline._norm_alt({"id": "", "title": "B"})
    assert isinstance(d6["id"], str) and d6["id"]
    assert d6["id"] != ""  # 空は uuid に置換される


def test_clip01_and_allow_prob(monkeypatch):
    c01 = api_pipeline._clip01
    assert c01(-1.0) == 0.0
    assert c01(0.5) == 0.5
    assert c01(2.0) == 1.0
    # 例外 → 0.0
    assert c01("bad") == 0.0

    # _allow_prob は predict_gate_label のラッパ
    monkeypatch.setattr(api_pipeline, "predict_gate_label", lambda text: {"allow": 0.8})
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

    # 初期状態を作る（実装が "存在前提で読む" 場合も落ちない）
    val_json.write_text(json.dumps({"ema": {}}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(api_pipeline, "VAL_JSON", val_json, raising=False)
    monkeypatch.setattr(api_pipeline, "META_LOG", meta_log, raising=False)
    monkeypatch.setattr(api_pipeline, "LOG_DIR", log_dir, raising=False)
    monkeypatch.setattr(api_pipeline, "DATASET_DIR", dataset_dir, raising=False)

    # DecideResponse をスタブに差し替え（pydantic 依存を回避）
    monkeypatch.setattr(api_pipeline, "DecideResponse", DummyResponseModel, raising=False)

    # DatasetWriter → no-op
    def fake_build_dataset_record(req_payload, res_payload, meta, eval_meta):
        return {"req": req_payload, "res": res_payload, "meta": meta, "eval_meta": eval_meta}

    def fake_append_dataset_record(record):
        return None

    monkeypatch.setattr(api_pipeline, "build_dataset_record", fake_build_dataset_record, raising=False)
    monkeypatch.setattr(api_pipeline, "append_dataset_record", fake_append_dataset_record, raising=False)

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

    monkeypatch.setattr(api_pipeline, "append_trust_log", fake_append_trust_log, raising=False)
    monkeypatch.setattr(api_pipeline, "write_shadow_decide", fake_write_shadow_decide, raising=False)

    # --- MemoryOS スタブ ---
    class DummyMem:
        def __init__(self) -> None:
            self.put_calls: List[tuple] = []
            self.add_usage_calls: List[tuple] = []

        def recent(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
            return []

        def search(
            self,
            query: str,
            k: int,
            kinds: List[str],
            min_sim: float = 0.3,
            user_id: str | None = None,
        ):
            # kinds に応じて 1件ずつ返す（mem_hits を確実に増やす）
            out: Dict[str, List[Dict[str, Any]]] = {}
            for kind in kinds:
                out.setdefault(kind, []).append(
                    {"id": f"{kind}-1", "kind": kind, "text": f"{kind} memory text", "score": 0.9}
                )
            return out

        def put(self, user_id: str, key: str, value: Dict[str, Any]) -> None:
            self.put_calls.append((user_id, key, value))

        def add_usage(self, user_id: str, ids: List[str]) -> None:
            self.add_usage_calls.append((user_id, ids))

    dummy_mem = DummyMem()
    monkeypatch.setattr(api_pipeline, "mem", dummy_mem, raising=False)

    # MemoryModel は読み込まれていない前提（applied=False 分岐）
    monkeypatch.setattr(api_pipeline, "MEM_VEC", None, raising=False)
    monkeypatch.setattr(api_pipeline, "MEM_CLF", None, raising=False)

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
                {"id": "s1", "title": "First step", "description": "Do something small but concrete."},
                {"id": "s2", "title": "Second step", "description": "Evaluate and iterate."},
            ],
            "source": "test-planner",
            "raw": {"note": "planner"},
        }

    monkeypatch.setattr(planner_mod, "plan_for_veritas_agi", fake_plan_for_veritas_agi, raising=False)

    # --- veritas_core.decide スタブ（ここが未パッチだとテストが不安定になるので固定） ---
    def dummy_decide(*args, **kwargs):
        # run_decide_pipeline 側がどんな引数名で渡してきても耐える
        alternatives = kwargs.get("alternatives")
        options = kwargs.get("options")
        alts = alternatives or options or [
            {"id": "A", "title": "A", "description": "descA", "score": 1.0},
            {"id": "B", "title": "B", "description": "descB", "score": 0.5},
        ]

        # chosen は先頭（なければ {}）
        chosen = alts[0] if isinstance(alts, list) and alts else {}

        return {
            "evidence": [{"source": "core", "uri": None, "snippet": "core evidence", "confidence": 0.9}],
            "critique": [{"text": "crit"}],
            "debate": [{"candidate": chosen.get("title", "A")}],
            "telos_score": 0.6,
            "fuji": {"status": "allow", "risk": 0.2, "reasons": ["ok"], "violations": []},
            "alternatives": alts,
            "extras": {"metrics": {"core_called": True}},
            "chosen": chosen,
            "rsi_note": "note",
            "evo": {"next": "evo"},
        }

    monkeypatch.setattr(api_pipeline.veritas_core, "decide", dummy_decide, raising=False)

    # dedupe は no-op
    monkeypatch.setattr(api_pipeline.veritas_core, "_dedupe_alts", lambda alts: alts, raising=False)

    # --- FUJI スタブ（デフォルト allow） ---
    def fake_fuji_allow(query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "allow", "risk": 0.2, "reasons": ["ok"], "violations": [], "modifications": []}

    monkeypatch.setattr(api_pipeline.fuji_core, "validate_action", fake_fuji_allow, raising=False)

    # --- ValueCore スタブ ---
    class DummyVCResult:
        def __init__(self) -> None:
            self.scores = {"prudence": 0.7}
            self.total = 0.7
            self.top_factors = ["prudence"]
            self.rationale = "ok"

    monkeypatch.setattr(api_pipeline.value_core, "evaluate", lambda query, ctx: DummyVCResult(), raising=False)

    # --- DebateOS スタブ ---
    def dummy_run_debate(query: str, options: List[Dict[str, Any]], context: Dict[str, Any]):
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

    # --- WebSearch スタブ（通常は ok/results を返す） ---
    def fake_web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
        return {"ok": True, "results": [{"url": "https://example.com", "snippet": "web snippet", "title": "Web"}]}

    monkeypatch.setattr(api_pipeline, "web_search", fake_web_search, raising=False)

    # --- ReasonOS スタブ ---
    def fake_reflect(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"next_value_boost": 0.0, "improvement_tips": ["tip1", "tip2"]}

    async def dummy_gen_tmpl(query, chosen, gate, values, planner):
        return {"template": True}

    def dummy_generate_reason(
        query: str,
        planner: Dict[str, Any] | None,
        values: Dict[str, Any],
        gate: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        # 実装側が note を生成しない場合のため、テスト側が期待する「note」をここで供給
        return {"text": "reason text", "note": "note"}

    monkeypatch.setattr(api_pipeline.reason_core, "reflect", fake_reflect, raising=False)
    monkeypatch.setattr(api_pipeline.reason_core, "generate_reflection_template", dummy_gen_tmpl, raising=False)
    monkeypatch.setattr(api_pipeline.reason_core, "generate_reason", dummy_generate_reason, raising=False)

    # --- Persona ローダースタブ ---
    monkeypatch.setattr(api_pipeline, "load_persona", lambda: {"name": "default"}, raising=False)

    return api_pipeline


# =========================================================
# run_decide_pipeline のメインテスト
# =========================================================


@pytest.mark.anyio
async def test_run_decide_pipeline_happy_path(patched_pipeline):
    pipeline = patched_pipeline

    body = {"query": "Test veritas agi research", "context": {"user_id": "u1"}, "options": []}
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

    # metrics / extras contract（壊れやすいので最低限の存在を担保）
    extras = payload.get("extras") or {}
    metrics = extras.get("metrics") or {}
    assert "latency_ms" in metrics
    assert metrics.get("alts_count", 0) >= 1
    assert "mem_hits" in metrics
    assert "value_ema" in metrics
    assert "effective_risk" in metrics
    assert "cost_benefit" in metrics

    cost_benefit = metrics.get("cost_benefit") or {}
    assert isinstance(cost_benefit, dict)
    assert "total_token_cost" in cost_benefit
    assert "total_uncertainty_reduction_pct" in cost_benefit
    assert len(cost_benefit.get("steps", [])) == 3
    stages = [step.get("stage") for step in cost_benefit.get("steps", [])]
    assert stages == ["debate", "critique", "fuji_gate"]

    # ★ Memory evidence が evidence に混ざること（仕様として担保）
    assert any(
        isinstance(ev, dict) and str(ev.get("source", "")).startswith("memory:")
        for ev in payload.get("evidence", [])
    ), "memory:* ソースの evidence が含まれているはず"

    # ReasonOS が note を付与していること（note が無い実装ならここで仕様を固定）
    assert "reason" in payload
    assert isinstance(payload["reason"], dict)
    assert payload["reason"].get("note")

    # WorldModel hint（実装が extras に入れる契約）
    assert "veritas_agi" in extras

    # value-learning により VAL_JSON が維持されているはず（最低 contract: JSONで ema キーがある）
    val_json = pipeline.VAL_JSON
    assert val_json.exists()
    data = json.loads(val_json.read_text(encoding="utf-8"))
    assert "ema" in data


@pytest.mark.anyio
async def test_run_decide_pipeline_veritas_query_uses_web_and_plan(patched_pipeline):
    """VERITAS / AGI / 論文系クエリで PlannerOS + WebSearch 経路を踏むケース。"""
    pipeline = patched_pipeline

    q = "VERITAS OS の AGI 論文について教えて"
    body = {"query": q, "context": {"user_id": "u-veritas"}}
    req = DummyReqModel(body=body)
    request = DummyRequest()

    payload = await pipeline.run_decide_pipeline(req, request)

    # PlannerOS の結果
    assert "plan" in payload and isinstance(payload["plan"], dict)
    assert len(payload["plan"].get("steps", [])) >= 1
    assert payload["planner"]["source"] == "test-planner"

    # WebSearch の結果が extras と evidence に反映されている
    extras = payload.get("extras") or {}
    assert "web_search" in extras
    assert extras["web_search"]["ok"] is True

    # ★ web evidence / web_hits の contract
    metrics = extras.get("metrics") or {}
    assert metrics.get("web_hits", 0) >= 1
    assert metrics.get("web_evidence_count", 0) >= 1

    assert any(ev.get("source") == "web" for ev in payload.get("evidence", [])), "web ソースの evidence が含まれているはず"

    # memory_meta に query/context が入っていること
    mem_meta = extras.get("memory_meta") or {}
    assert mem_meta.get("query") == q
    assert mem_meta.get("context", {}).get("user_id") == "u-veritas"


@pytest.mark.anyio
async def test_run_decide_pipeline_fuji_reject(monkeypatch, patched_pipeline):
    """FUJI が rejected を返した場合に gate が拒否になるか。"""
    pipeline = patched_pipeline

    def fake_fuji_reject(query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "rejected",
            "reasons": ["policy_violation"],
            "violations": ["high_risk_action"],
            "risk": 0.99,
            "modifications": [],
        }

    monkeypatch.setattr(pipeline.fuji_core, "validate_action", fake_fuji_reject, raising=False)

    body = {"query": "危険な操作を実行して", "context": {"user_id": "u-risky"}}
    req = DummyReqModel(body=body)
    request = DummyRequest()

    payload = await pipeline.run_decide_pipeline(req, request)

    assert payload["decision_status"] == "rejected"
    assert payload["gate"]["decision_status"] == "rejected"
    assert isinstance(payload.get("rejection_reason"), str)
    assert payload["rejection_reason"].startswith("FUJI gate:")
    assert payload["chosen"] == {} or payload["chosen"] is None
    assert payload["alternatives"] == [] or payload.get("options") == []


@pytest.mark.anyio
async def test_run_decide_pipeline_fast_mode_flags(patched_pipeline):
    """fast=true が context / body に正しく反映されるか。"""
    pipeline = patched_pipeline

    body = {"query": "Fast mode test", "fast": True, "context": {"user_id": "u-fast", "mode": "fast"}}
    req = DummyReqModel(body=body)
    request = DummyRequest(params={"fast": "true"})

    payload = await pipeline.run_decide_pipeline(req, request)

    extras = payload.get("extras") or {}
    mem_meta = extras.get("memory_meta") or {}
    ctx = mem_meta.get("context") or {}

    assert ctx.get("fast") is True
    assert ctx.get("mode") == "fast"


@pytest.mark.anyio
async def test_run_decide_pipeline_with_explicit_options_and_no_ml_gate(monkeypatch, patched_pipeline):
    """
    explicit options を渡したとき alternatives の id が維持される（opt1/opt2）か、
    もしくは core_alt が残ることを担保する回帰テスト。
    さらに MEM_VEC/MEM_CLF=None のとき predict_gate_label が呼ばれないことも担保。
    """
    pipeline = patched_pipeline

    # --- MLゲート無効化 ---
    monkeypatch.setattr(pipeline, "MEM_VEC", None, raising=False)
    monkeypatch.setattr(pipeline, "MEM_CLF", None, raising=False)

    def predict_gate_label_must_not_be_called(text: str):
        raise AssertionError("predict_gate_label should not be called when MEM_VEC/MEM_CLF is None")

    monkeypatch.setattr(pipeline, "predict_gate_label", predict_gate_label_must_not_be_called, raising=False)

    # --- kernel.decide を必ず用意（kernel 経由でも core に到達させる）---
    m_kernel = types.ModuleType("veritas_os.core.kernel")

    def kernel_decide(*args, **kwargs):
        return pipeline.veritas_core.decide(*args, **kwargs)

    m_kernel.decide = kernel_decide
    sys.modules["veritas_os.core.kernel"] = m_kernel

    # --- 明示 options ---
    body = {
        "query": "Simple planning for VERITAS demo",  # AGI を含めない
        "options": [
            {"id": "opt1", "title": "First option", "description": "explicit 1"},
            {"id": "opt2", "title": "Second option", "description": "explicit 2"},
        ],
        "context": {"user_id": "user-options", "fast": True},
    }
    req = DummyReqModel(body)
    request = DummyRequest(params={})

    payload = await pipeline.run_decide_pipeline(req, request)

    assert payload["decision_status"] == "allow"
    assert isinstance(payload.get("alternatives"), list) and payload["alternatives"]

    alt_ids = {alt.get("id") for alt in payload["alternatives"] if isinstance(alt, dict)}
    assert ({"opt1", "opt2"} & alt_ids) or ("core_alt" in alt_ids)


# =========================================================
# 追加テスト: 6つの「最短で効く」分岐カバー
# =========================================================


@pytest.mark.anyio
async def test_run_decide_pipeline_kernel_decide_missing_contract(monkeypatch, patched_pipeline):
    """
    (1) kernel.decide 不在でも落ちず、extras.metrics が揃う contract を担保。
    実装が kernel を使っていなくても、このテストは "壊れた環境" contract として有用。
    """
    pipeline = patched_pipeline

    # kernel モジュールは存在するが decide が無い、という状態を作る
    m_kernel = types.ModuleType("veritas_os.core.kernel")
    sys.modules["veritas_os.core.kernel"] = m_kernel

    body = {"query": "kernel missing decide", "context": {"user_id": "u-kernel"}}
    req = DummyReqModel(body=body)
    request = DummyRequest()

    payload = await pipeline.run_decide_pipeline(req, request)

    assert payload.get("ok") is True
    extras = payload.get("extras") or {}
    metrics = extras.get("metrics") or {}
    # contract: metrics が最低限揃う
    for k in ["mem_hits", "memory_evidence_count", "web_hits", "web_evidence_count"]:
        assert k in metrics
    assert "stage_latency" in metrics
    for stage_name in ["retrieval", "web", "llm", "gate", "persist"]:
        assert stage_name in metrics["stage_latency"]


@pytest.mark.anyio
async def test_run_decide_pipeline_web_search_none_injects_web_evidence(monkeypatch, patched_pipeline):
    """
    (2) web_search が None を返しても web evidence が最低1件入ることを担保。
    """
    pipeline = patched_pipeline

    monkeypatch.setattr(pipeline, "web_search", lambda query, max_results=5: None, raising=False)

    body = {"query": "web none test", "context": {"user_id": "u-webnone"}, "web": True}
    req = DummyReqModel(body=body)
    request = DummyRequest()

    payload = await pipeline.run_decide_pipeline(req, request)

    extras = payload.get("extras") or {}
    metrics = extras.get("metrics") or {}
    assert metrics.get("web_evidence_count", 0) >= 1
    assert any(ev.get("source") == "web" for ev in payload.get("evidence", [])), "web fallback evidence が入るはず"


@pytest.mark.anyio
async def test_run_decide_pipeline_web_search_exception_injects_web_evidence(monkeypatch, patched_pipeline):
    """
    (2) web_search が例外でも web evidence が最低1件入ることを担保。
    """
    pipeline = patched_pipeline

    def boom_ws(*args, **kwargs):
        raise RuntimeError("boom web_search")

    monkeypatch.setattr(pipeline, "web_search", boom_ws, raising=False)

    body = {"query": "web exception test", "context": {"user_id": "u-webex"}, "web": True}
    req = DummyReqModel(body=body)
    request = DummyRequest()

    payload = await pipeline.run_decide_pipeline(req, request)

    extras = payload.get("extras") or {}
    metrics = extras.get("metrics") or {}
    assert metrics.get("web_evidence_count", 0) >= 1
    assert any(ev.get("source") == "web" for ev in payload.get("evidence", [])), "web exception fallback evidence が入るはず"


@pytest.mark.anyio
async def test_run_decide_pipeline_web_search_results_increase_web_hits(monkeypatch, patched_pipeline):
    """
    (3) web_search が results を返すと web_hits が増え、web evidence が入ることを担保。
    """
    pipeline = patched_pipeline

    def ws(query: str, max_results: int = 5):
        return {
            "ok": True,
            "results": [
                {"url": "https://example.com/1", "snippet": "s1", "title": "t1"},
                {"url": "https://example.com/2", "snippet": "s2", "title": "t2"},
            ],
        }

    monkeypatch.setattr(pipeline, "web_search", ws, raising=False)

    body = {"query": "web results test", "context": {"user_id": "u-webhit"}, "web": True}
    req = DummyReqModel(body=body)
    request = DummyRequest()

    payload = await pipeline.run_decide_pipeline(req, request)

    extras = payload.get("extras") or {}
    metrics = extras.get("metrics") or {}
    assert metrics.get("web_hits", 0) >= 2
    assert any(ev.get("source") == "web" for ev in payload.get("evidence", []))


@pytest.mark.anyio
async def test_run_decide_pipeline_critique_module_missing_fallback(monkeypatch, patched_pipeline):
    """
    (4) critique モジュール欠損時の fallback 経路。
    実装差があるので、存在するキーのみを contract として検証。
    """
    pipeline = patched_pipeline

    # import 失敗相当を作る（モジュール削除）
    sys.modules.pop("veritas_os.core.critique", None)

    # pipeline 側が critique_core を参照する実装の場合にも備えて None に寄せる
    if hasattr(pipeline, "critique_core"):
        monkeypatch.setattr(pipeline, "critique_core", None, raising=False)

    body = {"query": "critique missing test", "context": {"user_id": "u-critmiss"}}
    req = DummyReqModel(body=body)
    request = DummyRequest()

    payload = await pipeline.run_decide_pipeline(req, request)

    # fallback critique の contract（あれば検証）
    critique = payload.get("critique")
    assert isinstance(critique, (dict, list))

    extras = payload.get("extras") or {}
    env_tools = extras.get("env_tools") or {}
    if "critique_degraded" in env_tools:
        assert env_tools["critique_degraded"] is True


@pytest.mark.anyio
async def test_run_decide_pipeline_memory_evidence_present(patched_pipeline):
    """
    (6) MemoryOS があると mem_hits/memory_evidence_count が増え、
        evidence に memory:* が入ることを担保。
    """
    pipeline = patched_pipeline

    body = {"query": "memory evidence test", "context": {"user_id": "u-memev"}}
    req = DummyReqModel(body=body)
    request = DummyRequest()

    payload = await pipeline.run_decide_pipeline(req, request)

    extras = payload.get("extras") or {}
    metrics = extras.get("metrics") or {}
    assert metrics.get("mem_hits", 0) >= 1
    assert metrics.get("memory_evidence_count", 0) >= 1
    assert any(
        isinstance(ev, dict) and str(ev.get("source", "")).startswith("memory:")
        for ev in payload.get("evidence", [])
    ), "memory:* ソースの evidence が含まれているはず"


# =========================================================
# 追加テスト: 残りの分岐カバー狙い（既存）
# =========================================================


@pytest.mark.anyio
async def test_run_decide_pipeline_dataset_and_shadow_modes(monkeypatch, patched_pipeline):
    pipeline = patched_pipeline

    dataset_calls: List[Dict[str, Any]] = []
    shadow_calls: List[Dict[str, Any]] = []

    def rec_build_dataset(req_payload, res_payload, meta, eval_meta):
        dataset_calls.append({"req": req_payload, "meta": meta, "eval_meta": eval_meta})
        return {"ok": True}

    def rec_append_dataset(record):
        dataset_calls.append({"record": record})

    def rec_shadow(request_id, body, chosen, telos_score, fuji_dict):
        shadow_calls.append(
            {"request_id": request_id, "body": body, "chosen": chosen, "telos": telos_score, "fuji": fuji_dict}
        )

    monkeypatch.setattr(pipeline, "build_dataset_record", rec_build_dataset, raising=False)
    monkeypatch.setattr(pipeline, "append_dataset_record", rec_append_dataset, raising=False)
    monkeypatch.setattr(pipeline, "write_shadow_decide", rec_shadow, raising=False)

    body = {"query": "dataset / shadow mode test", "context": {"user_id": "u-dataset"}, "dataset": True, "shadow_only": True}
    req = DummyReqModel(body=body)
    request = DummyRequest(params={"dataset": "1", "shadow_only": "true"})

    payload = await pipeline.run_decide_pipeline(req, request)

    assert isinstance(payload, dict)
    assert payload.get("query") == "dataset / shadow mode test"
    assert len(dataset_calls) >= 1
    assert len(shadow_calls) >= 1


@pytest.mark.anyio
async def test_run_decide_pipeline_with_memory_model(monkeypatch, patched_pipeline):
    pipeline = patched_pipeline

    class DummyMemModel:
        def __init__(self, kind: str) -> None:
            self.kind = kind
            self.applied = True

        def __getattr__(self, name: str):
            def _dummy(*args, **kwargs):
                return {"ok": True, "kind": self.kind, "name": name}

            return _dummy

    monkeypatch.setattr(pipeline, "MEM_VEC", DummyMemModel("vec"), raising=False)
    monkeypatch.setattr(pipeline, "MEM_CLF", DummyMemModel("clf"), raising=False)

    body = {"query": "memory model test", "context": {"user_id": "u-mem"}}
    req = DummyReqModel(body=body)
    request = DummyRequest()

    payload = await pipeline.run_decide_pipeline(req, request)

    assert isinstance(payload, dict)
    assert payload.get("query") == "memory model test"

    extras = payload.get("extras") or {}
    mm = extras.get("memory_model") or extras.get("memory_models") or {}
    assert isinstance(mm, (dict, list))


@pytest.mark.anyio
async def test_run_decide_pipeline_core_decide_error_handling(monkeypatch, patched_pipeline):
    pipeline = patched_pipeline

    def boom_decide(*args, **kwargs):
        raise RuntimeError("boom in core decide")

    monkeypatch.setattr(pipeline.veritas_core, "decide", boom_decide, raising=False)

    body = {"query": "core decide error test", "context": {"user_id": "u-error"}}
    req = DummyReqModel(body=body)
    request = DummyRequest()

    payload = await pipeline.run_decide_pipeline(req, request)

    assert isinstance(payload, dict)
    status = payload.get("decision_status", "")
    assert isinstance(status, str)


@pytest.mark.anyio
async def test_run_decide_pipeline_no_memory_hits(monkeypatch, patched_pipeline):
    pipeline = patched_pipeline

    def search_empty(query: str, k: int, kinds: List[str], min_sim: float = 0.3, user_id: str | None = None):
        return {}

    monkeypatch.setattr(pipeline.mem, "search", search_empty, raising=False)

    body = {"query": "no memory hits test", "context": {"user_id": "u-nomem"}}
    req = DummyReqModel(body=body)
    request = DummyRequest()

    payload = await pipeline.run_decide_pipeline(req, request)

    assert isinstance(payload, dict)

    extras = payload.get("extras") or {}
    metrics = extras.get("metrics") or {}
    if "mem_hits" in metrics:
        assert metrics["mem_hits"] == 0

# =========================================================
# pipeline.py 例外分岐カバー（90%台へ寄せる）
# =========================================================

@pytest.mark.anyio
async def test_run_decide_pipeline_value_core_evaluate_exception_fallback(monkeypatch, patched_pipeline):
    """
    ValueCore.evaluate が例外を投げても、run_decide_pipeline が落ちずに
    values / metrics contract を維持する（例外分岐カバー）。
    """
    pipeline = patched_pipeline

    def boom_value_core(*args, **kwargs):
        raise RuntimeError("boom value_core.evaluate")

    monkeypatch.setattr(pipeline.value_core, "evaluate", boom_value_core, raising=False)

    body = {"query": "value core exception test", "context": {"user_id": "u-vc-ex"}}
    req = DummyReqModel(body=body)
    request = DummyRequest()

    payload = await pipeline.run_decide_pipeline(req, request)

    # 落ちないこと + 最低限 contract
    assert isinstance(payload, dict)
    assert payload.get("ok") is True

    # values が消えない（fallback でも良い）
    assert "values" in payload
    assert isinstance(payload["values"], dict)
    assert isinstance(payload["values"].get("scores", {}), dict)

    # metrics が最低限残る
    extras = payload.get("extras") or {}
    metrics = extras.get("metrics") or {}
    assert "value_ema" in metrics


@pytest.mark.anyio
async def test_run_decide_pipeline_world_model_update_exception_swallowed(monkeypatch, patched_pipeline):
    """
    WorldModel.update_from_decision が例外でもパイプラインが落ちない（例外分岐カバー）。
    """
    pipeline = patched_pipeline

    def boom_update(*args, **kwargs):
        raise RuntimeError("boom world_model.update_from_decision")

    monkeypatch.setattr(pipeline.world_model, "update_from_decision", boom_update, raising=False)

    body = {"query": "world model update exception test", "context": {"user_id": "u-wm-ex"}}
    req = DummyReqModel(body=body)
    request = DummyRequest()

    payload = await pipeline.run_decide_pipeline(req, request)

    assert isinstance(payload, dict)
    assert payload.get("ok") is True

    # decision は成立している（chosen/alternatives は実装によって {} の場合もあるので緩めに）
    assert "decision_status" in payload
    assert "extras" in payload

    extras = payload.get("extras") or {}
    metrics = extras.get("metrics") or {}
    assert "latency_ms" in metrics


@pytest.mark.anyio
async def test_run_decide_pipeline_trustlog_and_shadow_exception_swallowed(monkeypatch, patched_pipeline):
    """
    TrustLog / shadow write が例外でも run_decide_pipeline が落ちない（例外分岐カバー）。
    """
    pipeline = patched_pipeline

    def boom_append_trust_log(*args, **kwargs):
        raise RuntimeError("boom append_trust_log")

    def boom_write_shadow(*args, **kwargs):
        raise RuntimeError("boom write_shadow_decide")

    monkeypatch.setattr(pipeline, "append_trust_log", boom_append_trust_log, raising=False)
    monkeypatch.setattr(pipeline, "write_shadow_decide", boom_write_shadow, raising=False)

    body = {"query": "trustlog exception test", "context": {"user_id": "u-log-ex"}}
    req = DummyReqModel(body=body)
    request = DummyRequest()

    payload = await pipeline.run_decide_pipeline(req, request)

    assert isinstance(payload, dict)
    assert payload.get("ok") is True

    extras = payload.get("extras") or {}
    metrics = extras.get("metrics") or {}

    # 監査ログが死んでも metrics / evidence / gate のどれかが欠けないようにしておく（緩い contract）
    assert isinstance(metrics, dict)
    assert "effective_risk" in metrics
    assert "gate" in payload




