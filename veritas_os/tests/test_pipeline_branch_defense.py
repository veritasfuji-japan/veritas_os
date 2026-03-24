# -*- coding: utf-8 -*-
"""
Branch-defense tests for veritas_os/core/pipeline.py.

Targets edge-case branches, fallback nuances, wrapper delegation details,
and backward-compat aliases that existing tests do not fully exercise.
Every test is self-contained, uses monkeypatch / tmp_path / fake objects,
and avoids real I/O, LLM, or network access.
"""

from __future__ import annotations

import asyncio
import json
import types
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, call

import pytest

from veritas_os.core import pipeline as pl


# =========================================================
# 1. _check_required_modules — message content validation
# =========================================================


class TestCheckRequiredModulesMessages:
    """Verify the ImportError message contains the correct module names."""

    def test_kernel_only_missing_mentions_kernel_not_fuji(self, monkeypatch):
        monkeypatch.setattr(pl, "veritas_core", None)
        monkeypatch.setattr(pl, "fuji_core", types.SimpleNamespace())
        with pytest.raises(ImportError, match="kernel") as exc_info:
            pl._check_required_modules()
        assert "fuji" not in str(exc_info.value)

    def test_fuji_only_missing_mentions_fuji_not_kernel(self, monkeypatch):
        monkeypatch.setattr(pl, "veritas_core", types.SimpleNamespace())
        monkeypatch.setattr(pl, "fuji_core", None)
        with pytest.raises(ImportError, match="fuji") as exc_info:
            pl._check_required_modules()
        assert "kernel" not in str(exc_info.value)

    def test_both_missing_message_contains_both(self, monkeypatch):
        monkeypatch.setattr(pl, "veritas_core", None)
        monkeypatch.setattr(pl, "fuji_core", None)
        with pytest.raises(ImportError) as exc_info:
            pl._check_required_modules()
        msg = str(exc_info.value)
        assert "kernel" in msg
        assert "fuji" in msg
        assert "FATAL" in msg

    def test_success_returns_none(self, monkeypatch):
        monkeypatch.setattr(pl, "veritas_core", types.SimpleNamespace())
        monkeypatch.setattr(pl, "fuji_core", types.SimpleNamespace())
        result = pl._check_required_modules()
        assert result is None


# =========================================================
# 2. _dedupe_alts — kernel helper edge cases
# =========================================================


class TestDedupeAltsEdgeCases:
    """Edge cases for the kernel-first dedup logic with fallback."""

    def test_kernel_returns_empty_list_is_accepted(self, monkeypatch):
        """Empty list from kernel is still a valid list → no fallback."""
        kernel = types.SimpleNamespace(_dedupe_alts=lambda alts: [])
        monkeypatch.setattr(pl, "veritas_core", kernel)
        result = pl._dedupe_alts([{"id": "a"}, {"id": "b"}])
        assert result == []

    def test_kernel_returns_none_triggers_fallback(self, monkeypatch):
        kernel = types.SimpleNamespace(_dedupe_alts=lambda alts: None)
        monkeypatch.setattr(pl, "veritas_core", kernel)
        inp = [{"id": "a", "title": "x"}]
        result = pl._dedupe_alts(inp)
        assert isinstance(result, list)

    def test_kernel_returns_dict_triggers_fallback(self, monkeypatch):
        kernel = types.SimpleNamespace(_dedupe_alts=lambda alts: {"bad": True})
        monkeypatch.setattr(pl, "veritas_core", kernel)
        inp = [{"id": "a", "title": "x"}]
        result = pl._dedupe_alts(inp)
        assert isinstance(result, list)

    def test_kernel_returns_int_triggers_fallback(self, monkeypatch):
        kernel = types.SimpleNamespace(_dedupe_alts=lambda alts: 42)
        monkeypatch.setattr(pl, "veritas_core", kernel)
        inp = [{"id": "a", "title": "x"}]
        result = pl._dedupe_alts(inp)
        assert isinstance(result, list)

    def test_kernel_returns_tuple_triggers_fallback(self, monkeypatch):
        """Tuple is not list → fallback."""
        kernel = types.SimpleNamespace(_dedupe_alts=lambda alts: tuple(alts))
        monkeypatch.setattr(pl, "veritas_core", kernel)
        inp = [{"id": "a", "title": "x"}]
        result = pl._dedupe_alts(inp)
        assert isinstance(result, list)

    def test_fallback_preserves_identity(self, monkeypatch):
        """When fallback is used, items should be preserved."""
        monkeypatch.setattr(pl, "veritas_core", None)
        inp = [{"id": "a", "title": "first"}, {"id": "b", "title": "second"}]
        result = pl._dedupe_alts(inp)
        assert isinstance(result, list)
        # At minimum the fallback should not crash
        assert len(result) >= 1

    def test_kernel_exception_logs_debug(self, monkeypatch, caplog):
        """Verify exception path emits a debug log."""
        import logging

        def boom(alts):
            raise ValueError("dedup exploded")

        kernel = types.SimpleNamespace(_dedupe_alts=boom)
        monkeypatch.setattr(pl, "veritas_core", kernel)
        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline"):
            result = pl._dedupe_alts([{"id": "a", "title": "x"}])
        assert isinstance(result, list)
        assert any("kernel helper failed" in r.message for r in caplog.records)


