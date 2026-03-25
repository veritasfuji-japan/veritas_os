# veritas_os/tests/test_pipeline_compat.py
# -*- coding: utf-8 -*-
"""
Tests for pipeline_compat.py – utility functions extracted from pipeline.py.

Verifies that:
1. Functions work identically to their original pipeline.py implementations.
2. Backward-compat re-exports from pipeline.py still resolve correctly.
3. Edge cases (None, empty, special chars) are handled safely.
"""
from __future__ import annotations

import logging
import pytest
from unittest.mock import MagicMock


# =========================================================
# Direct imports from pipeline_compat
# =========================================================

class TestToDict:
    """to_dict / _to_dict – generic object-to-dict conversion."""

    def test_dict_passthrough(self):
        from veritas_os.core.pipeline_compat import to_dict
        d = {"a": 1}
        assert to_dict(d) is d

    def test_pydantic_v2_model_dump(self):
        from veritas_os.core.pipeline_compat import to_dict
        obj = MagicMock()
        obj.model_dump.return_value = {"key": "val"}
        assert to_dict(obj) == {"key": "val"}

    def test_pydantic_v1_dict(self):
        from veritas_os.core.pipeline_compat import to_dict
        obj = MagicMock(spec=[])
        obj.dict = MagicMock(return_value={"k": 1})
        assert to_dict(obj) == {"k": 1}

    def test_plain_object(self):
        from veritas_os.core.pipeline_compat import to_dict

        class Obj:
            pass

        o = Obj()
        o.x = 10
        o.y = "hello"
        result = to_dict(o)
        assert result.get("x") == 10
        assert result.get("y") == "hello"

    def test_circular_reference_filtered(self):
        from veritas_os.core.pipeline_compat import to_dict

        class Circ:
            pass

        obj = Circ()
        obj.self_ref = obj
        obj.name = "test"
        result = to_dict(obj)
        assert "name" in result
        assert "self_ref" not in result

    def test_none_returns_empty(self):
        from veritas_os.core.pipeline_compat import to_dict
        assert to_dict(None) == {}

    def test_int_returns_empty(self):
        from veritas_os.core.pipeline_compat import to_dict
        assert to_dict(42) == {}

    def test_backward_compat_alias(self):
        from veritas_os.core.pipeline_compat import _to_dict, to_dict
        assert _to_dict is to_dict


class TestGetRequestParams:
    """get_request_params / _get_request_params."""

    def test_starlette_query_params(self):
        from veritas_os.core.pipeline_compat import get_request_params

        class Req:
            query_params = {"fast": "true", "verbose": "1"}
            params = None

        result = get_request_params(Req())
        assert result["fast"] == "true"

    def test_dummy_params(self):
        from veritas_os.core.pipeline_compat import get_request_params

        class Req:
            query_params = None
            params = {"mode": "debug"}

        result = get_request_params(Req())
        assert result["mode"] == "debug"

    def test_both_merged(self):
        from veritas_os.core.pipeline_compat import get_request_params

        class Req:
            query_params = {"a": "1"}
            params = {"b": "2"}

        result = get_request_params(Req())
        assert result == {"a": "1", "b": "2"}

    def test_exception_safe(self):
        from veritas_os.core.pipeline_compat import get_request_params

        class BadReq:
            query_params = None

            def __getattribute__(self, name):
                if name == "params":
                    raise RuntimeError("boom")
                return object.__getattribute__(self, name)

        result = get_request_params(BadReq())
        assert result == {}

    def test_backward_compat_alias(self):
        from veritas_os.core.pipeline_compat import _get_request_params, get_request_params
        assert _get_request_params is get_request_params


class TestNormAlt:
    """_norm_alt – alternative normalization."""

    def test_basic_dict(self):
        from veritas_os.core.pipeline_compat import _norm_alt
        result = _norm_alt({"text": "Hello", "score": 0.8})
        assert result["title"] == "Hello"
        assert result["description"] == "Hello"
        assert result["score"] == 0.8
        assert "id" in result

    def test_id_preserved(self):
        from veritas_os.core.pipeline_compat import _norm_alt
        result = _norm_alt({"id": "abc123", "text": "X"})
        assert result["id"] == "abc123"

    def test_empty_id_generates_new(self):
        from veritas_os.core.pipeline_compat import _norm_alt
        result = _norm_alt({"id": "", "text": "X"})
        assert len(result["id"]) == 32  # uuid4().hex

    def test_none_id_generates_new(self):
        from veritas_os.core.pipeline_compat import _norm_alt
        result = _norm_alt({"text": "X"})
        assert len(result["id"]) == 32

    def test_control_chars_stripped_from_id(self):
        from veritas_os.core.pipeline_compat import _norm_alt
        result = _norm_alt({"id": "ab\x00cd\x1fef", "text": "X"})
        assert result["id"] == "abcdef"

    def test_id_length_capped(self):
        from veritas_os.core.pipeline_compat import _norm_alt
        long_id = "a" * 300
        result = _norm_alt({"id": long_id, "text": "X"})
        assert len(result["id"]) <= 256

    def test_score_defaults(self):
        from veritas_os.core.pipeline_compat import _norm_alt
        result = _norm_alt({"text": "X"})
        assert result["score"] == 1.0
        assert result["score_raw"] == 1.0

    def test_from_object(self):
        from veritas_os.core.pipeline_compat import _norm_alt

        class Alt:
            pass

        a = Alt()
        a.text = "hi"
        a.score = 0.5
        result = _norm_alt(a)
        assert result["title"] == "hi"
        assert result["score"] == 0.5


