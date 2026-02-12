# veritas_os/tests/test_pipeline_coverage_boost2.py
"""Tests targeting module-level helpers in veritas_os.core.pipeline."""
from __future__ import annotations

import logging
import os
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from veritas_os.core import pipeline


# =========================================================
# _to_bool
# =========================================================


class TestToBool:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            (True, True),
            (False, False),
            (1, True),
            (0, False),
            (1.5, True),
            (0.0, False),
            ("1", True),
            ("true", True),
            ("yes", True),
            ("y", True),
            ("on", True),
            ("0", False),
            ("false", False),
            ("no", False),
            ("n", False),
            ("off", False),
            ("", False),
            ("  TRUE  ", True),
            (None, False),
            ([], False),
        ],
    )
    def test_to_bool(self, inp, expected):
        assert pipeline._to_bool(inp) is expected


# =========================================================
# _warn
# =========================================================


class TestWarn:
    def test_info_prefix(self, caplog):
        with caplog.at_level(logging.INFO, logger="veritas_os.core.pipeline"):
            pipeline._warn("[INFO] something")
        assert "[INFO] something" in caplog.text

    def test_error_prefix(self, caplog):
        with caplog.at_level(logging.ERROR, logger="veritas_os.core.pipeline"):
            pipeline._warn("[ERROR] oops")
        assert "[ERROR] oops" in caplog.text

    def test_fatal_prefix(self, caplog):
        with caplog.at_level(logging.ERROR, logger="veritas_os.core.pipeline"):
            pipeline._warn("[FATAL] crash")
        assert "[FATAL] crash" in caplog.text

    def test_default_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="veritas_os.core.pipeline"):
            pipeline._warn("plain warning")
        assert "plain warning" in caplog.text

    def test_suppressed(self, monkeypatch):
        monkeypatch.setenv("VERITAS_PIPELINE_WARN", "0")
        with patch.object(pipeline.logger, "warning") as mock_w:
            pipeline._warn("hidden")
        mock_w.assert_not_called()


# =========================================================
# _check_required_modules
# =========================================================


class TestCheckRequiredModules:
    def test_all_present(self, monkeypatch):
        monkeypatch.setattr(pipeline, "veritas_core", MagicMock())
        monkeypatch.setattr(pipeline, "fuji_core", MagicMock())
        pipeline._check_required_modules()  # should not raise

    def test_missing_kernel(self, monkeypatch):
        monkeypatch.setattr(pipeline, "veritas_core", None)
        monkeypatch.setattr(pipeline, "fuji_core", MagicMock())
        with pytest.raises(ImportError, match="kernel"):
            pipeline._check_required_modules()

    def test_missing_fuji(self, monkeypatch):
        monkeypatch.setattr(pipeline, "veritas_core", MagicMock())
        monkeypatch.setattr(pipeline, "fuji_core", None)
        with pytest.raises(ImportError, match="fuji"):
            pipeline._check_required_modules()

    def test_missing_both(self, monkeypatch):
        monkeypatch.setattr(pipeline, "veritas_core", None)
        monkeypatch.setattr(pipeline, "fuji_core", None)
        with pytest.raises(ImportError, match="kernel.*fuji"):
            pipeline._check_required_modules()


# =========================================================
# _to_dict
# =========================================================


class TestToDict:
    def test_dict_passthrough(self):
        d = {"a": 1}
        assert pipeline._to_dict(d) is d

    def test_pydantic_model_dump(self):
        obj = MagicMock()
        obj.model_dump.return_value = {"x": 1}
        assert pipeline._to_dict(obj) == {"x": 1}

    def test_legacy_dict_method(self):
        obj = MagicMock(spec=[])
        obj.dict = MagicMock(return_value={"y": 2})
        assert pipeline._to_dict(obj) == {"y": 2}

    def test_simplenamespace(self):
        ns = SimpleNamespace(a=1, b=2)
        result = pipeline._to_dict(ns)
        assert result == {"a": 1, "b": 2}

    def test_none(self):
        assert pipeline._to_dict(None) == {}

    def test_string(self):
        assert pipeline._to_dict("hello") == {}


# =========================================================
# _get_request_params
# =========================================================


