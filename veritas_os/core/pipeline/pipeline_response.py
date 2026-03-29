# veritas_os/core/pipeline_response.py
# -*- coding: utf-8 -*-
"""
Pipeline response assembly stage.

Builds the final response dict from :class:`PipelineContext` and
coerces it to DecideResponse.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

try:
    from pydantic import ValidationError as _PydanticValidationError
except ImportError:  # pragma: no cover - pydantic is optional at core layer
    _PydanticValidationError = None  # type: ignore[assignment,misc]

from .pipeline_types import PipelineContext
from .pipeline_evidence import _norm_evidence_item, _dedupe_evidence
from .pipeline_helpers import _warn

logger = logging.getLogger(__name__)

# Top-level /v1/decide response groups.
# These constants document the payload layering without changing runtime behavior.
CORE_DECISION_FIELDS = (
    "ok",
    "error",
    "request_id",
    "query",
    "chosen",
    "alternatives",
    "evidence",
    "critique",
    "debate",
    "telos_score",
    "fuji",
    "gate",
    "values",
    "persona",
    "version",
    "decision_status",
    "rejection_reason",
)

AUDIT_DEBUG_INTERNAL_FIELDS = (
    "extras",
    "plan",
    "planner",
    "trust_log",
    "memory_citations",
    "memory_used_count",
)

BACKWARD_COMPAT_FIELDS = (
    "options",
)


def _build_response_layers(
    ctx: PipelineContext,
    *,
    load_persona_fn: Any,
    plan: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Build grouped payload layers for readability and maintenance.

    Layering is documentation-oriented: callers still receive one flat dict.
    """
    core = {
        "ok": True,
        "error": None,
        "request_id": ctx.request_id,
        "query": ctx.query,
        "chosen": ctx.chosen,
        "alternatives": ctx.alternatives,
        "evidence": ctx.evidence,
        "critique": ctx.critique,
        "debate": ctx.debate,
        "telos_score": float(ctx.telos),
        "fuji": ctx.fuji_dict,
        "gate": {
            "risk": float(ctx.effective_risk),
            "telos_score": float(ctx.telos),
            "decision_status": ctx.decision_status,
            "reason": ctx.rejection_reason,
            "modifications": ctx.modifications,
        },
        "values": ctx.values_payload,
        "persona": load_persona_fn(),
        "version": os.getenv("VERITAS_API_VERSION", "veritas-api 1.x"),
        "decision_status": ctx.decision_status,
        "rejection_reason": ctx.rejection_reason,
    }

    audit_debug_internal = {
        "extras": ctx.response_extras,
        "memory_citations": ctx.response_extras.get("memory_citations", []),
        "memory_used_count": ctx.response_extras.get("memory_used_count", 0),
        "plan": plan,
        "planner": ctx.response_extras.get("planner", {"steps": [], "raw": None, "source": "fallback"}),
        "trust_log": ctx.raw.get("trust_log") if isinstance(ctx.raw, dict) else None,
    }

    backward_compat = {
        # Legacy alias kept for historical clients; mirrors alternatives.
        "options": list(ctx.alternatives),
    }
    return {
        "core": core,
        "audit_debug_internal": audit_debug_internal,
        "backward_compat": backward_compat,
    }


def assemble_response(
    ctx: PipelineContext,
    *,
    load_persona_fn: Any,
    plan: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the DecideResponse‑compatible dict from pipeline context."""
    layers = _build_response_layers(ctx, load_persona_fn=load_persona_fn, plan=plan)
    # Flattened payload keeps pre-existing top-level contract/shape for clients.
    res: Dict[str, Any] = {}
    res.update(layers["core"])
    res.update(layers["audit_debug_internal"])
    res.update(layers["backward_compat"])

    # Continuation runtime shadow output (flag on only; omitted entirely when off)
    if ctx.continuation_snapshot is not None and ctx.continuation_receipt is not None:
        res["continuation"] = {
            "state": ctx.continuation_snapshot,
            "receipt": ctx.continuation_receipt,
        }

    return res


def coerce_to_decide_response(
    res: Dict[str, Any],
    *,
    DecideResponse: Any,
) -> Dict[str, Any]:
    """Coerce dict to DecideResponse model (best‑effort)."""
    _exc_types: tuple = (ValueError, TypeError)
    if _PydanticValidationError is not None:
        _exc_types = (ValueError, TypeError, _PydanticValidationError)
    try:
        payload = DecideResponse.model_validate(res).model_dump()
    except _exc_types as e:
        _warn(f"[model] decide response coerce: {e}")
        payload = res
    return payload


def finalize_evidence(
    payload: Dict[str, Any],
    *,
    web_evidence: Any,
    evidence_max: int,
) -> None:
    """Ensure evidence survives later overwrites, dedupe and cap."""
    try:
        payload_evidence = payload.get("evidence", None)
        if not isinstance(payload_evidence, list):
            try:
                payload_evidence = list(payload_evidence or [])
            except (KeyError, TypeError, AttributeError):
                payload_evidence = []

        if len(payload_evidence) == 0:
            evidence = payload.get("_pipeline_evidence")
            if isinstance(evidence, list) and evidence:
                payload_evidence = list(evidence)
            else:
                payload_evidence = []

        existing = set()
        for ev in payload_evidence:
            if not isinstance(ev, dict):
                continue
            existing.add((ev.get("source"), ev.get("uri"), ev.get("title"), ev.get("snippet")))

        for ev in web_evidence or []:
            if not isinstance(ev, dict):
                continue
            k = (ev.get("source"), ev.get("uri"), ev.get("title"), ev.get("snippet"))
            if k not in existing:
                payload_evidence.append(ev)
                existing.add(k)

        payload["evidence"] = payload_evidence
    except (KeyError, TypeError, AttributeError):
        payload["evidence"] = (
            payload.get("evidence") if isinstance(payload.get("evidence"), list) else []
        )

    # normalize / dedupe / cap
    try:
        payload["evidence"] = _dedupe_evidence(
            [ev for ev in (_norm_evidence_item(x) for x in (payload.get("evidence") or [])) if ev]
        )
    except (KeyError, TypeError, AttributeError):
        payload["evidence"] = []

    if isinstance(payload.get("evidence"), list) and len(payload["evidence"]) > evidence_max:
        payload["evidence"] = payload["evidence"][:evidence_max]