class TestToBool:
    """_to_bool – bool conversion."""

    def test_truthy(self):
        from veritas_os.core.pipeline_compat import _to_bool
        assert _to_bool("1") is True
        assert _to_bool("true") is True
        assert _to_bool("yes") is True
        assert _to_bool(True) is True

    def test_falsy(self):
        from veritas_os.core.pipeline_compat import _to_bool
        assert _to_bool("0") is False
        assert _to_bool("false") is False
        assert _to_bool("") is False
        assert _to_bool(None) is False


class TestToFloatOr:
    """_to_float_or – float conversion with default."""

    def test_valid(self):
        from veritas_os.core.pipeline_compat import _to_float_or
        assert _to_float_or("3.14", 0.0) == 3.14

    def test_invalid(self):
        from veritas_os.core.pipeline_compat import _to_float_or
        assert _to_float_or("not_a_number", 42.0) == 42.0

    def test_none(self):
        from veritas_os.core.pipeline_compat import _to_float_or
        assert _to_float_or(None, 1.0) == 1.0


class TestClip01:
    """_clip01 – clip float to [0, 1]."""

    def test_in_range(self):
        from veritas_os.core.pipeline_compat import _clip01
        assert _clip01(0.5) == 0.5

    def test_below(self):
        from veritas_os.core.pipeline_compat import _clip01
        assert _clip01(-0.5) == 0.0

    def test_above(self):
        from veritas_os.core.pipeline_compat import _clip01
        assert _clip01(1.5) == 1.0


class TestFallbackLoadPersona:
    """_fallback_load_persona."""

    def test_returns_fallback_dict(self):
        from veritas_os.core.pipeline_compat import _fallback_load_persona
        result = _fallback_load_persona()
        assert result == {"name": "fallback", "mode": "minimal"}


# =========================================================
# Re-export verification: importing from pipeline.py still works
# =========================================================

class TestPipelineReExports:
    """Verify that all moved functions are accessible from pipeline.py."""

    def test_to_dict_reexport(self):
        from veritas_os.core.pipeline import to_dict
        assert callable(to_dict)
        assert to_dict({"a": 1}) == {"a": 1}

    def test_to_dict_alias_reexport(self):
        from veritas_os.core.pipeline import _to_dict
        assert callable(_to_dict)

    def test_get_request_params_reexport(self):
        from veritas_os.core.pipeline import get_request_params
        assert callable(get_request_params)

    def test_get_request_params_alias_reexport(self):
        from veritas_os.core.pipeline import _get_request_params
        assert callable(_get_request_params)

    def test_norm_alt_reexport(self):
        from veritas_os.core.pipeline import _norm_alt
        result = _norm_alt({"text": "test"})
        assert result["title"] == "test"

    def test_to_bool_reexport(self):
        from veritas_os.core.pipeline import _to_bool
        assert _to_bool("1") is True

    def test_clip01_reexport(self):
        from veritas_os.core.pipeline import _clip01
        assert _clip01(0.5) == 0.5

    def test_fallback_load_persona_reexport(self):
        from veritas_os.core.pipeline import _fallback_load_persona
        assert _fallback_load_persona()["name"] == "fallback"


# =========================================================
# Logger integration: compat functions log to pipeline logger
# =========================================================

class TestCompatLogging:
    """Functions in pipeline_compat log to veritas_os.core.pipeline logger."""

    def test_get_request_params_logs_to_pipeline_logger(self, caplog):
        from veritas_os.core.pipeline_compat import get_request_params

        class BadReq:
            query_params = None
            def __getattribute__(self, name):
                if name == "params":
                    raise RuntimeError("test error")
                return object.__getattribute__(self, name)

        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline"):
            get_request_params(BadReq())

        assert any("params extraction failed" in r.message for r in caplog.records)

    def test_to_dict_logs_to_pipeline_logger(self, caplog):
        from veritas_os.core.pipeline_compat import to_dict

        class BadObj:
            def model_dump(self, **kw):
                raise RuntimeError("boom")

        with caplog.at_level(logging.DEBUG, logger="veritas_os.core.pipeline"):
            to_dict(BadObj())

        assert any("model_dump() failed" in r.message for r in caplog.records)