class TestGetRequestParams:
    def test_query_params_only(self):
        req = SimpleNamespace(query_params={"a": "1"})
        assert pipeline._get_request_params(req) == {"a": "1"}

    def test_params_only(self):
        req = SimpleNamespace(params={"b": "2"})
        assert pipeline._get_request_params(req) == {"b": "2"}

    def test_both_merged(self):
        req = SimpleNamespace(query_params={"a": "1"}, params={"b": "2"})
        result = pipeline._get_request_params(req)
        assert result == {"a": "1", "b": "2"}

    def test_neither(self):
        req = SimpleNamespace()
        assert pipeline._get_request_params(req) == {}

    def test_params_overrides_query_params(self):
        req = SimpleNamespace(query_params={"k": "old"}, params={"k": "new"})
        assert pipeline._get_request_params(req)["k"] == "new"


# =========================================================
# _ensure_metrics_contract
# =========================================================


class TestEnsureMetricsContract:
    def test_empty_dict(self):
        extras: Dict[str, Any] = {}
        pipeline._ensure_metrics_contract(extras)
        assert "metrics" in extras
        assert extras["metrics"]["mem_hits"] == 0
        assert extras["metrics"]["web_hits"] == 0
        assert extras["fast_mode"] is False

    def test_partial_preserves_existing(self):
        extras: Dict[str, Any] = {"metrics": {"mem_hits": 5}}
        pipeline._ensure_metrics_contract(extras)
        assert extras["metrics"]["mem_hits"] == 5
        assert extras["metrics"]["web_hits"] == 0


# =========================================================
# _norm_alt
# =========================================================


class TestNormAlt:
    def test_full_dict(self):
        d = {"title": "T", "description": "D", "score": 0.8, "id": "abc"}
        result = pipeline._norm_alt(d)
        assert result["title"] == "T"
        assert result["id"] == "abc"
        assert result["score"] == 0.8

    def test_missing_title_uses_text(self):
        d = {"text": "hello"}
        result = pipeline._norm_alt(d)
        assert result["title"] == "hello"

    def test_missing_id_generates_hex(self):
        d = {"title": "T"}
        result = pipeline._norm_alt(d)
        assert isinstance(result["id"], str)
        assert len(result["id"]) == 32  # uuid4().hex

    def test_empty_id_generates_new(self):
        d = {"id": "  "}
        result = pipeline._norm_alt(d)
        assert result["id"] != "  "
        assert len(result["id"]) == 32


# =========================================================
# _clip01
# =========================================================


class TestClip01:
    def test_within_range(self):
        assert pipeline._clip01(0.5) == 0.5

    def test_below_zero(self):
        assert pipeline._clip01(-1.0) == 0.0

    def test_above_one(self):
        assert pipeline._clip01(2.0) == 1.0


# =========================================================
# _safe_paths
# =========================================================


class TestSafePaths:
    def test_returns_four_paths(self):
        result = pipeline._safe_paths()
        assert len(result) == 4
        from pathlib import Path
        for p in result:
            assert isinstance(p, Path)

    def test_env_override_log_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("VERITAS_LOG_DIR", str(tmp_path / "logs"))
        monkeypatch.setenv("VERITAS_DATASET_DIR", str(tmp_path / "ds"))
        log_dir, ds_dir, _, _ = pipeline._safe_paths()
        assert str(tmp_path / "logs") in str(log_dir)
        assert str(tmp_path / "ds") in str(ds_dir)


# =========================================================
# _get_memory_store
# =========================================================


class TestGetMemoryStore:
    def test_mem_with_search(self, monkeypatch):
        mock_mem = MagicMock()
        mock_mem.search = MagicMock()
        monkeypatch.setattr(pipeline, "mem", mock_mem)
        assert pipeline._get_memory_store() is mock_mem

    def test_mem_with_MEM_attr(self, monkeypatch):
        mock_inner = MagicMock()
        mock_mem = MagicMock(spec=[])
        mock_mem.MEM = mock_inner
        monkeypatch.setattr(pipeline, "mem", mock_mem)
        assert pipeline._get_memory_store() is mock_inner

    def test_mem_is_none(self, monkeypatch):
        monkeypatch.setattr(pipeline, "mem", None)
        assert pipeline._get_memory_store() is None