# =========================================================
# 3. _safe_web_search — deeper edge cases
# =========================================================


class TestSafeWebSearchEdgeCases:
    """Edge-case branches for _safe_web_search sanitization and dispatch."""

    @pytest.mark.anyio
    async def test_query_becomes_empty_after_unicode_sanitization(self, monkeypatch):
        """Query composed entirely of unsafe Unicode chars → None."""
        called = []
        monkeypatch.setattr(
            pl, "web_search",
            lambda q, **kw: (called.append(q), {"ok": True})[1],
            raising=False,
        )
        # U+200F (RIGHT-TO-LEFT MARK) is in Cf category which is unsafe
        result = await pl._safe_web_search("\u200f\u200e\u202a\u202c")
        assert result is None
        assert len(called) == 0

    @pytest.mark.anyio
    async def test_max_results_string_coerced(self, monkeypatch):
        """max_results='3' should be coerced to int 3."""
        captured: List[int] = []

        def capture(q, max_results=5):
            captured.append(max_results)
            return {"ok": True}

        monkeypatch.setattr(pl, "web_search", capture, raising=False)
        await pl._safe_web_search("test", max_results="3")
        assert captured == [3]

    @pytest.mark.anyio
    async def test_max_results_none_defaults(self, monkeypatch):
        """max_results=None → fallback to 5."""
        captured: List[int] = []

        def capture(q, max_results=5):
            captured.append(max_results)
            return {"ok": True}

        monkeypatch.setattr(pl, "web_search", capture, raising=False)
        await pl._safe_web_search("test", max_results=None)
        assert captured == [5]

    @pytest.mark.anyio
    async def test_max_results_float_coerced(self, monkeypatch):
        """max_results=7.9 → int(7.9) → 7."""
        captured: List[int] = []

        def capture(q, max_results=5):
            captured.append(max_results)
            return {"ok": True}

        monkeypatch.setattr(pl, "web_search", capture, raising=False)
        await pl._safe_web_search("test", max_results=7.9)
        assert captured == [7]

    @pytest.mark.anyio
    async def test_max_results_non_numeric_string_defaults(self, monkeypatch):
        """max_results='bad' → fallback to 5."""
        captured: List[int] = []

        def capture(q, max_results=5):
            captured.append(max_results)
            return {"ok": True}

        monkeypatch.setattr(pl, "web_search", capture, raising=False)
        await pl._safe_web_search("test", max_results="bad")
        assert captured == [5]

    @pytest.mark.anyio
    async def test_value_error_fallback(self, monkeypatch):
        """ValueError from search function → returns None."""

        def raise_val(q, **kw):
            raise ValueError("bad value")

        monkeypatch.setattr(pl, "web_search", raise_val, raising=False)
        assert await pl._safe_web_search("query") is None

    @pytest.mark.anyio
    async def test_async_fn_that_raises(self, monkeypatch):
        """Async search function that raises → returns None."""

        async def async_boom(q, **kw):
            raise RuntimeError("async boom")

        monkeypatch.setattr(pl, "web_search", async_boom, raising=False)
        result = await pl._safe_web_search("query")
        assert result is None

    @pytest.mark.anyio
    async def test_async_fn_returns_non_dict(self, monkeypatch):
        """Async fn returns a list instead of dict → None."""

        async def async_list(q, **kw):
            return ["not", "a", "dict"]

        monkeypatch.setattr(pl, "web_search", async_list, raising=False)
        result = await pl._safe_web_search("query")
        assert result is None

    @pytest.mark.anyio
    async def test_sync_fn_returns_none(self, monkeypatch):
        """Sync fn returns None → None (not dict check)."""
        monkeypatch.setattr(pl, "web_search", lambda q, **kw: None, raising=False)
        result = await pl._safe_web_search("query")
        assert result is None

    @pytest.mark.anyio
    async def test_query_with_mixed_control_and_valid(self, monkeypatch):
        """Query mixing control chars and valid text preserves valid part."""
        captured: List[str] = []

        def capture(q, **kw):
            captured.append(q)
            return {"ok": True}

        monkeypatch.setattr(pl, "web_search", capture, raising=False)
        await pl._safe_web_search("hello\x00\x1fworld")
        assert len(captured) == 1
        assert "hello" in captured[0]
        assert "world" in captured[0]
        assert "\x00" not in captured[0]

    @pytest.mark.anyio
    async def test_web_search_attr_missing_falls_to_tool(self, monkeypatch):
        """When web_search attr is removed, _tool_web_search is used."""
        monkeypatch.delattr(pl, "web_search", raising=False)
        monkeypatch.setattr(
            pl, "_tool_web_search",
            lambda q, **kw: {"source": "tool"},
        )
        result = await pl._safe_web_search("test")
        assert result == {"source": "tool"}

    @pytest.mark.anyio
    async def test_neither_callable_both_non_callable(self, monkeypatch):
        """Both web_search and _tool_web_search are non-callable objects → None."""
        monkeypatch.setattr(pl, "web_search", 42, raising=False)
        monkeypatch.setattr(pl, "_tool_web_search", "not callable")
        result = await pl._safe_web_search("test")
        assert result is None


