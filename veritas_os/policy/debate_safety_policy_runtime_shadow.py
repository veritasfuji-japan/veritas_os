"""Runtime-visible Debate safety YAML shadow diagnostics (Phase 3a).

This module provides optional diagnostics only. It MUST NOT alter runtime
Debate enforcement behavior.
"""

from __future__ import annotations

import os
import re
from typing import Any

from veritas_os.policy.debate_safety_policy_loader import (
    DebateSafetyPolicySchemaError,
    DebateSafetyPolicyYamlSyntaxError,
    build_debate_safety_policy_shadow_report,
    load_debate_safety_policy_from_yaml,
)

SHADOW_PATH_ENV_VAR = "VERITAS_DEBATE_SAFETY_POLICY_SHADOW_PATH"


def build_debate_safety_policy_shadow_diagnostics(
    policy_path: str | None,
    *,
    strict: bool = False,
) -> dict[str, Any]:
    """Build shadow diagnostics for an optional local YAML policy path.

    The returned diagnostics are visibility metadata only. Runtime Debate
    enforcement remains hardcoded and authoritative.
    """
    if not policy_path:
        return {
            "enabled": False,
            "status": "not_configured",
            "enforcement_authoritative": "hardcoded",
        }

    if _is_remote_url(policy_path):
        return {
            "enabled": True,
            "status": "load_error",
            "error_type": "remote_path_not_allowed",
            "sanitized_error": "Only explicit local policy paths are allowed.",
            "enforcement_authoritative": "hardcoded",
        }

    try:
        policy = load_debate_safety_policy_from_yaml(policy_path)
        report = build_debate_safety_policy_shadow_report(policy)
        return {
            "enabled": True,
            "status": "loaded",
            "policy_id": report.get("policy_id"),
            "schema_version": report.get("schema_version"),
            "mode": report.get("mode"),
            "parity_status": report.get("parity_status", "parity_unknown"),
            "yaml_category_count": report.get("yaml_category_count", 0),
            "hardcoded_category_count": report.get("hardcoded_category_count", 0),
            "missing_hardcoded_categories": report.get("missing_hardcoded_categories", []),
            "extra_yaml_categories": report.get("extra_yaml_categories", []),
            "enforcement_authoritative": "hardcoded",
        }
    except DebateSafetyPolicyYamlSyntaxError as exc:
        return _error_diagnostics("load_error", exc, strict=strict)
    except DebateSafetyPolicySchemaError as exc:
        return _error_diagnostics("schema_error", exc, strict=strict)
    except Exception as exc:  # pragma: no cover - defensive fallback
        return _error_diagnostics("parity_unknown", exc, strict=strict)


def build_debate_safety_policy_shadow_diagnostics_from_env() -> dict[str, Any]:
    """Build diagnostics from ``VERITAS_DEBATE_SAFETY_POLICY_SHADOW_PATH``."""
    return build_debate_safety_policy_shadow_diagnostics(
        os.getenv(SHADOW_PATH_ENV_VAR),
        strict=False,
    )


def _error_diagnostics(status: str, exc: Exception, *, strict: bool) -> dict[str, Any]:
    if strict:
        raise exc
    return {
        "enabled": True,
        "status": status,
        "error_type": type(exc).__name__,
        "sanitized_error": _sanitize_error_message(exc),
        "enforcement_authoritative": "hardcoded",
    }


def _sanitize_error_message(exc: Exception) -> str:
    text = str(exc).strip().replace("\n", " ")
    text = re.sub(r"[^\s]+[/\\][^\s]*", "<path>", text)
    return (text[:240] + "...") if len(text) > 240 else text


def _is_remote_url(path: str) -> bool:
    normalized = path.strip().lower()
    return normalized.startswith("http://") or normalized.startswith("https://")
