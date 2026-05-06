"""Read-only observability capability endpoints."""
from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, Depends

from veritas_os.api.auth import require_permission
from veritas_os.api.rbac import Permission
from veritas_os.observability import tracing

router = APIRouter()


def _resolve_log_format() -> str:
    """Resolve structured logging format without exposing raw config values."""
    desired = (os.getenv("VERITAS_LOG_FORMAT", "text") or "text").strip().lower()
    if desired in {"json", "text"}:
        return desired
    if not desired:
        return "unknown"
    return "text"


def _is_exporter_configured() -> bool:
    """Return True when any safe exporter env signal is present."""
    candidate_vars = (
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_SERVICE_NAME",
        "OTEL_TRACES_EXPORTER",
    )
    return any(bool((os.getenv(name) or "").strip()) for name in candidate_vars)


@router.get(
    "/v1/observability/capabilities",
    dependencies=[Depends(require_permission(Permission.governance_read))],
)
def observability_capabilities() -> Dict[str, Any]:
    """Return runtime observability capabilities as a read-only snapshot."""
    opentelemetry_importable = tracing.otel_trace is not None

    return {
        "ok": True,
        "observability": {
            "structured_logging": {
                "available": True,
                "format": _resolve_log_format(),
                "trace_id_supported": True,
            },
            "tracing": {
                "helper_available": True,
                "opentelemetry_importable": opentelemetry_importable,
                "exporter_configured": _is_exporter_configured(),
                "no_op_fallback": True,
                "governance_span_chain": True,
                "rbac_denial_events": True,
                "rbac_denial_audit_append_visibility": True,
            },
            "human_approval": {
                "workbench_frontend_supported": True,
                "post_approval_edit_invalidation": True,
                "cryptographic_signature": False,
            },
            "docs": {
                "governance_trace_span_chain_en": "docs/en/operations/governance-trace-span-chain.md",
                "governance_trace_span_chain_ja": "docs/ja/operations/governance-trace-span-chain.md",
            },
            "non_goals_currently_not_configured": [
                "jaeger_deployment",
                "grafana_tempo_dashboard",
                "otlp_exporter_configuration",
                "production_collector",
                "frontend_visual_trace_viewer",
            ],
        },
    }
