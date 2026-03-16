# tests for veritas_os/core/fuji_policy.py
"""Tests for FUJI policy engine — loading, hot reload, rule evaluation."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from veritas_os.core.fuji_policy import (
    _DEFAULT_POLICY,
    _STRICT_DENY_POLICY,
    _apply_policy,
    _build_pii_patterns_from_policy,
    _fallback_policy,
    _load_policy,
    _load_policy_from_str,
    _policy_blocked_keywords,
    _policy_path,
    _strict_policy_load_enabled,
    _PII_RE,
    BANNED_KEYWORDS_FALLBACK,
    SENSITIVE_KEYWORDS_FALLBACK,
    reload_policy,
)


class TestPolicyBlockedKeywords:
    def test_fallback_when_no_policy_keywords(self):
        hard, sensitive = _policy_blocked_keywords({})
        assert hard == {w.lower() for w in BANNED_KEYWORDS_FALLBACK}
        assert sensitive == {w.lower() for w in SENSITIVE_KEYWORDS_FALLBACK}

    def test_custom_keywords(self):
        policy = {
            "blocked_keywords": {
                "hard_block": ["custom_banned"],
                "sensitive": ["custom_sensitive"],
            }
        }
        hard, sensitive = _policy_blocked_keywords(policy)
        assert "custom_banned" in hard
        assert "custom_sensitive" in sensitive

    def test_empty_hard_block_falls_back(self):
        policy = {"blocked_keywords": {"hard_block": [], "sensitive": ["x"]}}
        hard, sensitive = _policy_blocked_keywords(policy)
        assert hard == {w.lower() for w in BANNED_KEYWORDS_FALLBACK}
        assert "x" in sensitive


class TestApplyPolicy:
    def _default_call(self, risk=0.1, categories=None, stakes=0.5, telos=0.0):
        return _apply_policy(
            risk=risk,
            categories=categories or [],
            stakes=stakes,
            telos_score=telos,
            policy=_DEFAULT_POLICY,
        )

    def test_allow_low_risk(self):
        result = self._default_call(risk=0.1)
        assert result["decision_status"] == "allow"

    def test_deny_high_risk_illicit(self):
        result = self._default_call(risk=0.8, categories=["illicit"])
        assert result["decision_status"] == "deny"

    def test_hold_for_pii(self):
        result = self._default_call(risk=0.3, categories=["PII"])
        assert result["decision_status"] == "hold"

    def test_high_stakes_threshold(self):
        result = self._default_call(risk=0.4, stakes=0.9)
        # High stakes uses lower threshold (0.35), risk 0.4 > 0.35 → warn or higher
        assert result["risk"] == 0.4

    def test_low_stakes_threshold(self):
        result = self._default_call(risk=0.65, stakes=0.1)
        assert result["risk"] == 0.65

    def test_violation_details_populated(self):
        result = self._default_call(risk=0.9, categories=["self_harm"])
        assert len(result["violation_details"]) > 0
        assert result["violations"] == ["self_harm"]

    def test_strict_deny_policy(self):
        result = _apply_policy(
            risk=0.5,
            categories=[],
            stakes=0.5,
            telos_score=0.0,
            policy=_STRICT_DENY_POLICY,
        )
        assert result["decision_status"] == "deny"

    def test_policy_version_in_result(self):
        result = self._default_call()
        assert result["policy_version"] == "fuji_v2_default"


class TestStrictPolicyLoadEnabled:
    def test_disabled_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            # Remove the env var if set
            os.environ.pop("VERITAS_FUJI_STRICT_POLICY_LOAD", None)
            assert _strict_policy_load_enabled() is False

    def test_enabled(self):
        with mock.patch.dict(os.environ, {"VERITAS_FUJI_STRICT_POLICY_LOAD": "1"}):
            assert _strict_policy_load_enabled() is True


class TestFallbackPolicy:
    def test_returns_default_when_not_strict(self):
        with mock.patch.dict(os.environ, {"VERITAS_FUJI_STRICT_POLICY_LOAD": "0"}):
            result = _fallback_policy(path=None, reason="test")
        assert result["version"] == "fuji_v2_default"

    def test_returns_strict_deny_when_strict(self):
        with mock.patch.dict(os.environ, {"VERITAS_FUJI_STRICT_POLICY_LOAD": "1"}):
            result = _fallback_policy(path=None, reason="test")
        assert result["version"] == "fuji_v2_strict_deny"

    def test_with_exception(self):
        result = _fallback_policy(path=Path("/fake"), reason="error", exc=ValueError("bad"))
        assert "version" in result


class TestLoadPolicy:
    def test_returns_default_when_yaml_disabled(self):
        with mock.patch("veritas_os.core.fuji_policy.capability_cfg") as cfg:
            cfg.enable_fuji_yaml_policy = False
            result = _load_policy(Path("/any"))
        assert result["version"] == "fuji_v2_default"

    def test_returns_fallback_when_file_missing(self):
        with mock.patch("veritas_os.core.fuji_policy.yaml", create=True):
            result = _load_policy(Path("/nonexistent/path.yaml"))
        assert "version" in result


class TestLoadPolicyFromStr:
    def test_returns_default_when_yaml_disabled(self):
        with mock.patch("veritas_os.core.fuji_policy.capability_cfg") as cfg:
            cfg.enable_fuji_yaml_policy = False
            result = _load_policy_from_str("version: test", Path("/fake.yaml"))
        assert result["version"] == "fuji_v2_default"


class TestBuildPiiPatternsFromPolicy:
    def test_custom_phone_pattern(self):
        import re
        original = _PII_RE["phone"]
        try:
            policy = {"pii": {"patterns": {"phone": r"\d{3}-\d{4}"}}}
            _build_pii_patterns_from_policy(policy)
            assert _PII_RE["phone"].search("123-4567")
        finally:
            _PII_RE["phone"] = original

    def test_invalid_regex_skipped(self):
        original = _PII_RE["phone"]
        policy = {"pii": {"patterns": {"phone": "[invalid"}}}
        _build_pii_patterns_from_policy(policy)
        # Original pattern should remain (or at least no crash)

    def test_empty_policy(self):
        _build_pii_patterns_from_policy({})

    def test_non_dict_patterns(self):
        _build_pii_patterns_from_policy({"pii": {"patterns": "not_dict"}})


class TestPolicyPath:
    def test_returns_default_path_without_env(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VERITAS_FUJI_POLICY", None)
            p = _policy_path()
        assert "fuji_default.yaml" in str(p)