# =========================================================
# _call_with_accepted_kwargs
# =========================================================


class TestCallWithAcceptedKwargs:
    def test_subset_accepted(self):
        def fn(a, b):
            return a + b
        result = pipeline._call_with_accepted_kwargs(fn, {"a": 1, "b": 2, "c": 3})
        assert result == 3

    def test_fn_raises(self):
        def fn(a):
            raise ValueError("boom")
        with pytest.raises(ValueError, match="boom"):
            pipeline._call_with_accepted_kwargs(fn, {"a": 1})

    def test_no_inspectable_sig(self):
        # Trigger the except branch: signature() raises, then fn(**kwargs) succeeds
        class NoSig:
            def __call__(self, **kwargs):
                return kwargs.get("x", 0)

        fn = NoSig()
        # Patch inspect.signature to raise for this call
        orig = pipeline.inspect.signature
        def bad_sig(f):
            if f is fn:
                raise ValueError("no sig")
            return orig(f)
        with patch.object(pipeline.inspect, "signature", side_effect=bad_sig):
            result = pipeline._call_with_accepted_kwargs(fn, {"x": 42})
        assert result == 42


# =========================================================
# _memory_has
# =========================================================


class TestMemoryHas:
    def test_has_callable(self):
        store = SimpleNamespace(search=lambda: None)
        assert pipeline._memory_has(store, "search") is True

    def test_has_non_callable(self):
        store = SimpleNamespace(search="not callable")
        assert pipeline._memory_has(store, "search") is False

    def test_missing_attr(self):
        store = SimpleNamespace()
        assert pipeline._memory_has(store, "search") is False


# =========================================================
# _memory_search
# =========================================================