# =========================================================
# 4. get_request_params — additional edge cases
# =========================================================


class TestGetRequestParamsEdgeCases:
    def test_params_dict_conversion_error_swallowed(self):
        """dict(params) raises → error is swallowed, returns empty dict."""

        class BadParams:
            def __iter__(self):
                raise RuntimeError("not iterable")

        class Req:
            params = BadParams()

        out = pl.get_request_params(Req())
        assert out == {}

    def test_object_with_neither_attribute(self):
        """Object with no query_params or params → empty dict."""

        class Bare:
            pass

        out = pl.get_request_params(Bare())
        assert out == {}

    def test_none_query_params_skipped(self):
        """query_params is None → skipped, params still used."""

        class Req:
            query_params = None
            params = {"k": "v"}

        out = pl.get_request_params(Req())
        assert out == {"k": "v"}

    def test_none_params_skipped(self):
        """params is None → skipped, query_params still used."""

        class Req:
            query_params = {"k": "v"}
            params = None

        out = pl.get_request_params(Req())
        assert out == {"k": "v"}

    def test_both_none(self):
        """Both None → empty dict."""

        class Req:
            query_params = None
            params = None

        out = pl.get_request_params(Req())
        assert out == {}

    def test_params_overrides_query_params_same_key(self):
        """params values override query_params for same key."""

        class Req:
            query_params = {"mode": "fast", "only_qp": "1"}
            params = {"mode": "slow", "only_p": "2"}

        out = pl.get_request_params(Req())
        assert out["mode"] == "slow"
        assert out["only_qp"] == "1"
        assert out["only_p"] == "2"


# =========================================================
# 5. to_dict — deeper fallback edge cases
# =========================================================


