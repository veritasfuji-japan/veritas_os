"""Shared helper utilities for One-Day PoC smoke/benchmark evidence packets."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

EVIDENCE_PACKET_TYPE = "veritas_one_day_poc_evidence"
EVIDENCE_SCHEMA_VERSION = "one_day_poc_evidence.v1"
EXPECTED_NON_GOALS = [
    "not_a_runtime_deployment_reference",
    "no_jaeger_grafana_tempo_otlp_deployment",
    "no_cryptographic_human_approval_signature",
    "no_new_trustlog_durability_guarantee",
]


def extract_observability_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract a sanitized observability summary from API payloads."""
    observability = payload.get("observability")
    if not isinstance(observability, dict):
        observability = {}

    structured = observability.get("structured_logging")
    if not isinstance(structured, dict):
        structured = {}

    tracing = observability.get("tracing")
    if not isinstance(tracing, dict):
        tracing = {}

    return {
        "structured_logging_format": structured.get("format"),
        "opentelemetry_importable": tracing.get("opentelemetry_importable"),
        "exporter_configured": tracing.get("exporter_configured"),
        "governance_span_chain": tracing.get("governance_span_chain"),
        "rbac_denial_audit_append_visibility": tracing.get(
            "rbac_denial_audit_append_visibility"
        ),
    }


def build_evidence_packet(
    observability: dict[str, Any],
    capabilities_status: int,
    capabilities_ok: bool,
    policy_status: int,
    warnings: list[str],
) -> dict[str, Any]:
    """Build a sanitized one-day PoC evidence packet."""
    return {
        "packet_type": EVIDENCE_PACKET_TYPE,
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "read_only": True,
        "mutation_allowed": False,
        "checks": {
            "observability_capabilities": {
                "status_code": capabilities_status,
                "ok": capabilities_ok,
                "summary": observability,
            },
            "governance_policy_read": {
                "status_code": policy_status,
                "required": False,
            },
        },
        "docs": {
            "walkthrough_en": "docs/en/poc/one-day-poc-walkthrough.md",
            "walkthrough_ja": "docs/ja/poc/one-day-poc-walkthrough.md",
            "trace_span_chain_en": "docs/en/operations/governance-trace-span-chain.md",
            "trace_span_chain_ja": "docs/ja/operations/governance-trace-span-chain.md",
        },
        "non_goals": EXPECTED_NON_GOALS,
        "warnings": warnings,
    }