class TestMemorySearch:
    def test_success(self):
        store = MagicMock()
        store.search.return_value = [{"id": "1"}]
        result = pipeline._memory_search(store, query="test", k=5)
        assert result == [{"id": "1"}]

    def test_no_search(self):
        store = SimpleNamespace()
        with pytest.raises(RuntimeError, match="not available"):
            pipeline._memory_search(store, query="q")

    def test_type_error_fallback(self):
        call_count = 0

        def flaky_search(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TypeError("bad kwargs")
            return ["fallback"]

        store = MagicMock()
        store.search = flaky_search
        result = pipeline._memory_search(store, query="q", k=3)
        assert result == ["fallback"]

    def test_minimal_fallback(self):
        """Falls through all attempts to positional call."""
        call_count = 0

        def tricky_search(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise TypeError("nope")
            if call_count == 3:
                raise Exception("still no")
            return ["pos_result"]

        store = MagicMock()
        store.search = tricky_search
        result = pipeline._memory_search(store, query="q", k=2)
        assert result == ["pos_result"]


# =========================================================
# _memory_put
# =========================================================


class TestMemoryPut:
    def test_success(self):
        store = MagicMock()
        result = pipeline._memory_put(store, "u1", key="k", value="v", meta=None)
        assert result is None
        store.put.assert_called()

    def test_no_put(self):
        store = SimpleNamespace()
        assert pipeline._memory_put(store, "u1", key="k", value="v") is None

    def test_fallback_chains(self):
        call_count = 0

        def bad_put(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise Exception("fail")

        store = MagicMock()
        store.put = bad_put
        pipeline._memory_put(store, "u1", key="k", value="v", meta=None)
        assert call_count == 4


# =========================================================
# _memory_add_usage
# =========================================================


class TestMemoryAddUsage:
    def test_success(self):
        store = MagicMock()
        pipeline._memory_add_usage(store, "u1", ["id1", "id2"])
        store.add_usage.assert_called()

    def test_no_method(self):
        store = SimpleNamespace()
        assert pipeline._memory_add_usage(store, "u1", ["id1"]) is None

    def test_fallback_to_positional(self):
        call_count = 0

        def bad_add_usage(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("kwargs fail")

        store = MagicMock()
        store.add_usage = bad_add_usage
        pipeline._memory_add_usage(store, "u1", ["id1"])
        assert call_count == 2


# =========================================================
# _normalize_web_payload
# =========================================================


class TestNormalizeWebPayload:
    def test_none(self):
        assert pipeline._normalize_web_payload(None) is None

    def test_dict_with_results(self):
        p = {"results": [{"title": "A"}], "ok": True}
        out = pipeline._normalize_web_payload(p)
        assert out["ok"] is True
        assert len(out["results"]) == 1

    def test_dict_without_results_uses_items(self):
        p = {"items": [{"title": "B"}]}
        out = pipeline._normalize_web_payload(p)
        assert out["results"] == [{"title": "B"}]
        assert out["ok"] is True

    def test_dict_without_results_uses_hits(self):
        p = {"hits": [{"title": "C"}]}
        out = pipeline._normalize_web_payload(p)
        assert out["results"] == [{"title": "C"}]

    def test_dict_without_results_uses_organic(self):
        p = {"organic": [{"title": "D"}]}
        out = pipeline._normalize_web_payload(p)
        assert out["results"] == [{"title": "D"}]

    def test_dict_empty(self):
        p: dict = {}
        out = pipeline._normalize_web_payload(p)
        assert out["results"] == []
        assert out["ok"] is True

    def test_dict_with_ok_false(self):
        p = {"ok": False, "results": []}
        out = pipeline._normalize_web_payload(p)
        assert out["ok"] is False

    def test_list_payload(self):
        p = [{"title": "X"}]
        out = pipeline._normalize_web_payload(p)
        assert out["ok"] is True
        assert out["results"] == [{"title": "X"}]

    def test_string_payload(self):
        out = pipeline._normalize_web_payload("raw text")
        assert out["ok"] is True
        assert len(out["results"]) == 1
        assert out["results"][0]["title"] == "raw text"


# =========================================================
# _norm_evidence_item_simple
# =========================================================


class TestNormEvidenceItemSimple:
    def test_valid_dict(self):
        ev = {
            "source": "web",
            "uri": "http://a.com",
            "title": "A",
            "snippet": "s",
            "confidence": 0.9,
        }
        result = pipeline._norm_evidence_item_simple(ev)
        assert result["source"] == "web"
        assert result["confidence"] == 0.9

    def test_weight_fallback(self):
        ev = {"weight": 0.6, "kind": "test"}
        result = pipeline._norm_evidence_item_simple(ev)
        assert result["confidence"] == 0.6

    def test_title_from_kind(self):
        ev = {"kind": "doc"}
        result = pipeline._norm_evidence_item_simple(ev)
        assert "doc" in result["title"]

    def test_uri_from_kind(self):
        ev = {"kind": "mem"}
        result = pipeline._norm_evidence_item_simple(ev)
        assert "mem" in result["uri"]

    def test_non_dict(self):
        assert pipeline._norm_evidence_item_simple("not a dict") is None
        assert pipeline._norm_evidence_item_simple(42) is None
        assert pipeline._norm_evidence_item_simple(None) is None

    def test_confidence_clamp(self):
        ev = {"confidence": 2.0}
        result = pipeline._norm_evidence_item_simple(ev)
        assert result["confidence"] == 1.0

        ev2 = {"confidence": -1.0}
        result2 = pipeline._norm_evidence_item_simple(ev2)
        assert result2["confidence"] == 0.0

    def test_none_snippet(self):
        ev = {"snippet": None}
        result = pipeline._norm_evidence_item_simple(ev)
        assert result["snippet"] == ""


# =========================================================
# _evidencepy_to_pipeline_item
# =========================================================


class TestEvidencepyToPipelineItem:
    def test_valid(self):
        ev = {"source": "local", "kind": "memory", "snippet": "s", "weight": 0.8, "tags": ["t"]}
        result = pipeline._evidencepy_to_pipeline_item(ev)
        assert result is not None
        assert result["source"] == "local"
        assert result["confidence"] == 0.8
        assert "memory" in result["uri"]

    def test_defaults(self):
        ev: dict = {}
        result = pipeline._evidencepy_to_pipeline_item(ev)
        assert result is not None
        assert result["confidence"] == 0.5
        assert "unknown" in result["title"]


# =========================================================
# _to_float_or (alias for _safe_float)
# =========================================================


class TestToFloatOr:
    def test_valid(self):
        assert pipeline._to_float_or("3.14", 0.0) == 3.14

    def test_invalid(self):
        assert pipeline._to_float_or("bad", 1.0) == 1.0
