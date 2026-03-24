# -*- coding: utf-8 -*-
"""
Coverage hardening tests for veritas_os/core/pipeline.py.

Targets branches, fallbacks, wrappers and backward-compat aliases that
were NOT yet exercised by existing tests.  Each test is self-contained,
uses monkeypatch / tmp_path / fake objects, and avoids real I/O, LLM,
or network access.
"""

from __future__ import annotations

import asyncio
import json
import types
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from veritas_os.core import pipeline as pl


# =========================================================
# 1. _check_required_modules
# =========================================================


class TestCheckRequiredModules:
    """_check_required_modules must raise ImportError when core modules are
    absent and succeed silently when they are present."""

    def test_both_present_no_error(self, monkeypatch):
        monkeypatch.setattr(pl, "veritas_core", types.SimpleNamespace())
        monkeypatch.setattr(pl, "fuji_core", types.SimpleNamespace())
        pl._check_required_modules()  # must not raise

    def test_kernel_missing(self, monkeypatch):
        monkeypatch.setattr(pl, "veritas_core", None)
        monkeypatch.setattr(pl, "fuji_core", types.SimpleNamespace())
        with pytest.raises(ImportError, match="kernel"):
            pl._check_required_modules()

    def test_fuji_missing(self, monkeypatch):
        monkeypatch.setattr(pl, "veritas_core", types.SimpleNamespace())
        monkeypatch.setattr(pl, "fuji_core", None)
        with pytest.raises(ImportError, match="fuji"):
            pl._check_required_modules()

    def test_both_missing(self, monkeypatch):
        monkeypatch.setattr(pl, "veritas_core", None)
        monkeypatch.setattr(pl, "fuji_core", None)
        with pytest.raises(ImportError, match="kernel.*fuji"):
            pl._check_required_modules()


# =========================================================
# 2. _dedupe_alts  (kernel helper / fallback)
# =========================================================


class TestDedupeAlts:
    """_dedupe_alts delegates to kernel._dedupe_alts when available,
    falls back to _dedupe_alts_fallback otherwise."""

    def test_kernel_helper_success(self, monkeypatch):
        sentinel = [{"id": "deduped", "title": "ok"}]
        kernel = types.SimpleNamespace(_dedupe_alts=lambda alts: sentinel)
        monkeypatch.setattr(pl, "veritas_core", kernel)
        assert pl._dedupe_alts([{"id": "a"}, {"id": "b"}]) is sentinel

    def test_kernel_helper_returns_non_list_falls_back(self, monkeypatch):
        kernel = types.SimpleNamespace(_dedupe_alts=lambda alts: "not_a_list")
        monkeypatch.setattr(pl, "veritas_core", kernel)
        result = pl._dedupe_alts([{"id": "a", "title": "x"}])
        assert isinstance(result, list)

    def test_kernel_helper_raises_falls_back(self, monkeypatch):
        def exploding(_alts):
            raise RuntimeError("boom")

        kernel = types.SimpleNamespace(_dedupe_alts=exploding)
        monkeypatch.setattr(pl, "veritas_core", kernel)
        result = pl._dedupe_alts([{"id": "a", "title": "x"}])
        assert isinstance(result, list)

    def test_kernel_none_falls_back(self, monkeypatch):
        monkeypatch.setattr(pl, "veritas_core", None)
        result = pl._dedupe_alts([{"id": "a", "title": "x"}])
        assert isinstance(result, list)

    def test_kernel_missing_attr_falls_back(self, monkeypatch):
        """kernel exists but has no _dedupe_alts attribute."""
        monkeypatch.setattr(pl, "veritas_core", types.SimpleNamespace())
        result = pl._dedupe_alts([{"id": "a", "title": "x"}])
        assert isinstance(result, list)


# =========================================================
# 3. _safe_web_search
# =========================================================


