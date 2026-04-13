# tests for veritas_os/api/utils.py
"""Tests for API utility functions."""
from __future__ import annotations

import os
from unittest import mock

import pytest

from veritas_os.api.utils import (
    _classify_decide_failure,
    _coerce_alt_list,
    _coerce_decide_payload,
    _coerce_fuji_payload,
    _decide_example,
    _errstr,
    _gen_request_id,
    _is_debug_mode,
    _is_direct_fuji_api_enabled,
    _log_decide_failure,
    _parse_risk_from_trust_entry,
    _prov_actor_for_entry,
    _stage_summary,
    redact,
)


class TestErrstr:
    def test_formats_error(self):
        assert _errstr(ValueError("oops")) == "ValueError: oops"


class TestStageSummary:
    def test_dict_with_summary(self):
        assert _stage_summary({"summary": "hello"}, "default") == "hello"

    def test_dict_without_summary(self):
        assert _stage_summary({"other": 1}, "default") == "default"

    def test_list_with_dict_summary(self):
        assert _stage_summary([{"summary": "found"}], "default") == "found"

    def test_list_with_string(self):
        assert _stage_summary(["direct"], "default") == "direct"

    def test_string(self):
        assert _stage_summary("raw", "default") == "raw"

    def test_default(self):
        assert _stage_summary(None, "fallback") == "fallback"

    def test_empty_string(self):
        assert _stage_summary("", "default") == "default"

    def test_whitespace_only_summary(self):
        assert _stage_summary({"summary": "   "}, "default") == "default"


class TestRedact:
    def test_masks_email(self):
        result = redact("contact me at user@example.com")
        assert "user@example.com" not in result

    def test_masks_phone(self):
        result = redact("call 090-1234-5678")
        assert "090-1234-5678" not in result

    def test_empty(self):
        assert redact("") == ""

    def test_no_pii(self):
        assert redact("hello world") == "hello world"


class TestGenRequestId:
    def test_returns_string(self):
        rid = _gen_request_id("test")
        assert isinstance(rid, str)
        assert len(rid) == 24

    def test_unique(self):
        assert _gen_request_id("a") != _gen_request_id("b")


class TestCoerceAltList:
    def test_none(self):
        assert _coerce_alt_list(None) == []

    def test_dict_wrapped(self):
        result = _coerce_alt_list({"title": "opt1"})
        assert len(result) == 1
        assert result[0]["title"] == "opt1"

    def test_string(self):
        result = _coerce_alt_list("raw")
        assert len(result) == 1
        assert result[0]["title"] == "raw"

    def test_list_of_dicts(self):
        result = _coerce_alt_list([{"title": "a"}, {"title": "b"}])
        assert len(result) == 2

    def test_list_with_non_dict(self):
        result = _coerce_alt_list(["plain_string"])
        assert result[0]["title"] == "plain_string"

    def test_score_conversion(self):
        result = _coerce_alt_list([{"title": "x", "score": "0.5"}])
        assert result[0]["score"] == 0.5

    def test_bad_score(self):
        result = _coerce_alt_list([{"title": "x", "score": "bad"}])
        assert result[0]["score"] == 1.0

    @pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_score(self, score):
        result = _coerce_alt_list([{"title": "x", "score": score}])
        assert result[0]["score"] == 1.0


class TestCoerceDecidePayload:
    def test_non_dict(self):
        result = _coerce_decide_payload("raw")
        assert result["ok"] is True
        assert result["chosen"]["title"] == "raw"

    def test_dict_fills_defaults(self):
        result = _coerce_decide_payload({})
        assert result["ok"] is True
        assert result["trust_log"] is None
        assert result["chosen"] == {}

    def test_chosen_non_dict_coerced(self):
        result = _coerce_decide_payload({"chosen": "text"})
        assert result["chosen"] == {"title": "text"}

    def test_options_to_alternatives(self):
        result = _coerce_decide_payload({"options": [{"title": "a"}]})
        assert len(result["alternatives"]) == 1


class TestCoerceFujiPayload:
    def test_non_dict(self):
        result = _coerce_fuji_payload("raw", action="test")
        assert result["status"] == "allow"
        assert result["action"] == "test"

    def test_dict_fills_defaults(self):
        result = _coerce_fuji_payload({})
        assert result["status"] == "allow"
        assert result["reasons"] == []
        assert result["violations"] == []


class TestClassifyDecideFailure:
    def test_timeout(self):
        assert _classify_decide_failure(TimeoutError()) == "timeout"

    def test_permission(self):
        assert _classify_decide_failure(PermissionError()) == "permission_denied"

    def test_value_error(self):
        assert _classify_decide_failure(ValueError()) == "invalid_input"

    def test_other(self):
        assert _classify_decide_failure(RuntimeError()) == "internal"


class TestIsDebugMode:
    def test_off(self):
        with mock.patch.dict(os.environ, {"VERITAS_DEBUG_MODE": "0"}):
            assert _is_debug_mode() is False

    def test_on(self):
        with mock.patch.dict(os.environ, {"VERITAS_DEBUG_MODE": "true"}):
            assert _is_debug_mode() is True


class TestIsDirectFujiApiEnabled:
    def test_off(self):
        with mock.patch.dict(os.environ, {"VERITAS_ENABLE_DIRECT_FUJI_API": ""}):
            assert _is_direct_fuji_api_enabled() is False

    def test_on(self):
        with mock.patch.dict(os.environ, {"VERITAS_ENABLE_DIRECT_FUJI_API": "1"}):
            assert _is_direct_fuji_api_enabled() is True

    def test_forced_off_in_production(self):
        with mock.patch.dict(
            os.environ,
            {
                "VERITAS_ENABLE_DIRECT_FUJI_API": "1",
                "VERITAS_ENV": "production",
            },
        ):
            assert _is_direct_fuji_api_enabled() is False


class TestParseRiskFromTrustEntry:
    def test_direct_risk(self):
        assert _parse_risk_from_trust_entry({"risk": 0.5}) == 0.5

    def test_gate_risk(self):
        assert _parse_risk_from_trust_entry({"gate": {"risk": 0.3}}) == 0.3

    def test_fuji_risk(self):
        assert _parse_risk_from_trust_entry({"fuji": {"risk": 0.7}}) == 0.7

    def test_none_for_missing(self):
        assert _parse_risk_from_trust_entry({}) is None

    def test_non_dict(self):
        assert _parse_risk_from_trust_entry("bad") is None

    def test_non_finite_risk(self):
        assert _parse_risk_from_trust_entry({"risk": float("nan")}) is None
        assert _parse_risk_from_trust_entry({"risk": float("inf")}) is None

    def test_boolean_risk_is_ignored(self):
        assert _parse_risk_from_trust_entry({"risk": True}) is None
        assert _parse_risk_from_trust_entry({"gate": {"risk": False}}) is None


class TestProvActorForEntry:
    def test_updated_by(self):
        assert _prov_actor_for_entry({"updated_by": "alice"}) == "alice"

    def test_actor(self):
        assert _prov_actor_for_entry({"actor": "bob"}) == "bob"

    def test_default(self):
        assert _prov_actor_for_entry({}) == "veritas_api"


class TestDecideExample:
    def test_structure(self):
        ex = _decide_example()
        assert "context" in ex
        assert "query" in ex
        assert "options" in ex


class TestLogDecideFailure:
    def test_no_error(self):
        # Should not raise
        _log_decide_failure("msg", None)

    def test_with_exception(self):
        _log_decide_failure("msg", ValueError("bad"))

    def test_with_string(self):
        _log_decide_failure("msg", "error detail")