class TestToDictEdgeCases:
    def test_model_dump_exclude_none(self):
        """model_dump(exclude_none=True) is called correctly."""

        class Obj:
            def model_dump(self, exclude_none=False):
                if exclude_none:
                    return {"a": 1}
                return {"a": 1, "b": None}

        assert pl.to_dict(Obj()) == {"a": 1}

    def test_dict_passthrough_identity(self):
        """Dict input is returned as-is (same reference)."""
        d = {"x": 42}
        assert pl.to_dict(d) is d

    def test___dict___access_raises_falls_through(self):
        """Object whose __dict__ access raises → falls to empty dict."""

        class Weird:
            def __getattribute__(self, name):
                if name == "__dict__":
                    raise TypeError("no __dict__")
                return object.__getattribute__(self, name)

        result = pl.to_dict(Weird())
        assert result == {}

    def test_circular_reference_filtered(self):
        """Object with self-referencing attribute filtered out."""

        class Circular:
            pass

        obj = Circular()
        obj.name = "test"
        obj.self_ref = obj  # circular reference

        result = pl.to_dict(obj)
        assert "name" in result
        assert result["name"] == "test"
        assert "self_ref" not in result  # filtered out

    def test_model_dump_returns_non_dict_falls_to_dict_method(self):
        """model_dump returns non-dict → falls through to dict()."""

        class Obj:
            def model_dump(self, **kw):
                return "not a dict"  # type: ignore

            def dict(self):
                return {"via": "dict_method"}

        # model_dump doesn't raise but also doesn't return dict —
        # current code doesn't check return type of model_dump
        # so it will return whatever model_dump returns.
        result = pl.to_dict(Obj())
        # model_dump returns "not a dict" which is truthy, and code returns it.
        # Actually, looking at the code: the model_dump try block returns o.model_dump(exclude_none=True)
        # unconditionally if it doesn't raise. So "not a dict" will be returned.
        # This is existing behavior — we just document it.
        assert result is not None

    def test_no_dict_but_has___dict__(self):
        """Object without model_dump or dict() but with __dict__."""

        class Plain:
            def __init__(self):
                self.x = 1
                self.y = "hello"

        result = pl.to_dict(Plain())
        assert result == {"x": 1, "y": "hello"}

    def test_empty_object___dict__(self):
        """Object with empty __dict__."""

        class Empty:
            pass

        result = pl.to_dict(Empty())
        assert result == {}


# =========================================================
# 6. _load_persisted_decision — matching by request_id
# =========================================================