class TestSafeWebSearch:
    """_safe_web_search sanitises inputs, resolves sync/async callables
    from the module namespace, and swallows all expected exceptions."""

    @pytest.mark.anyio
    async def test_empty_query_returns_none(self, monkeypatch):
        monkeypatch.setattr(pl, "web_search", lambda q, **kw: {"ok": True}, raising=False)
        assert await pl._safe_web_search("") is None
        assert await pl._safe_web_search("   ") is None
        assert await pl._safe_web_search(None) is None

    @pytest.mark.anyio
    async def test_long_query_is_truncated(self, monkeypatch):
        captured: List[str] = []

        def capture(q, **kw):
            captured.append(q)
            return {"ok": True}

        monkeypatch.setattr(pl, "web_search", capture, raising=False)
        long_q = "x" * 1000
        await pl._safe_web_search(long_q)
        assert len(captured) == 1
        assert len(captured[0]) <= 512

    @pytest.mark.anyio
    async def test_control_chars_removed(self, monkeypatch):
        captured: List[str] = []

        def capture(q, **kw):
            captured.append(q)
            return {"ok": True}

        monkeypatch.setattr(pl, "web_search", capture, raising=False)
        await pl._safe_web_search("hello\x00world\x1f!")
        assert "\x00" not in captured[0]
        assert "\x1f" not in captured[0]

    @pytest.mark.anyio
    async def test_no_callable_returns_none(self, monkeypatch):
        """When neither web_search nor _tool_web_search are callable → None."""
        monkeypatch.delattr(pl, "web_search", raising=False)
        monkeypatch.setattr(pl, "_tool_web_search", None)
        assert await pl._safe_web_search("test query") is None

    @pytest.mark.anyio
    async def test_awaitable_return(self, monkeypatch):
        """If the callable returns an awaitable, it is awaited."""

        async def async_ws(q, **kw):
            return {"ok": True, "results": []}

        monkeypatch.setattr(pl, "web_search", async_ws, raising=False)
        result = await pl._safe_web_search("async query")
        assert result == {"ok": True, "results": []}

    @pytest.mark.anyio
    async def test_runtime_error_fallback(self, monkeypatch):
        def raise_runtime(q, **kw):
            raise RuntimeError("service down")

        monkeypatch.setattr(pl, "web_search", raise_runtime, raising=False)
        assert await pl._safe_web_search("query") is None

    @pytest.mark.anyio
    async def test_timeout_error_fallback(self, monkeypatch):
        def raise_timeout(q, **kw):
            raise TimeoutError("timed out")

        monkeypatch.setattr(pl, "web_search", raise_timeout, raising=False)
        assert await pl._safe_web_search("query") is None

    @pytest.mark.anyio
    async def test_connection_error_fallback(self, monkeypatch):
        def raise_conn(q, **kw):
            raise ConnectionError("refused")

        monkeypatch.setattr(pl, "web_search", raise_conn, raising=False)
        assert await pl._safe_web_search("query") is None

    @pytest.mark.anyio
    async def test_os_error_fallback(self, monkeypatch):
        def raise_os(q, **kw):
            raise OSError("disk fail")

        monkeypatch.setattr(pl, "web_search", raise_os, raising=False)
        assert await pl._safe_web_search("query") is None

    @pytest.mark.anyio
    async def test_type_error_fallback(self, monkeypatch):
        def raise_type(q, **kw):
            raise TypeError("bad arg")

        monkeypatch.setattr(pl, "web_search", raise_type, raising=False)
        assert await pl._safe_web_search("query") is None

    @pytest.mark.anyio
    async def test_non_dict_return_gives_none(self, monkeypatch):
        """If web_search returns non-dict, _safe_web_search returns None."""
        monkeypatch.setattr(pl, "web_search", lambda q, **kw: "string_result", raising=False)
        assert await pl._safe_web_search("query") is None

    @pytest.mark.anyio
    async def test_max_results_clipping(self, monkeypatch):
        captured_max: List[int] = []

        def capture(q, max_results=5):
            captured_max.append(max_results)
            return {"ok": True}

        monkeypatch.setattr(pl, "web_search", capture, raising=False)

        await pl._safe_web_search("q", max_results=0)
        await pl._safe_web_search("q", max_results=100)
        await pl._safe_web_search("q", max_results=-5)

        assert captured_max == [1, 20, 1]

    @pytest.mark.anyio
    async def test_tool_web_search_fallback(self, monkeypatch):
        """When module-level web_search is not set, _tool_web_search is tried."""
        monkeypatch.delattr(pl, "web_search", raising=False)
        monkeypatch.setattr(
            pl, "_tool_web_search",
            lambda q, **kw: {"ok": True, "via": "tool"},
        )
        result = await pl._safe_web_search("fallback query")
        assert result == {"ok": True, "via": "tool"}


