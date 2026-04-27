# veritas_os/api/routes_decide.py
"""Decision pipeline, replay, and FUJI validation endpoints.

Route handlers are intentionally kept thin ("controller" style).
Business logic for failure handling, event publishing, compliance
stops, and response coercion/validation lives in
:mod:`~veritas_os.api.decide_service` and :mod:`~veritas_os.api.utils`.
"""
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from veritas_os.api.auth import require_permission
from veritas_os.api.governance import get_policy
from veritas_os.api.rbac import Permission
from veritas_os.api.schemas import DecideRequest, DecideResponse, FujiDecision
from veritas_os.api.pipeline_orchestrator import resolve_dynamic_steps
from veritas_os.audit.wat_events import (
    derive_latest_revocation_state,
    format_event_ts_utc,
    persist_wat_issuance_event,
    persist_wat_replay_event,
    persist_wat_validation_event,
)
from veritas_os.security.wat_token import (
    WAT_VERSION_V1,
    build_wat_claims,
    compute_action_digest,
    compute_observable_digests,
    compute_observable_digest,
    make_psid_display,
    sign_wat,
)
from veritas_os.security.wat_verifier import validate_local
from veritas_os.security.signing import Signer, build_trustlog_signer
from veritas_os.logging.paths import LOG_DIR
from veritas_os.api.utils import (
    _classify_decide_failure,
    _coerce_decide_payload,
    _coerce_fuji_payload,
    _errstr,
    _is_debug_mode,
    _is_direct_fuji_api_enabled,
    _log_decide_failure,
    _stage_summary,
    DECIDE_GENERIC_ERROR,
)
from veritas_os.api.constants import DECISION_REJECTED
from veritas_os.api import decide_service as _svc

logger = logging.getLogger(__name__)

try:
    from veritas_os.observability.metrics import record_decide, set_telos_score
except Exception:  # pragma: no cover - optional observability dependency
    def record_decide(status: Any, mode: Any, intent: Any, duration_seconds: float | None = None) -> None:
        return None

    def set_telos_score(user_id: Any, score: Any) -> None:
        return None

router = APIRouter()

# Rejection status set, shared across handlers.
# DECISION_REJECTED is "rejected" (lowercase) — the .lower() comparison
# in check_fuji_rejection handles any casing from pipeline output.
_REJECTED_STATUSES: set[str] = {"reject", "rejected", DECISION_REJECTED}


def _get_server():
    """Late import to avoid circular dependency at module load time."""
    from veritas_os.api import server as srv
    return srv