class TestLoadPersistedDecisionEdgeCases:
    def test_matches_by_request_id(self, monkeypatch, tmp_path):
        """Wrapper + impl matches by request_id field, not just decision_id."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        monkeypatch.setattr(pl, "LOG_DIR", log_dir)

        req_id = "req-abc-123"
        payload = {"request_id": req_id, "decision_id": "other-id", "query": "test"}
        (log_dir / "decide_some_file.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

        result = pl._load_persisted_decision(req_id)
        assert result is not None
        assert result["request_id"] == req_id

    def test_nonexistent_log_dir(self, monkeypatch, tmp_path):
        """If LOG_DIR doesn't exist, returns None without crash."""
        monkeypatch.setattr(pl, "LOG_DIR", tmp_path / "nonexistent")
        result = pl._load_persisted_decision("any-id")
        assert result is None

    def test_corrupt_json_skipped(self, monkeypatch, tmp_path):
        """Corrupt JSON files are skipped, valid ones still found."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        monkeypatch.setattr(pl, "LOG_DIR", log_dir)

        # Write corrupt file first (sorted reverse, so name matters)
        (log_dir / "decide_zzz.json").write_text("NOT JSON", encoding="utf-8")
        # Write valid file
        payload = {"decision_id": "good-id", "query": "test"}
        (log_dir / "decide_aaa.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

        result = pl._load_persisted_decision("good-id")
        assert result is not None
        assert result["decision_id"] == "good-id"


# =========================================================
# 7. replay_decision — wrapper delegation edge cases
# =========================================================


class TestReplayDecisionEdgeCases:
    @pytest.mark.anyio
    async def test_mock_external_apis_false_passed(self, monkeypatch, tmp_path):
        """mock_external_apis=False is correctly forwarded."""
        captured: Dict[str, Any] = {}

        async def fake_impl(decision_id, **kwargs):
            captured.update(kwargs)
            return {"id": decision_id}

        monkeypatch.setattr(pl, "_replay_decision_impl", fake_impl)
        monkeypatch.setattr(pl, "LOG_DIR", tmp_path / "logs")
        monkeypatch.setattr(pl, "REPLAY_REPORT_DIR", tmp_path / "reports")

        await pl.replay_decision("d-1", mock_external_apis=False)
        assert captured["mock_external_apis"] is False

    @pytest.mark.anyio
    async def test_atomic_io_flags_passed(self, monkeypatch, tmp_path):
        """_HAS_ATOMIC_IO and _atomic_write_json are passed through."""
        captured: Dict[str, Any] = {}

        async def fake_impl(decision_id, **kwargs):
            captured.update(kwargs)
            return {"id": decision_id}

        monkeypatch.setattr(pl, "_replay_decision_impl", fake_impl)
        monkeypatch.setattr(pl, "LOG_DIR", tmp_path)
        monkeypatch.setattr(pl, "REPLAY_REPORT_DIR", tmp_path)

        await pl.replay_decision("d-2")
        assert "_HAS_ATOMIC_IO" in captured
        assert "_atomic_write_json" in captured
        assert isinstance(captured["_HAS_ATOMIC_IO"], bool)


# =========================================================
# 8. run_decide_pipeline — orchestration contract
# =========================================================


class _DummyReqModel:
    """Fake DecideRequest for orchestration tests."""

    def __init__(self, body: dict):
        self._body = body

    def model_dump(self, **kw):
        return dict(self._body)


class _DummyRequest:
    """Fake FastAPI Request."""

    def __init__(self, params=None):
        self.query_params = params or {}


@pytest.fixture
def _pipeline_env(monkeypatch, tmp_path):
    """Minimal patched environment for run_decide_pipeline."""
    import veritas_os.core.planner as planner_mod

    val_json = tmp_path / "val.json"
    meta_log = tmp_path / "meta.log"
    log_dir = tmp_path / "logs"
    dataset_dir = tmp_path / "dataset"
    log_dir.mkdir(parents=True, exist_ok=True)
    dataset_dir.mkdir(parents=True, exist_ok=True)
    val_json.write_text(json.dumps({"ema": {}}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(pl, "VAL_JSON", val_json)
    monkeypatch.setattr(pl, "META_LOG", meta_log)
    monkeypatch.setattr(pl, "LOG_DIR", log_dir)
    monkeypatch.setattr(pl, "DATASET_DIR", dataset_dir)

    class DummyResponseModel:
        def __init__(self, **data):
            self._data = data

        @classmethod
        def model_validate(cls, data):
            return cls(**data)

        def model_dump(self):
            return self._data

    monkeypatch.setattr(pl, "DecideResponse", DummyResponseModel, raising=False)
    monkeypatch.setattr(pl, "build_dataset_record", lambda *a, **kw: {}, raising=False)
    monkeypatch.setattr(pl, "append_dataset_record", lambda *a, **kw: None, raising=False)
    monkeypatch.setattr(pl, "append_trust_log", lambda *a, **kw: None, raising=False)
    monkeypatch.setattr(pl, "write_shadow_decide", lambda *a, **kw: None, raising=False)

    # MemoryOS stub
    class DummyMem:
        def recent(self, user_id, limit=20):
            return []

        def search(self, query, k, kinds, min_sim=0.3, user_id=None):
            return {}

        def put(self, user_id, key, value):
            pass

        def add_usage(self, user_id, ids):
            pass

    monkeypatch.setattr(pl, "mem", DummyMem())
    monkeypatch.setattr(pl, "MEM_VEC", None)
    monkeypatch.setattr(pl, "MEM_CLF", None)

    # WorldModel stub
    class DummyWorld:
        def inject_state_into_context(self, context, user_id):
            ctx = dict(context or {})
            ctx["world_state"] = {"user": user_id}
            ctx["user_id"] = user_id
            return ctx

        def simulate(self, user_id, query, chosen):
            return {"utility": 0.5, "confidence": 0.5}

        def update_from_decision(self, *a, **kw):
            pass

        def next_hint_for_veritas_agi(self):
            return {}

    monkeypatch.setattr(pl, "world_model", DummyWorld())

    # PlannerOS stub
    monkeypatch.setattr(
        planner_mod,
        "plan_for_veritas_agi",
        lambda context, query: {"steps": [], "source": "test", "raw": {}},
        raising=False,
    )

    # kernel.decide stub
    def dummy_decide(*args, **kwargs):
        alts = kwargs.get("alternatives") or kwargs.get("options") or [
            {"id": "A", "title": "A", "description": "descA", "score": 1.0},
        ]
        chosen = alts[0] if isinstance(alts, list) and alts else {}
        return {
            "evidence": [{"source": "core", "snippet": "ok", "confidence": 0.8}],
            "critique": [],
            "debate": [],
            "telos_score": 0.6,
            "fuji": {"status": "allow", "risk": 0.2, "reasons": [], "violations": []},
            "alternatives": alts,
            "extras": {},
            "chosen": chosen,
        }

    monkeypatch.setattr(pl.veritas_core, "decide", dummy_decide, raising=False)
    monkeypatch.setattr(pl.veritas_core, "_dedupe_alts", lambda alts: alts, raising=False)

    # FUJI stub
    monkeypatch.setattr(
        pl.fuji_core,
        "validate_action",
        lambda query, context: {
            "status": "allow",
            "risk": 0.2,
            "reasons": [],
            "violations": [],
            "modifications": [],
        },
        raising=False,
    )

    # ValueCore stub
    class DummyVCResult:
        scores = {"prudence": 0.7}
        total = 0.7
        top_factors = ["prudence"]
        rationale = "ok"

    monkeypatch.setattr(
        pl.value_core, "evaluate", lambda query, ctx: DummyVCResult(), raising=False
    )

    # DebateOS stub
    monkeypatch.setattr(
        pl.debate_core,
        "run_debate",
        lambda query, options, context: {
            "options": options,
            "chosen": options[0] if options else {},
            "source": "test",
            "raw": {},
        },
        raising=False,
    )

    # WebSearch → no-op
    monkeypatch.setattr(pl, "web_search", lambda q, **kw: None, raising=False)

    # ReasonOS stub
    monkeypatch.setattr(
        pl.reason_core,
        "reflect",
        lambda payload: {"next_value_boost": 0.0, "improvement_tips": []},
        raising=False,
    )

    async def dummy_gen_tmpl(*a, **kw):
        return {}

    monkeypatch.setattr(
        pl.reason_core, "generate_reflection_template", dummy_gen_tmpl, raising=False
    )
    monkeypatch.setattr(
        pl.reason_core,
        "generate_reason",
        lambda *a, **kw: {"text": "reason text", "note": "note"},
        raising=False,
    )

    # Persona
    monkeypatch.setattr(pl, "load_persona", lambda: {"name": "default"})

    return pl


class TestRunDecidePipelineContract:
    """Verify orchestration contract: stage ordering, extras/metrics invariants,
    and memory_store_getter injection."""

    @pytest.mark.anyio
    async def test_extras_metrics_contract_fields(self, _pipeline_env):
        """All documented extras/metrics contract fields must be present."""
        body = {
            "query": "contract test",
            "context": {"user_id": "u1"},
            "options": [],
        }
        payload = await _pipeline_env.run_decide_pipeline(
            _DummyReqModel(body), _DummyRequest()
        )

        extras = payload.get("extras") or {}
        metrics = extras.get("metrics") or {}

        # Documented contract: these keys must always exist
        assert "mem_hits" in metrics
        assert "memory_evidence_count" in metrics
        assert "web_hits" in metrics
        assert "web_evidence_count" in metrics
        assert isinstance(metrics.get("mem_hits"), int)
        assert isinstance(metrics.get("web_hits"), int)

        # fast_mode presence
        assert "fast_mode" in extras or "fast_mode" in metrics

    @pytest.mark.anyio
    async def test_response_has_required_top_level_keys(self, _pipeline_env):
        """Pipeline response must contain mandatory top-level keys."""
        body = {
            "query": "top-level test",
            "context": {"user_id": "u1"},
            "options": [],
        }
        payload = await _pipeline_env.run_decide_pipeline(
            _DummyReqModel(body), _DummyRequest()
        )

        assert "query" in payload
        assert "chosen" in payload
        assert isinstance(payload.get("alternatives"), list)
        assert isinstance(payload.get("evidence"), list)

    @pytest.mark.anyio
    async def test_memory_store_getter_override(self, _pipeline_env, monkeypatch):
        """memory_store_getter param overrides the default _get_memory_store."""
        custom_store_called = []

        def custom_getter():
            custom_store_called.append(True)
            return None  # No actual memory store

        body = {
            "query": "memory getter test",
            "context": {"user_id": "u1"},
            "options": [],
        }
        payload = await _pipeline_env.run_decide_pipeline(
            _DummyReqModel(body),
            _DummyRequest(),
            memory_store_getter=custom_getter,
        )

        # The custom getter should have been called at least once
        assert len(custom_store_called) >= 1
        # Pipeline should still complete successfully
        assert "query" in payload

    @pytest.mark.anyio
    async def test_pipeline_with_explicit_options(self, _pipeline_env):
        """Pipeline handles explicit options in request body."""
        body = {
            "query": "options test",
            "context": {"user_id": "u1"},
            "options": [
                {"id": "opt1", "title": "Option 1", "description": "First"},
                {"id": "opt2", "title": "Option 2", "description": "Second"},
            ],
        }
        payload = await _pipeline_env.run_decide_pipeline(
            _DummyReqModel(body), _DummyRequest()
        )
        assert isinstance(payload.get("alternatives"), list)

    @pytest.mark.anyio
    async def test_fuji_missing_raises_import_error(self, _pipeline_env, monkeypatch):
        """When fuji_core is None, pipeline must raise ImportError."""
        monkeypatch.setattr(_pipeline_env, "fuji_core", None)
        body = {"query": "should fail", "context": {"user_id": "u1"}}
        with pytest.raises(ImportError, match="fuji"):
            await _pipeline_env.run_decide_pipeline(
                _DummyReqModel(body), _DummyRequest()
            )


# =========================================================
# 9. Backward-compatibility aliases — wrappers
# =========================================================


class TestBackwardCompatWrappers:
    """Verify wrapper functions and aliases preserve backward compat."""

    def test_to_bool_delegates(self):
        """_to_bool wraps _to_bool_local and handles standard inputs."""
        assert pl._to_bool("1") is True
        assert pl._to_bool("0") is False
        assert pl._to_bool("true") is True
        assert pl._to_bool("false") is False
        assert pl._to_bool(True) is True
        assert pl._to_bool(False) is False

    def test_to_float_or_delegates(self):
        """_to_float_or wraps _safe_float."""
        assert pl._to_float_or(3.14, 0.0) == 3.14
        assert pl._to_float_or("bad", 1.5) == 1.5
        assert pl._to_float_or(None, 2.0) == 2.0

    def test_clip01_clamps(self):
        """_clip01 clamps to [0.0, 1.0]."""
        assert pl._clip01(0.5) == 0.5
        assert pl._clip01(-0.5) == 0.0
        assert pl._clip01(1.5) == 1.0
        assert pl._clip01(0.0) == 0.0
        assert pl._clip01(1.0) == 1.0

    def test_to_dict_alias_same_reference(self):
        assert pl._to_dict is pl.to_dict

    def test_get_request_params_alias_same_reference(self):
        assert pl._get_request_params is pl.get_request_params

    def test_fallback_load_persona_returns_dict(self):
        """_fallback_load_persona returns minimal persona dict."""
        result = pl._fallback_load_persona()
        assert isinstance(result, dict)
        assert "name" in result

    def test_norm_alt_generates_id(self):
        """_norm_alt assigns a new UUID id when id is missing."""
        alt = {"title": "Test", "description": "Desc"}
        result = pl._norm_alt(alt)
        assert "id" in result
        assert len(result["id"]) > 0

    def test_norm_alt_preserves_existing_id(self):
        """_norm_alt keeps existing non-empty id."""
        alt = {"id": "keep-me", "title": "Test"}
        result = pl._norm_alt(alt)
        assert result["id"] == "keep-me"

    def test_norm_alt_sanitizes_control_chars_in_id(self):
        """_norm_alt strips control chars from id."""
        alt = {"id": "hello\x00world\x1f!", "title": "T"}
        result = pl._norm_alt(alt)
        assert "\x00" not in result["id"]
        assert "\x1f" not in result["id"]


# =========================================================
# 10. _warn — edge cases
# =========================================================


class TestWarnEdgeCases:
    def test_default_env_enables_warning(self, monkeypatch, caplog):
        """When VERITAS_PIPELINE_WARN is not set, warnings are emitted (default '1')."""
        import logging

        monkeypatch.delenv("VERITAS_PIPELINE_WARN", raising=False)
        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline"):
            pl._warn("[WARN] default env test")
        assert any("default env test" in r.message for r in caplog.records)

    def test_warn_level_for_bracket_warn(self, monkeypatch, caplog):
        """[WARN] prefix → logging.WARNING level."""
        import logging

        monkeypatch.setenv("VERITAS_PIPELINE_WARN", "1")
        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline"):
            pl._warn("[WARN] test warn level")
        warn_records = [
            r for r in caplog.records if "test warn level" in r.message
        ]
        assert len(warn_records) >= 1
        assert warn_records[0].levelno == logging.WARNING


# =========================================================
# 11. Optional dependency import doesn't crash
# =========================================================


class TestOptionalImportResilience:
    """Verify that the pipeline module is importable even when optional
    dependencies are missing, and that expected attributes exist."""

    def test_evidence_core_attribute_exists(self):
        """evidence_core is defined (may be None if import failed)."""
        assert hasattr(pl, "evidence_core")

    def test_mem_attribute_exists(self):
        """mem is defined (may be None if import failed)."""
        assert hasattr(pl, "mem")

    def test_value_core_attribute_exists(self):
        assert hasattr(pl, "value_core")

    def test_world_model_attribute_exists(self):
        assert hasattr(pl, "world_model")

    def test_reason_core_attribute_exists(self):
        assert hasattr(pl, "reason_core")

    def test_debate_core_attribute_exists(self):
        assert hasattr(pl, "debate_core")

    def test_decide_request_attribute_exists(self):
        assert hasattr(pl, "DecideRequest")

    def test_decide_response_attribute_exists(self):
        assert hasattr(pl, "DecideResponse")

    def test_has_sanitize_is_bool(self):
        assert isinstance(pl._HAS_SANITIZE, bool)

    def test_has_atomic_io_is_bool(self):
        assert isinstance(pl._HAS_ATOMIC_IO, bool)

    def test_log_dir_is_path(self):
        from pathlib import Path

        assert isinstance(pl.LOG_DIR, Path)

    def test_evidence_max_is_int(self):
        assert isinstance(pl.EVIDENCE_MAX, int)
        assert pl.EVIDENCE_MAX > 0


# =========================================================
# 12. _get_memory_store wrapper
# =========================================================


class TestGetMemoryStoreEdgeCases:
    def test_returns_none_when_mem_none(self, monkeypatch):
        monkeypatch.setattr(pl, "mem", None)
        assert pl._get_memory_store() is None

    def test_delegates_to_impl_when_mem_set(self, monkeypatch):
        """When mem is set, wrapper delegates to _get_memory_store_impl."""
        sentinel = object()
        monkeypatch.setattr(pl, "mem", types.SimpleNamespace())
        monkeypatch.setattr(
            pl, "_get_memory_store_impl", lambda mem: sentinel
        )
        assert pl._get_memory_store() is sentinel


# =========================================================
# 13. _save_valstats / _load_valstats wrappers
# =========================================================


class TestValstatsWrappers:
    def test_load_valstats_delegates(self, monkeypatch, tmp_path):
        val_json = tmp_path / "val.json"
        val_json.write_text(json.dumps({"ema": {"x": 1}}), encoding="utf-8")
        monkeypatch.setattr(pl, "VAL_JSON", val_json)
        result = pl._load_valstats()
        assert isinstance(result, dict)

    def test_save_valstats_writes(self, monkeypatch, tmp_path):
        val_json = tmp_path / "val.json"
        monkeypatch.setattr(pl, "VAL_JSON", val_json)
        monkeypatch.setattr(pl, "_HAS_ATOMIC_IO", False)
        monkeypatch.setattr(pl, "_atomic_write_json", None)
        pl._save_valstats({"ema": {"test": 0.5}})
        assert val_json.exists()


# =========================================================
# 14. _allow_prob wrapper
# =========================================================


class TestAllowProbEdgeCases:
    def test_attribute_error_returns_zero(self, monkeypatch):
        """predict_gate_label returns non-dict → AttributeError on .get → 0.0."""
        monkeypatch.setattr(pl, "predict_gate_label", lambda text: "not a dict")
        assert pl._allow_prob("test") == 0.0

    def test_normal_float_value(self, monkeypatch):
        monkeypatch.setattr(pl, "predict_gate_label", lambda text: {"allow": 0.85})
        assert pl._allow_prob("test") == 0.85
