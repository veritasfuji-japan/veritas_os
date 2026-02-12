# -*- coding: utf-8 -*-
"""Tests to boost coverage for veritas_os/core/utils.py."""
from __future__ import annotations

import math
from unittest import mock

from veritas_os.core.utils import (
    _clip01,
    _clamp,
    _clamp01,
    _extract_json_object,
    _get_nested,
    _redact_text,
    _safe_float,
    _strip_code_block,
    _to_float,
    _to_text,
    _truncate,
    redact_payload,
    utc_now,
    utc_now_iso_z,
)


# ── _safe_float NaN / Inf ────────────────────────────────────────────

def test_safe_float_nan() -> None:
    assert _safe_float(float("nan"), 0.0) == 0.0


def test_safe_float_inf() -> None:
    assert _safe_float(float("inf"), -1.0) == -1.0


def test_safe_float_negative_inf() -> None:
    assert _safe_float(float("-inf")) == 0.0


def test_safe_float_valid_number() -> None:
    assert _safe_float("3.14") == 3.14


def test_safe_float_invalid_string() -> None:
    assert _safe_float("abc", 5.0) == 5.0


# ── _to_float / _clip01 / _clamp / _clamp01 ─────────────────────────

def test_to_float_delegates() -> None:
    assert _to_float("2.5") == 2.5


def test_clip01_in_range() -> None:
    assert _clip01(0.5) == 0.5


def test_clip01_above() -> None:
    assert _clip01(1.5) == 1.0


def test_clip01_below() -> None:
    assert _clip01(-0.3) == 0.0


def test_clamp_basic() -> None:
    assert _clamp(5, 0, 10) == 5.0
    assert _clamp(15, 0, 10) == 10.0


def test_clamp01_basic() -> None:
    assert _clamp01(0.5) == 0.5


# ── _get_nested edge cases ───────────────────────────────────────────

def test_get_nested_none_in_chain() -> None:
    d = {"a": {"b": None}}
    # b is None so traversal into "c" should hit the not-isinstance(dict) branch
    assert _get_nested(d, "a", "b", "c", default="miss") == "miss"


def test_get_nested_missing_key() -> None:
    d = {"a": {"b": 1}}
    assert _get_nested(d, "a", "x", default=99) == 99


# ── _truncate edge cases ─────────────────────────────────────────────

def test_truncate_short_max_len() -> None:
    # max_len shorter than suffix length → raw slice without suffix
    assert _truncate("abcdef", max_len=2) == "ab"


def test_truncate_max_len_equals_suffix() -> None:
    # max_len == len(suffix) → raw slice
    assert _truncate("abcdef", max_len=3, suffix="...") == "abc"


def test_truncate_empty_string() -> None:
    assert _truncate("", max_len=5) == ""


# ── _to_text dict field lookup ────────────────────────────────────────

def test_to_text_dict_with_query() -> None:
    assert _to_text({"query": "hello"}) == "hello"


def test_to_text_dict_with_title() -> None:
    assert _to_text({"title": "My Title"}) == "My Title"


def test_to_text_dict_no_text_fields() -> None:
    # No recognized text field → falls through to str()
    result = _to_text({"foo": "bar"})
    assert "foo" in result  # dict __str__ contains key


# ── _strip_code_block ────────────────────────────────────────────────

def test_strip_code_block_json() -> None:
    raw = '```json\n{"a": 1}\n```'
    assert _strip_code_block(raw) == '{"a": 1}'


def test_strip_code_block_plain() -> None:
    assert _strip_code_block('{"a": 1}') == '{"a": 1}'


def test_strip_code_block_empty() -> None:
    assert _strip_code_block("") == ""


def test_strip_code_block_no_newline() -> None:
    # ``` without newline – first_nl == -1 branch, endswith(```) strips it
    assert _strip_code_block("```") == ""


# ── _extract_json_object ─────────────────────────────────────────────

def test_extract_json_object_with_prefix() -> None:
    result = _extract_json_object('some prefix {"key": "val"} suffix')
    assert '"key"' in result and '"val"' in result


def test_extract_json_object_no_json() -> None:
    assert _extract_json_object("no json here") == ""


def test_extract_json_object_empty() -> None:
    assert _extract_json_object("") == ""


def test_extract_json_object_invalid_json() -> None:
    assert _extract_json_object("{not valid json}") == ""


# ── _redact_text regex PII masking ────────────────────────────────────

def test_redact_text_email() -> None:
    result = _redact_text("contact user@example.com please")
    assert "user@example.com" not in result


def test_redact_text_phone() -> None:
    result = _redact_text("call 090-1234-5678 now")
    assert "090-1234-5678" not in result


def test_redact_text_empty() -> None:
    assert _redact_text("") == ""


# ── redact_payload recursive ──────────────────────────────────────────

def test_redact_payload_dict() -> None:
    payload = {"msg": "email user@example.com"}
    result = redact_payload(payload)
    assert "user@example.com" not in result["msg"]


def test_redact_payload_list() -> None:
    payload = ["user@example.com"]
    result = redact_payload(payload)
    assert "user@example.com" not in result[0]


def test_redact_payload_tuple() -> None:
    payload = ("user@example.com",)
    result = redact_payload(payload)
    assert isinstance(result, tuple)
    assert "user@example.com" not in result[0]


def test_redact_payload_depth_limit() -> None:
    # At depth > 50, value is returned as-is
    result = redact_payload("user@example.com", _depth=51)
    assert result == "user@example.com"


def test_redact_payload_non_string() -> None:
    assert redact_payload(42) == 42
    assert redact_payload(None) is None


# ── _to_text None / str paths ────────────────────────────────────────

def test_to_text_none() -> None:
    assert _to_text(None) == ""


def test_to_text_string() -> None:
    assert _to_text("hello") == "hello"


# ── utc_now / utc_now_iso_z ──────────────────────────────────────────

def test_utc_now_returns_aware() -> None:
    dt = utc_now()
    assert dt.tzinfo is not None


def test_utc_now_iso_z() -> None:
    result = utc_now_iso_z()
    assert result.endswith("Z")


# ── _get_nested full path success ─────────────────────────────────────

def test_get_nested_success() -> None:
    d = {"a": {"b": {"c": 42}}}
    assert _get_nested(d, "a", "b", "c") == 42


# ── _truncate normal case ────────────────────────────────────────────

def test_truncate_normal() -> None:
    assert _truncate("abcdefghij", max_len=7) == "abcd..."


# ── _redact_text regex fallback (sanitize module mocked out) ──────────

def test_redact_text_regex_fallback_email() -> None:
    import veritas_os.core.utils as utils_mod
    with mock.patch.object(utils_mod, "_HAS_SANITIZE_IMPL", False):
        result = utils_mod._redact_text("contact user@example.com please")
        assert "[redacted@email]" in result


def test_redact_text_regex_fallback_phone() -> None:
    import veritas_os.core.utils as utils_mod
    with mock.patch.object(utils_mod, "_HAS_SANITIZE_IMPL", False):
        result = utils_mod._redact_text("call 090-1234-5678 now")
        assert "[redacted:phone]" in result