def _resolve_candidate_action(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve a stable candidate action envelope from a decide payload."""
    decision = payload.get("decision")
    business_decision = payload.get("business_decision")
    return {
        "decision": decision,
        "business_decision": business_decision,
        "selected_option": payload.get("selected_option"),
    }


def _derive_psid_full(
    *,
    request_id: str,
    query: str,
    candidate_action: Dict[str, Any],
) -> str:
    """Derive policy-scoped identifier seed for observer-only shadow lane."""
    material = {
        "request_id": request_id,
        "query": query,
        "candidate_action": candidate_action,
    }
    encoded = repr(material).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _build_shadow_observables(payload: Dict[str, Any]) -> list[Any]:
    """Build observable reference list for WAT digesting, preserving missing pointers."""
    trust_log = payload.get("trust_log")
    if isinstance(trust_log, dict):
        pointers = trust_log.get("pointers")
        if isinstance(pointers, list):
            return pointers
    evidence = payload.get("evidence")
    if isinstance(evidence, list):
        return evidence
    return []


def _coerce_warning_only_until_epoch(value: Any) -> int | None:
    """Coerce shadow validation warning horizon to epoch seconds when possible."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    return None


def _policy_section(policy: Dict[str, Any], key: str) -> Dict[str, Any]:
    """Return a policy subsection as dict, falling back to empty mapping."""
    section = policy.get(key)
    if isinstance(section, dict):
        return section
    return {}


def _build_drift_runtime_config(drift_scoring_cfg: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    """Build verifier drift runtime config from governance policy values.

    The local verifier consumes normalized axis names:
    ``policy``, ``signature``, ``observable``, and ``temporal``.
    """

    def _safe_float(value: Any, default: float) -> float:
        """Defensively coerce numeric policy values to float defaults."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    return {
        "drift_weights": {
            "policy": _safe_float(drift_scoring_cfg.get("policy_weight"), 0.4),
            "signature": _safe_float(drift_scoring_cfg.get("signature_weight"), 0.3),
            "observable": _safe_float(drift_scoring_cfg.get("observable_weight"), 0.2),
            "temporal": _safe_float(drift_scoring_cfg.get("temporal_weight"), 0.1),
        },
        "drift_thresholds": {
            "healthy": _safe_float(drift_scoring_cfg.get("healthy_threshold"), 0.2),
            "critical": _safe_float(drift_scoring_cfg.get("critical_threshold"), 0.5),
        },
    }




def _build_wat_signer_metadata(signer: Signer) -> Dict[str, Any]:
    """Build normalized signer metadata embedded into WAT claims."""
    return {
        "signer_type": signer.signer_type,
        "signer_key_id": signer.signer_key_id(),
        "signer_key_version": signer.signer_key_version(),
        "signature_algorithm": signer.signature_algorithm(),
        "public_key_fingerprint": signer.public_key_fingerprint(),
    }


def _resolve_wat_shadow_signer(wat_cfg: Dict[str, Any]) -> Signer:
    """Resolve shadow-lane WAT signer using existing signing abstraction."""
    keys_dir = Path(LOG_DIR) / "keys"
    backend_raw = str(wat_cfg.get("signer_backend", "existing_signer")).strip().lower()
    backend = None if backend_raw in {"", "existing_signer"} else backend_raw
    ensure_local_keys = backend in {None, "file", "file_ed25519"}
    return build_trustlog_signer(
        private_key_path=keys_dir / "trustlog_ed25519_private.key",
        public_key_path=keys_dir / "trustlog_ed25519_public.key",
        ensure_local_keys=ensure_local_keys,
        backend=backend,
    )


def _resolve_shadow_revocation_state(*, wat_id: str) -> Dict[str, Any]:
    """Resolve runtime revocation status from the WAT event lane source.

    Security:
        This observer uses event-lane-derived structured state as the single
        runtime source of truth and does not synthesize fallback statuses.
    """
    state = dict(derive_latest_revocation_state(wat_id))
    state["status"] = str(state.get("status", "active") or "active")
    state.setdefault("source", "wat_events")
    return state


def _build_wat_event_lane_details(
    *,
    failure_type: str,
    validation_status: str,
    revocation_state: Dict[str, Any],
    replay_binding_required: bool,
    replay_binding_escalation_threshold: int,
    partial_validation_requires_confirmation: bool,
) -> Dict[str, Any]:
    """Build structured event-lane observability detail for drill-down paths."""
    details: Dict[str, Any] = {
        "validation_status": validation_status,
    }
    replay_failure_reasons = {
        "replay_binding_missing",
        "replay_binding_incomplete",
        "action_digest_mismatch",
        "replay_detected",
    }
    if failure_type in replay_failure_reasons:
        details["replay_binding_failure"] = {
            "reason": failure_type,
            "required": replay_binding_required,
            "escalation_threshold": replay_binding_escalation_threshold,
        }
    revocation_status = str(revocation_state.get("status", "active") or "active")
    details["revocation_transition_trace"] = {
        "status": revocation_status,
        "event_type": revocation_state.get("event_type"),
        "event_id": revocation_state.get("event_id"),
        "event_ts": revocation_state.get("ts"),
        "source": revocation_state.get("source", "wat_events"),
    }
    if failure_type == "partial_validation_confirmation_required":
        details["partial_validation_confirmation_failure"] = {
            "reason": failure_type,
            "requires_confirmation": partial_validation_requires_confirmation,
            "confirmation_received": False,
        }
    return details


def _run_wat_shadow_observer(
    *,
    srv: Any,
    req: DecideRequest,
    coerced: Dict[str, Any],
) -> Dict[str, Any] | None:
    """Execute observer-only WAT issuance + strict local validation shadow hook.

    This helper is additive-only: it never mutates enforcement decisions and
    never raises into the production /v1/decide flow.
    """
    try:
        policy = get_policy()
    except Exception:
        logger.debug("WAT shadow policy load failed", exc_info=True)
        return None
    if not isinstance(policy, dict):
        return None

    wat_cfg = _policy_section(policy, "wat")
    if not bool(wat_cfg.get("enabled", False)):
        return None
    if str(wat_cfg.get("issuance_mode", "shadow_only")) != "shadow_only":
        return None

    psid_cfg = _policy_section(policy, "psid")
    shadow_cfg = _policy_section(policy, "shadow_validation")
    revocation_cfg = _policy_section(policy, "revocation")
    drift_scoring_cfg = _policy_section(policy, "drift_scoring")
    drift_runtime_cfg = _build_drift_runtime_config(drift_scoring_cfg)
    request_id = str(coerced.get("request_id") or "")
    query = str(getattr(req, "query", "") or coerced.get("query") or "")
    candidate_action = _resolve_candidate_action(coerced)
    psid_full = _derive_psid_full(
        request_id=request_id,
        query=query,
        candidate_action=candidate_action,
    )
    psid_display = make_psid_display(
        psid_full,
        display_length=int(psid_cfg.get("display_length", 12)),
    )

    observables = _build_shadow_observables(coerced)
    observable_digest_list = compute_observable_digests(observables)
    action_digest = compute_action_digest(candidate_action)
    aggregate_observable_digest = compute_observable_digest(observables)
    now_ts = int(time.time())
    ttl = int(wat_cfg.get("default_ttl_seconds", 300))
    expiry_ts = now_ts + max(1, ttl)
    wat_id = f"wat_{uuid4().hex}"

    issue_event = persist_wat_issuance_event(
        wat_id=wat_id,
        actor="api:decide_observer",
        details={
            "mode": "shadow",
            "request_id": request_id,
            "psid": psid_full,
            "psid_display": psid_display,
            "action_digest": action_digest,
            "observable_digest": aggregate_observable_digest,
            "observable_digest_list": observable_digest_list,
            "ttl_seconds": ttl,
        },
    )

    replay_cache = srv.get_wat_shadow_replay_cache()
    signer = _resolve_wat_shadow_signer(wat_cfg)
    claims = build_wat_claims(
        version=WAT_VERSION_V1,
        wat_id=wat_id,
        psid_full=psid_full,
        action_payload=candidate_action,
        observable_refs=observables,
        issuance_ts=now_ts,
        expiry_ts=expiry_ts,
        nonce=request_id or "unknown-request",
        session_id=request_id or "unknown-session",
        signer_metadata=_build_wat_signer_metadata(signer),
        psid_display_length=int(psid_cfg.get("display_length", 12)),
    )
    signed_wat = sign_wat(claims, signer)
    revocation_state = _resolve_shadow_revocation_state(wat_id=wat_id)
    effective_revocation_status = str(revocation_state.get("status", "active"))
    degrade_on_pending = bool(revocation_cfg.get("degrade_on_pending", True))
    replay_binding_escalation_threshold = int(
        shadow_cfg.get("replay_binding_escalation_threshold", 4)
    )
    partial_validation_requires_confirmation = bool(
        shadow_cfg.get("partial_validation_requires_confirmation", True)
    )

    verifier_result = validate_local(
        signed_wat=signed_wat,
        psid_full_local=psid_full,
        action_digest_local=action_digest,
        observable_refs_local=observables,
        observable_digest_local=aggregate_observable_digest,
        issuance_ts_local=now_ts,
        expiry_ts_local=expiry_ts,
        execution_nonce=request_id or "unknown-request",
        session_id=request_id or "unknown-session",
        revocation_state=revocation_state,
        config={
            "observer_only_mode": True,
            "allow_partial_validation": False,
            "degrade_on_pending": degrade_on_pending,
            "timestamp_skew_tolerance_seconds": int(
                shadow_cfg.get("timestamp_skew_tolerance_seconds", 5)
            ),
            "warning_only_until": _coerce_warning_only_until_epoch(
                shadow_cfg.get("warning_only_until")
            ),
            "replay_binding_required": shadow_cfg.get("replay_binding_required", False),
            "replay_binding_escalation_threshold": replay_binding_escalation_threshold,
            "partial_validation_requires_confirmation": partial_validation_requires_confirmation,
            "drift_weights": drift_runtime_cfg["drift_weights"],
            "drift_thresholds": drift_runtime_cfg["drift_thresholds"],
        },
        signer=signer,
        replay_cache=replay_cache,
    )

    failure_type = str(verifier_result.get("failure_type") or "")
    validation_status = str(verifier_result.get("validation_status") or "invalid")
    event_lane_details = _build_wat_event_lane_details(
        failure_type=failure_type,
        validation_status=validation_status,
        revocation_state=revocation_state,
        replay_binding_required=bool(shadow_cfg.get("replay_binding_required", False)),
        replay_binding_escalation_threshold=replay_binding_escalation_threshold,
        partial_validation_requires_confirmation=partial_validation_requires_confirmation,
    )
    if failure_type == "replay_detected":
        persisted_validation = persist_wat_replay_event(
            wat_id=wat_id,
            actor="api:decide_observer",
            details={
                "request_id": request_id,
                "psid_display": psid_display,
                "validation_status": validation_status,
                "event_lane_details": event_lane_details,
            },
        )
        replay_status = "suspected"
    else:
        event_type = "wat_validated" if validation_status == "valid" else "wat_validation_failed"
        persisted_validation = persist_wat_validation_event(
            wat_id=wat_id,
            actor="api:decide_observer",
            event_type=event_type,
            status="ok" if event_type == "wat_validated" else "warning",
            details={
                "request_id": request_id,
                "psid_display": psid_display,
                "validation_status": validation_status,
                "failure_type": failure_type or None,
                "observable_digest_list": observable_digest_list,
                "warning_context": "wat_shadow_warning" if event_type != "wat_validated" else "",
                "warning_correlation_id": request_id or str(issue_event.get("event_id") or wat_id),
                "event_lane_details": event_lane_details,
            },
        )
        replay_status = "suspected" if failure_type == "replay_detected" else "clear"

    drift_vector = verifier_result.get("drift_vector")
    integrity_summary = {
        "action_digest": action_digest,
        "observable_digest": aggregate_observable_digest,
        "observable_digest_list": observable_digest_list,
        "pointer_missing_digest_alive": bool(not observables and aggregate_observable_digest),
    }
    integrity_severity = "healthy" if validation_status == "valid" else "warning"
    if str(verifier_result.get("admissibility_state")) in {"non_admissible", "blocked"}:
        integrity_severity = "critical"
    operator_verbosity = str(policy.get("operator_verbosity") or "minimal")
    if operator_verbosity not in {"minimal", "expanded"}:
        operator_verbosity = "minimal"
    correlation_id = request_id or str(issue_event.get("event_id") or wat_id)
    warning_context = ""
    if validation_status in {"revoked_pending", "partial"} or integrity_severity == "warning":
        warning_context = "wat_shadow_warning"
        logger.warning(
            "WAT shadow warning context=%s correlation_id=%s status=%s failure_type=%s",
            warning_context,
            correlation_id,
            validation_status,
            failure_type or "",
        )
    if failure_type == "partial_validation_confirmation_required":
        logger.warning(
            "WAT shadow partial-validation confirmation failure "
            "correlation_id=%s wat_id=%s",
            correlation_id,
            wat_id,
        )
    event_ts = format_event_ts_utc(
        persisted_validation.get("event_ts") or persisted_validation.get("ts")
    )
    summary = {
        "observer_only": True,
        "operator_verbosity": operator_verbosity,
        "integrity_severity": integrity_severity,
        "affected_lanes": ["wat_shadow"],
        "event_ts": event_ts,
        "correlation_id": correlation_id,
        "wat_id": wat_id,
        "psid_display": psid_display,
        "validation_status": validation_status,
        "admissibility_state": verifier_result.get("admissibility_state"),
        "drift_vector": drift_vector,
        "replay_status": replay_status,
        "revocation_status": effective_revocation_status,
        "warning_context": warning_context,
        "warning_correlation_id": correlation_id,
        "integrity_summary": integrity_summary,
        "event_lane_details": event_lane_details,
        "issue_event_id": issue_event.get("event_id"),
        "validation_event_id": persisted_validation.get("event_id"),
    }
    try:
        srv._publish_event("wat.shadow.validation", summary)
    except Exception:
        logger.debug("wat.shadow.validation event publish failed", exc_info=True)
    return summary


def _normalize_wat_drift_vector(raw_vector: Any) -> Dict[str, float]:
    """Normalize WAT drift vector keys for the public DecideResponse contract.

    Canonical public keys are ``policy``, ``signature``, ``observable``,
    and ``temporal``. Legacy backend keys (``*_drift``) are accepted and
    mapped additively to preserve compatibility with existing producers.
    """
    if not isinstance(raw_vector, dict):
        raw_vector = {}
    key_map = {
        "policy": "policy",
        "policy_drift": "policy",
        "signature": "signature",
        "signature_drift": "signature",
        "observable": "observable",
        "observable_drift": "observable",
        "temporal": "temporal",
        "temporal_drift": "temporal",
    }
    normalized: Dict[str, float] = {}
    for source_key, target_key in key_map.items():
        if target_key in normalized:
            continue
        value = raw_vector.get(source_key)
        if isinstance(value, (int, float)):
            normalized[target_key] = float(value)
    for key in ("policy", "signature", "observable", "temporal"):
        normalized.setdefault(key, 0.0)
    return normalized


def _resolve_operator_verbosity(value: Any) -> str:
    """Resolve canonical operator verbosity with minimal-default safety."""
    verbosity = str(value or "minimal")
    if verbosity not in {"minimal", "expanded"}:
        return "minimal"
    return verbosity


def _resolve_operator_role(request: Request) -> str:
    """Resolve request RBAC role for operator-facing detail controls."""
    role = getattr(getattr(request, "state", None), "rbac_role", None)
    if isinstance(role, str) and role.strip():
        return role.strip().lower()
    return "admin"


def _build_operator_surface(
    *,
    summary: Dict[str, Any],
    detail: Optional[Dict[str, Any]],
    operator_verbosity: str,
    role: str,
    expanded_roles: set[str],
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Build minimal-default operator surface with role-gated expanded detail."""
    effective_verbosity = "expanded" if operator_verbosity == "expanded" and role in expanded_roles else "minimal"
    summary["operator_verbosity"] = effective_verbosity
    if effective_verbosity == "expanded" and isinstance(detail, dict):
        return summary, detail
    return summary, None


def _attach_wat_contract_fields(payload: Dict[str, Any], wat_shadow: Dict[str, Any]) -> None:
    """Attach additive canonical WAT fields to decide payload.

    This keeps legacy ``meta["wat_shadow"]`` intact while promoting stable,
    frontend-consumable top-level fields.
    """
    integrity_state = "healthy" if str(wat_shadow.get("validation_status")) == "valid" else "warning"
    if str(wat_shadow.get("admissibility_state")) in {"non_admissible", "blocked"}:
        integrity_state = "critical"
    payload["wat_integrity"] = {
        "integrity_state": integrity_state,
        "wat_id": wat_shadow.get("wat_id"),
        "psid_display": wat_shadow.get("psid_display"),
        "validation_status": wat_shadow.get("validation_status"),
        "admissibility_state": wat_shadow.get("admissibility_state"),
        "replay_status": wat_shadow.get("replay_status"),
        "revocation_status": wat_shadow.get("revocation_status"),
        "action_summary": "observer_only_validation",
    }
    payload["wat_drift_vector"] = _normalize_wat_drift_vector(wat_shadow.get("drift_vector"))
    operator_verbosity = _resolve_operator_verbosity(wat_shadow.get("operator_verbosity"))
    summary, detail = _build_operator_surface(
        summary={
        # v1 lock-in: intentionally minimal operator-facing default surface.
            "integrity_severity": integrity_state,
            "affected_lanes": list(wat_shadow.get("affected_lanes") or ["wat_shadow"]),
            "event_ts": format_event_ts_utc(wat_shadow.get("event_ts") or wat_shadow.get("ts")),
            "correlation_id": str(
                wat_shadow.get("correlation_id") or payload.get("request_id") or wat_shadow.get("wat_id") or ""
            ),
            "warning_context": str(wat_shadow.get("warning_context") or ""),
            "warning_correlation_id": str(
                wat_shadow.get("warning_correlation_id")
                or wat_shadow.get("correlation_id")
                or payload.get("request_id")
                or wat_shadow.get("wat_id")
                or ""
            ),
        },
        detail={
            "drift_vector": _normalize_wat_drift_vector(wat_shadow.get("drift_vector")),
            "verifier_output_raw": wat_shadow.get("verifier_output_raw"),
            "historical_drift_trend": wat_shadow.get("historical_drift_trend"),
            "event_lane_details": wat_shadow.get("event_lane_details"),
        },
        operator_verbosity=operator_verbosity,
        role="admin",
        expanded_roles={"admin"},
    )
    payload["wat_operator_summary"] = summary
    if detail is not None:
        payload["wat_operator_detail"] = detail


def _attach_bind_operator_surface(
    *,
    payload: Dict[str, Any],
    policy: Dict[str, Any],
    role: str,
) -> None:
    """Attach reusable minimal/expanded operator surface for bind governance."""
    bind_summary = payload.get("bind_summary")
    if not isinstance(bind_summary, dict):
        return
    operator_verbosity = _resolve_operator_verbosity(policy.get("operator_verbosity"))
    bind_outcome = str(payload.get("bind_outcome") or bind_summary.get("outcome") or "")
    summary, detail = _build_operator_surface(
        summary={
            "bind_state": bind_outcome.lower() or "unknown",
            "bind_outcome": bind_outcome,
            "bind_reason_code": str(payload.get("bind_reason_code") or bind_summary.get("reason_code") or ""),
            "bind_receipt_id": str(payload.get("bind_receipt_id") or bind_summary.get("bind_receipt_id") or ""),
            "execution_intent_id": str(
                payload.get("execution_intent_id") or bind_summary.get("execution_intent_id") or ""
            ),
        },
        detail={
            "authority_check_result": payload.get("authority_check_result"),
            "constraint_check_result": payload.get("constraint_check_result"),
            "drift_check_result": payload.get("drift_check_result"),
            "risk_check_result": payload.get("risk_check_result"),
        },
        operator_verbosity=operator_verbosity,
        role=role,
        expanded_roles={"admin"},
    )
    payload["bind_operator_summary"] = summary
    if detail is not None:
        payload["bind_operator_detail"] = detail


# ------------------------------------------------------------------
# /v1/decide
# ------------------------------------------------------------------

@router.post("/v1/decide", response_model=DecideResponse, dependencies=[Depends(require_permission(Permission.decide))])
async def decide(req: DecideRequest, request: Request):
    started_at = time.perf_counter()
    mode = "fast" if bool(getattr(req, "fast_mode", False)) else "normal"
    intent = "unknown"
    req_context = getattr(req, "context", None)
    if isinstance(req_context, dict):
        intent = req_context.get("intent") or intent

    def _record(status: str) -> None:
        record_decide(
            status=status,
            mode=mode,
            intent=intent,
            duration_seconds=time.perf_counter() - started_at,
        )

    srv = _get_server()
    p = srv.get_decision_pipeline()
    if p is None:
        _log_decide_failure("decision_pipeline unavailable", srv._pipeline_state.err)
        # Best-effort recovery for subsequent requests when availability is
        # temporarily degraded by test/runtime mutation of lazy state.
        if (
            getattr(srv._pipeline_state, "obj", None) is None
            and getattr(srv._pipeline_state, "attempted", False)
            and getattr(srv._pipeline_state, "err", None) is not None
        ):
            srv._pipeline_state = srv._LazyState()
        try:
            srv._publish_event("decide.completed", {"ok": False, "error": DECIDE_GENERIC_ERROR})
        except Exception:
            logger.debug("event publish failed on pipeline unavailable (best-effort)", exc_info=True)
        _record("unavailable")
        return _svc.error_response(503, error=DECIDE_GENERIC_ERROR)

    try:
        payload = await p.run_decide_pipeline(req=req, request=request)
    except Exception as e:
        failure_category = _classify_decide_failure(e)
        _log_decide_failure("decision_pipeline execution failed", e)
        try:
            srv._publish_event(
                "decide.completed",
                {"ok": False, "error": DECIDE_GENERIC_ERROR, "failure_category": failure_category},
            )
        except Exception:
            logger.debug("event publish failed on pipeline error (best-effort)", exc_info=True)
        _record("error")
        return _svc.error_response(503, error=DECIDE_GENERIC_ERROR, failure_category=failure_category)

    if isinstance(payload, dict):
        resolve_dynamic_steps(payload)
        try:
            _svc.publish_stage_events(srv._publish_event, _stage_summary, payload)
        except Exception:
            logger.debug("stage event publish failed (best-effort)", exc_info=True)

    coerced = _coerce_decide_payload(payload, seed=getattr(req, "query", "") or "")
    policy = get_policy()
    operator_role = _resolve_operator_role(request)
    _attach_bind_operator_surface(payload=coerced, policy=policy, role=operator_role)

    try:
        wat_shadow = _run_wat_shadow_observer(srv=srv, req=req, coerced=coerced)
        if wat_shadow:
            meta = coerced.get("meta")
            if not isinstance(meta, dict):
                meta = {}
                coerced["meta"] = meta
            meta["wat_shadow"] = wat_shadow
            _attach_wat_contract_fields(coerced, wat_shadow)
    except Exception:
        logger.debug("observer-only WAT shadow hook failed", exc_info=True)

    coerced, stop_response = _svc.apply_compliance_stop(coerced, srv._publish_event)
    if stop_response is not None:
        _record("compliance_stop")
        return stop_response

    try:
        _svc.publish_decide_completion(srv._publish_event, coerced)
        _svc.check_fuji_rejection(
            srv._publish_event,
            coerced.get("fuji") or {},
            rejected_statuses=_REJECTED_STATUSES,
            extra_event_fields={"request_id": coerced.get("request_id")},
        )
    except Exception:
        logger.debug("post-pipeline event publish failed (best-effort)", exc_info=True)

    fuji = coerced.get("fuji") if isinstance(coerced, dict) else {}
    status = "allow"
    if isinstance(fuji, dict):
        status = str(fuji.get("decision_status") or fuji.get("status") or status)

    user_id = getattr(getattr(request, "state", None), "user_id", None)
    if user_id is None and isinstance(req_context, dict):
        user_id = req_context.get("user_id")
    set_telos_score(user_id=user_id or "anonymous", score=coerced.get("telos_score"))
    _record(status)

    return _svc.validate_and_respond(
        DecideResponse, coerced,
        publish_fn=srv._publish_event,
        errstr_fn=_errstr,
        is_debug_fn=_is_debug_mode,
    )


# ------------------------------------------------------------------
# /v1/replay
# ------------------------------------------------------------------

@router.post("/v1/replay/{decision_id}")
async def replay_endpoint(decision_id: str, request: Request):
    """Replay one persisted decision and write replay report JSON.

    Note: This endpoint requires HMAC signature verification in addition
    to the router-level API key + rate limit dependencies.
    """
    srv = _get_server()
    # Manually invoke HMAC signature verification (originally a Depends())
    await srv.verify_signature(
        request,
        x_api_key=request.headers.get("X-API-Key"),
        x_timestamp=request.headers.get("X-Timestamp"),
        x_nonce=request.headers.get("X-Nonce"),
        x_signature=request.headers.get("X-Signature"),
        x_veritas_timestamp=request.headers.get("X-VERITAS-TIMESTAMP"),
        x_veritas_nonce=request.headers.get("X-VERITAS-NONCE"),
        x_veritas_signature=request.headers.get("X-VERITAS-SIGNATURE"),
    )
    try:
        result = await srv.run_replay(decision_id=decision_id)
    except ValueError:
        return JSONResponse(
            status_code=404,
            content={"ok": False, "decision_id": decision_id, "error": "decision_not_found"},
        )
    except Exception as e:
        logger.error("replay endpoint failed: %s", _errstr(e))
        return JSONResponse(
            status_code=500,
            content={"ok": False, "decision_id": decision_id, "error": "replay_failed"},
        )

    return {
        "ok": True,
        "decision_id": result.decision_id,
        "replay_path": result.replay_path,
        "match": result.match,
        "diff_summary": result.diff_summary,
        "replay_time_ms": result.replay_time_ms,
        "schema_version": result.schema_version,
        "severity": result.severity,
        "divergence_level": result.divergence_level,
        "audit_summary": result.audit_summary,
    }


@router.post("/v1/decision/replay/{decision_id}")
async def replay_decision_endpoint(decision_id: str, request: Request):
    """Replay a persisted decision deterministically and return diff report."""
    srv = _get_server()
    p = srv.get_decision_pipeline()
    if p is None or not hasattr(p, "replay_decision"):
        return JSONResponse(
            status_code=503,
            content={
                "match": False,
                "diff": {"error": DECIDE_GENERIC_ERROR},
                "replay_time_ms": 0,
            },
        )

    mock_external_apis = True
    try:
        qv = request.query_params.get("mock_external_apis")
        if qv is not None:
            mock_external_apis = str(qv).strip().lower() not in {"0", "false", "no", "off"}
    except Exception:
        mock_external_apis = True

    try:
        result = await p.replay_decision(
            decision_id=decision_id,
            mock_external_apis=mock_external_apis,
        )
    except Exception as e:
        logger.error("decision replay failed: %s", _errstr(e))
        return JSONResponse(
            status_code=500,
            content={
                "match": False,
                "diff": {"error": "replay_failed"},
                "replay_time_ms": 0,
            },
        )
    return result


# ------------------------------------------------------------------
# /v1/fuji/validate
# ------------------------------------------------------------------

def _call_fuji(fc: Any, action: str, context: dict) -> dict:
    """validate_action / validate の微妙なシグネチャ差を吸収する。"""
    if hasattr(fc, "validate_action"):
        fn = fc.validate_action
        try:
            return fn(action=action, context=context)
        except TypeError:
            return fn(action, context)
    if hasattr(fc, "validate"):
        fn = fc.validate
        try:
            return fn(action=action, context=context)
        except TypeError:
            try:
                return fn(action, context)
            except TypeError:
                return fn(action)
    raise RuntimeError("fuji_core has neither validate_action nor validate")


@router.post("/v1/fuji/validate", response_model=FujiDecision, dependencies=[Depends(require_permission(Permission.decide))])
def fuji_validate(payload: dict):
    srv = _get_server()
    if not _is_direct_fuji_api_enabled():
        return JSONResponse(
            status_code=403,
            content={
                "detail": (
                    "direct_fuji_api_disabled: use /v1/decide pipeline or set "
                    "VERITAS_ENABLE_DIRECT_FUJI_API=1"
                )
            },
        )

    fc = srv.get_fuji_core()
    if fc is None:
        logger.warning("fuji_validate: fuji_core unavailable: %s", srv._fuji_state.err)
        return JSONResponse(
            status_code=503,
            content={"detail": "fuji_core unavailable"}
        )

    action = str(payload.get("action", "") or "")[:10_000]
    context = payload.get("context") or {}

    try:
        result = _call_fuji(fc, action, context)
    except RuntimeError as e:
        err_msg = str(e)
        if "neither validate_action nor validate" in err_msg:
            logger.error("fuji_validate: %s", err_msg)
            return JSONResponse(
                status_code=500,
                content={"detail": "FUJI core interface error"}
            )
        logger.error("fuji_validate RuntimeError: %s", err_msg)
        return JSONResponse(
            status_code=200,
            content={"status": "error", "reasons": ["Validation failed"], "violations": []}
        )
    except Exception as e:
        logger.error("fuji_validate error: %s", _errstr(e))
        return JSONResponse(
            status_code=200,
            content={"status": "error", "reasons": ["Validation failed"], "violations": []}
        )

    coerced = _coerce_fuji_payload(result, action=action)
    _svc.check_fuji_rejection(
        srv._publish_event,
        coerced,
        rejected_statuses=_REJECTED_STATUSES,
        extra_event_fields={"action": action},
    )
    return _svc.validate_and_respond(
        FujiDecision, coerced,
        publish_fn=srv._publish_event,
        errstr_fn=_errstr,
        is_debug_fn=_is_debug_mode,
        set_ok_false=False,
    )