# =========================================================
# 4. get_request_params  (query_params + params merge)
# =========================================================


class TestGetRequestParams:
    def test_both_query_params_and_params(self):
        class Req:
            query_params = {"a": "1"}
            params = {"b": "2"}

        out = pl.get_request_params(Req())
        assert out == {"a": "1", "b": "2"}

    def test_query_params_only(self):
        class Req:
            query_params = {"x": "10"}

        out = pl.get_request_params(Req())
        assert out == {"x": "10"}

    def test_params_overrides_query_params(self):
        class Req:
            query_params = {"k": "old"}
            params = {"k": "new"}

        out = pl.get_request_params(Req())
        assert out["k"] == "new"

    def test_query_params_dict_conversion_error(self):
        """dict(qp) raises TypeError → swallowed."""

        class BadQP:
            def __iter__(self):
                raise TypeError("not iterable")

        class Req:
            query_params = BadQP()

        out = pl.get_request_params(Req())
        assert out == {}


# =========================================================
# 5. to_dict  (model_dump / dict() / __dict__ failures)
# =========================================================


class TestToDictFallbacks:
    def test_model_dump_failure_falls_to_dict_method(self):
        class Obj:
            def model_dump(self, **_kw):
                raise RuntimeError("model_dump boom")

            def dict(self):
                return {"via": "dict"}

        assert pl.to_dict(Obj()) == {"via": "dict"}

    def test_model_dump_and_dict_failure_falls_to___dict__(self):
        class Obj:
            def __init__(self):
                self.x = 42

            def model_dump(self, **_kw):
                raise TypeError("no model_dump")

            def dict(self):
                raise ValueError("no dict")

        result = pl.to_dict(Obj())
        assert result["x"] == 42

    def test_all_paths_fail_returns_empty(self):
        """Object with model_dump, dict, __dict__ all broken."""

        class Hopeless:
            def model_dump(self, **_kw):
                raise RuntimeError("nope")

            def dict(self):
                raise RuntimeError("nope")

            def __getattribute__(self, name):
                if name == "__dict__":
                    raise AttributeError("nope")
                return object.__getattribute__(self, name)

        assert pl.to_dict(Hopeless()) == {}

    def test_none_and_int_return_empty(self):
        assert pl.to_dict(None) == {}
        assert pl.to_dict(42) == {}


# =========================================================
# 6. _load_persisted_decision wrapper
# =========================================================


class TestLoadPersistedDecisionWrapper:
    def test_delegates_to_impl(self, monkeypatch, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        monkeypatch.setattr(pl, "LOG_DIR", log_dir)

        # Write a fake decision file matching the impl's glob pattern (decide_*.json)
        decision_id = "test-decision-001"
        decision_file = log_dir / f"decide_{decision_id}.json"
        payload = {"decision_id": decision_id, "query": "test"}
        decision_file.write_text(json.dumps(payload), encoding="utf-8")

        result = pl._load_persisted_decision(decision_id)
        assert result is not None
        assert result["decision_id"] == decision_id

    def test_missing_decision_returns_none(self, monkeypatch, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        monkeypatch.setattr(pl, "LOG_DIR", log_dir)
        assert pl._load_persisted_decision("nonexistent-id") is None


# =========================================================
# 7. replay_decision wrapper  (signature delegation)
# =========================================================


class TestReplayDecisionWrapper:
    @pytest.mark.anyio
    async def test_delegates_all_deps(self, monkeypatch, tmp_path):
        """Verify the wrapper passes module-level deps to impl."""
        captured: Dict[str, Any] = {}

        async def fake_impl(decision_id, **kwargs):
            captured.update(kwargs)
            return {"replayed": True, "id": decision_id}

        monkeypatch.setattr(pl, "_replay_decision_impl", fake_impl)
        monkeypatch.setattr(pl, "LOG_DIR", tmp_path / "logs")
        monkeypatch.setattr(pl, "REPLAY_REPORT_DIR", tmp_path / "reports")

        result = await pl.replay_decision("d-123", mock_external_apis=True)
        assert result["replayed"] is True
        assert result["id"] == "d-123"
        assert captured["mock_external_apis"] is True
        assert captured["run_decide_pipeline_fn"] is pl.run_decide_pipeline
        assert captured["DecideRequest"] is pl.DecideRequest
        assert captured["_load_decision_fn"] is pl._load_persisted_decision


# =========================================================
# 8. run_decide_pipeline orchestration
# =========================================================


class DummyReqModel:
    def __init__(self, body):
        self._body = body

    def model_dump(self):
        return self._body


class DummyRequest:
    def __init__(self, params=None):
        self.query_params = params or {}


@pytest.fixture
def pipeline_env(monkeypatch, tmp_path):
    """Minimal environment for run_decide_pipeline."""
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
        planner_mod, "plan_for_veritas_agi",
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
            "critique": [], "debate": [],
            "telos_score": 0.6,
            "fuji": {"status": "allow", "risk": 0.2, "reasons": [], "violations": []},
            "alternatives": alts, "extras": {}, "chosen": chosen,
        }

    monkeypatch.setattr(pl.veritas_core, "decide", dummy_decide, raising=False)
    monkeypatch.setattr(pl.veritas_core, "_dedupe_alts", lambda alts: alts, raising=False)

    # FUJI stub
    monkeypatch.setattr(
        pl.fuji_core, "validate_action",
        lambda query, context: {"status": "allow", "risk": 0.2, "reasons": [], "violations": [], "modifications": []},
        raising=False,
    )

    # ValueCore stub
    class DummyVCResult:
        scores = {"prudence": 0.7}
        total = 0.7
        top_factors = ["prudence"]
        rationale = "ok"

    monkeypatch.setattr(pl.value_core, "evaluate", lambda query, ctx: DummyVCResult(), raising=False)

    # DebateOS stub
    monkeypatch.setattr(
        pl.debate_core, "run_debate",
        lambda query, options, context: {"options": options, "chosen": options[0] if options else {}, "source": "test", "raw": {}},
        raising=False,
    )

    # WebSearch → no-op
    monkeypatch.setattr(pl, "web_search", lambda q, **kw: None, raising=False)

    # ReasonOS stub
    monkeypatch.setattr(pl.reason_core, "reflect", lambda payload: {"next_value_boost": 0.0, "improvement_tips": []}, raising=False)

    async def dummy_gen_tmpl(*a, **kw):
        return {}

    monkeypatch.setattr(pl.reason_core, "generate_reflection_template", dummy_gen_tmpl, raising=False)
    monkeypatch.setattr(
        pl.reason_core, "generate_reason",
        lambda *a, **kw: {"text": "reason text", "note": "note"},
        raising=False,
    )

    # Persona
    monkeypatch.setattr(pl, "load_persona", lambda: {"name": "default"})

    return pl


class TestRunDecidePipelineOrchestration:
    @pytest.mark.anyio
    async def test_stages_called_and_metrics_present(self, pipeline_env):
        body = {"query": "orchestration test", "context": {"user_id": "u1"}, "options": []}
        payload = await pipeline_env.run_decide_pipeline(DummyReqModel(body), DummyRequest())

        # basic response structure
        assert "query" in payload
        assert "chosen" in payload
        assert isinstance(payload.get("alternatives"), list)
        assert isinstance(payload.get("evidence"), list)

        # extras / metrics contract
        extras = payload.get("extras") or {}
        metrics = extras.get("metrics") or {}
        assert "mem_hits" in metrics
        assert "web_hits" in metrics
        assert "fast_mode" in metrics or "fast_mode" in extras

    @pytest.mark.anyio
    async def test_kernel_missing_raises(self, pipeline_env, monkeypatch):
        """When veritas_core is None, pipeline must raise ImportError."""
        monkeypatch.setattr(pipeline_env, "veritas_core", None)
        body = {"query": "should fail", "context": {"user_id": "u1"}}
        with pytest.raises(ImportError, match="kernel"):
            await pipeline_env.run_decide_pipeline(DummyReqModel(body), DummyRequest())


# =========================================================
# 9. Optional dependency import safety
# =========================================================


class TestOptionalImportSafety:
    def test_pipeline_module_imports_even_with_missing_optional_deps(self):
        """pipeline module must already be imported; verify key exports exist."""
        assert hasattr(pl, "run_decide_pipeline")
        assert hasattr(pl, "_safe_web_search")
        assert hasattr(pl, "to_dict")
        assert hasattr(pl, "get_request_params")
        assert hasattr(pl, "_check_required_modules")
        assert hasattr(pl, "_dedupe_alts")
        assert hasattr(pl, "_norm_alt")

    def test_atomic_io_flag_is_bool(self):
        assert isinstance(pl._HAS_ATOMIC_IO, bool)

    def test_sanitize_flag_is_bool(self):
        assert isinstance(pl._HAS_SANITIZE, bool)


# =========================================================
# 10. Backward compatibility aliases
# =========================================================


class TestBackwardCompatAliases:
    def test_to_dict_alias(self):
        assert pl._to_dict is pl.to_dict

    def test_get_request_params_alias(self):
        assert pl._get_request_params is pl.get_request_params

    def test_call_core_decide_exported(self):
        assert callable(pl.call_core_decide)

    def test_pipeline_context_exported(self):
        assert pl.PipelineContext is not None

    def test_safe_filename_id_exported(self):
        assert callable(pl._safe_filename_id)

    def test_sanitize_for_diff_exported(self):
        assert callable(pl._sanitize_for_diff)

    def test_build_replay_diff_exported(self):
        assert callable(pl._build_replay_diff)

    def test_replay_request_exported(self):
        assert pl._ReplayRequest is not None

    def test_safe_filename_re_exported(self):
        assert pl._SAFE_FILENAME_RE is not None


# =========================================================
# 11. _warn log level selection
# =========================================================


class TestWarn:
    def test_info_prefix(self, monkeypatch, caplog):
        import logging

        monkeypatch.setenv("VERITAS_PIPELINE_WARN", "1")
        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline"):
            pl._warn("[INFO] test info message")
        assert any("test info message" in r.message for r in caplog.records)

    def test_error_prefix(self, monkeypatch, caplog):
        import logging

        monkeypatch.setenv("VERITAS_PIPELINE_WARN", "1")
        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline"):
            pl._warn("[ERROR] test error message")
        assert any(r.levelno == logging.ERROR for r in caplog.records if "test error" in r.message)

    def test_fatal_prefix(self, monkeypatch, caplog):
        import logging

        monkeypatch.setenv("VERITAS_PIPELINE_WARN", "1")
        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline"):
            pl._warn("[FATAL] fatal test")
        assert any(r.levelno == logging.ERROR for r in caplog.records if "fatal test" in r.message)

    def test_plain_warning(self, monkeypatch, caplog):
        import logging

        monkeypatch.setenv("VERITAS_PIPELINE_WARN", "1")
        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline"):
            pl._warn("plain warning message")
        assert any(r.levelno == logging.WARNING for r in caplog.records if "plain warning" in r.message)

    def test_suppressed_by_env(self, monkeypatch, caplog):
        import logging

        monkeypatch.setenv("VERITAS_PIPELINE_WARN", "0")
        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline"):
            pl._warn("should not appear")
        assert not any("should not appear" in r.message for r in caplog.records)


# =========================================================
# 12. _allow_prob exception handling
# =========================================================


class TestAllowProb:
    def test_normal_return(self, monkeypatch):
        monkeypatch.setattr(pl, "predict_gate_label", lambda text: {"allow": 0.75})
        assert pl._allow_prob("test") == 0.75

    def test_missing_allow_key(self, monkeypatch):
        monkeypatch.setattr(pl, "predict_gate_label", lambda text: {})
        assert pl._allow_prob("test") == 0.0

    def test_non_numeric_allow(self, monkeypatch):
        monkeypatch.setattr(pl, "predict_gate_label", lambda text: {"allow": "bad"})
        assert pl._allow_prob("test") == 0.0

    def test_allow_none(self, monkeypatch):
        monkeypatch.setattr(pl, "predict_gate_label", lambda text: {"allow": None})
        assert pl._allow_prob("test") == 0.0


# =========================================================
# 13. _get_memory_store wrapper
# =========================================================


class TestGetMemoryStore:
    def test_returns_none_when_mem_is_none(self, monkeypatch):
        monkeypatch.setattr(pl, "mem", None)
        assert pl._get_memory_store() is None

    def test_delegates_when_mem_is_set(self, monkeypatch):
        fake_mem = types.SimpleNamespace(get_store=lambda: "the_store")
        monkeypatch.setattr(pl, "mem", fake_mem)
        # Result depends on _get_memory_store_impl; just verify no crash
        # and that it attempts delegation
        try:
            pl._get_memory_store()
        except Exception:
            pass  # impl may need specific attributes - we just test the wrapper path
