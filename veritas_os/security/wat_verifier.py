"""Strict local admissibility verifier for WAT tokens.

This module is intentionally local and self-contained. It performs claim-level
verification and returns a structured result contract that can be consumed by
higher layers without wiring into runtime API routes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, MutableSet, Sequence

from veritas_os.security.hash import canonical_json_dumps, sha256_hex
from veritas_os.security.signing import Signer
from veritas_os.security.wat_token import compute_observable_digests, verify_wat_signature

ValidationStatus = str
AdmissibilityState = str

_DEFAULT_THRESHOLDS: dict[str, float] = {
    "healthy": 0.2,
    "critical": 0.5,
}

_DEFAULT_WEIGHTS: dict[str, float] = {
    "policy": 0.4,
    "signature": 0.3,
    "observable": 0.2,
    "temporal": 0.1,
}


@dataclass(frozen=True)
class DriftVector:
    """Per-axis drift levels in the range ``[0.0, 1.0]``."""

    policy_drift: float
    signature_drift: float
    observable_drift: float
    temporal_drift: float


@dataclass(frozen=True)
class DriftScore:
    """Weighted drift score and classification."""

    score: float
    classification: str


@dataclass(frozen=True)
class VerifierResult:
    """Structured result contract for local WAT admissibility decisions."""

    validation_status: ValidationStatus
    admissibility_state: AdmissibilityState
    failure_type: str | None
    drift_vector: DriftVector
    audit_event_ref: str
    mission_control_event_name: str
    operator_message: str

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe dictionary representation."""
        return asdict(self)


def score_drift(
    drift_vector: DriftVector,
    weights: Mapping[str, float] | None = None,
    thresholds: Mapping[str, float] | None = None,
) -> DriftScore:
    """Compute weighted drift score and severity classification.

    Classification bands:
    - ``healthy``: score < healthy threshold.
    - ``warning``: healthy threshold <= score < critical threshold.
    - ``critical``: score >= critical threshold.
    """
    applied_weights = dict(_DEFAULT_WEIGHTS)
    if weights:
        applied_weights.update(weights)
    applied_thresholds = dict(_DEFAULT_THRESHOLDS)
    if thresholds:
        applied_thresholds.update(thresholds)

    healthy_threshold = float(applied_thresholds["healthy"])
    critical_threshold = float(applied_thresholds["critical"])
    if critical_threshold < healthy_threshold:
        healthy_threshold, critical_threshold = critical_threshold, healthy_threshold

    score = (
        drift_vector.policy_drift * applied_weights["policy"]
        + drift_vector.signature_drift * applied_weights["signature"]
        + drift_vector.observable_drift * applied_weights["observable"]
        + drift_vector.temporal_drift * applied_weights["temporal"]
    )

    if score < healthy_threshold:
        classification = "healthy"
    elif score < critical_threshold:
        classification = "warning"
    else:
        classification = "critical"
    return DriftScore(score=score, classification=classification)


def resolve_admissibility_state(
    *,
    validation_status: ValidationStatus,
    drift_score: DriftScore,
    partial_allowed: bool,
    pending_is_warning: bool = True,
) -> AdmissibilityState:
    """Resolve admissibility state from status and drift posture."""
    if validation_status in {"invalid", "stale", "revoked_confirmed"}:
        return "non_admissible"
    if validation_status == "partial":
        return "warning_only_shadow" if partial_allowed else "non_admissible"
    if validation_status == "revoked_pending":
        return "warning_only_shadow" if pending_is_warning else "non_admissible"
    if drift_score.classification in {"warning", "critical"}:
        return "warning_only_shadow"
    return "admissible"


def build_operator_message(result: VerifierResult) -> str:
    """Build a concise human-readable operator message."""
    if result.failure_type:
        return (
            f"WAT local verification status={result.validation_status}; "
            f"failure={result.failure_type}; admissibility={result.admissibility_state}."
        )
    return (
        f"WAT local verification status={result.validation_status}; "
        f"admissibility={result.admissibility_state}."
    )


def _to_epoch(ts: Any) -> int | None:
    if ts is None:
        return None
    if isinstance(ts, int):
        return ts
    if isinstance(ts, float):
        return int(ts)
    return int(str(ts))


def _derive_revocation_status(revocation_state: Any) -> str:
    if revocation_state is None:
        return "active"
    if isinstance(revocation_state, str):
        return revocation_state
    if isinstance(revocation_state, Mapping):
        value = revocation_state.get("status")
        if isinstance(value, str):
            return value
    return "active"


def _normalize_observable_digest_list(raw_value: Any) -> list[str] | None:
    """Normalize observable digest list claim values for strict comparison."""
    if raw_value is None:
        return None
    if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes, bytearray)):
        return None
    return [str(item) for item in raw_value]


def _is_partial_allowed(config: Mapping[str, Any], now_ts: int) -> bool:
    observer_only_mode = bool(config.get("observer_only_mode", False))
    if not observer_only_mode:
        return False
    warning_only_until = _to_epoch(config.get("warning_only_until"))
    if warning_only_until is None:
        return False
    return now_ts <= warning_only_until


def _verify_signature_local(
    *,
    claims: Mapping[str, Any],
    signature_b64: str,
    signer: Signer | None,
    config: Mapping[str, Any],
) -> bool:
    verifier = config.get("signature_verifier")
    if callable(verifier):
        return bool(verifier(claims, signature_b64))
    if signer is None:
        return False
    try:
        return verify_wat_signature(claims, signature_b64, signer)
    except Exception:
        return False


def _build_audit_event_ref(
    *,
    validation_status: str,
    failure_type: str | None,
    binding_key: str,
) -> str:
    event_digest = sha256_hex(
        canonical_json_dumps(
            {
                "validation_status": validation_status,
                "failure_type": failure_type,
                "binding_key": binding_key,
            }
        )
    )
    return f"wat_local_verifier:{event_digest[:24]}"


def _is_missing_text(value: Any) -> bool:
    """Return ``True`` when a replay-binding text field is missing."""
    return not str(value or "").strip()


def _resolve_replay_binding_failure(
    *,
    required: bool,
    claim_action_digest: str,
    action_digest_local: str,
    claim_nonce: str,
    execution_nonce: str,
    claim_session_id: str,
    session_id: str,
) -> str | None:
    """Resolve replay-binding failures for strict and observer-only modes.

    Strict mode requires action-digest + nonce + session-id to all exist and
    match exactly. Observer-only mode keeps historical behavior by rejecting
    only explicit mismatches.
    """
    claim_missing = {
        "action_digest": _is_missing_text(claim_action_digest),
        "nonce": _is_missing_text(claim_nonce),
        "session_id": _is_missing_text(claim_session_id),
    }
    local_missing = {
        "action_digest": _is_missing_text(action_digest_local),
        "nonce": _is_missing_text(execution_nonce),
        "session_id": _is_missing_text(session_id),
    }

    if required:
        missing_any = any(claim_missing.values()) or any(local_missing.values())
        if missing_any:
            missing_count = sum(claim_missing.values()) + sum(local_missing.values())
            return "replay_binding_missing" if missing_count >= 4 else "replay_binding_incomplete"

    if claim_action_digest != action_digest_local:
        return "action_digest_mismatch"
    if claim_nonce != execution_nonce or claim_session_id != session_id:
        return "replay_binding_incomplete" if required else "replay_detected"
    return None


def validate_local(
    *,
    signed_wat: Mapping[str, Any],
    psid_full_local: str,
    action_digest_local: str,
    observable_refs_local: Sequence[object] | None,
    observable_digest_local: str,
    issuance_ts_local: int | None,
    expiry_ts_local: int | None,
    execution_nonce: str,
    session_id: str,
    revocation_state: str | Mapping[str, Any] | None,
    config: Mapping[str, Any] | None = None,
    signer: Signer | None = None,
    now_ts: int | None = None,
    replay_cache: MutableSet[str] | None = None,
) -> dict[str, Any]:
    """Validate a signed WAT locally and return structured contract output.

    Security warning:
        This verifier enforces replay protection using
        ``action_digest + nonce + session_id``. Callers should provide a durable
        replay cache in production to avoid process-restart replay windows.
    """
    cfg = dict(config or {})
    current_ts = now_ts if now_ts is not None else int(datetime.now(tz=timezone.utc).timestamp())

    claims = signed_wat.get("claims") if isinstance(signed_wat, Mapping) else None
    signature_b64 = signed_wat.get("signature") if isinstance(signed_wat, Mapping) else None
    if not isinstance(claims, Mapping) or not isinstance(signature_b64, str):
        drift_vector = DriftVector(0.0, 1.0, 0.0, 0.0)
        result = VerifierResult(
            validation_status="invalid",
            admissibility_state="non_admissible",
            failure_type="malformed_signed_wat",
            drift_vector=drift_vector,
            audit_event_ref=_build_audit_event_ref(
                validation_status="invalid",
                failure_type="malformed_signed_wat",
                binding_key="malformed",
            ),
            mission_control_event_name="wat.local.invalid",
            operator_message="WAT local verification status=invalid; "
            "failure=malformed_signed_wat; admissibility=non_admissible.",
        )
        return result.to_dict()

    claim_psid_full = str(claims.get("psid_full", ""))
    claim_action_digest = str(claims.get("action_digest", ""))
    claim_observable_digest = str(claims.get("observable_digest", ""))
    claim_observable_digest_list = _normalize_observable_digest_list(
        claims.get("observable_digest_list")
    )
    claim_issuance_ts = _to_epoch(claims.get("issuance_ts"))
    claim_expiry_ts = _to_epoch(claims.get("expiry_ts"))
    claim_nonce = str(claims.get("nonce", ""))
    claim_session_id = str(claims.get("session_id", ""))

    binding_key = f"{claim_action_digest}:{execution_nonce}:{session_id}"
    revocation_status = _derive_revocation_status(revocation_state)
    partial_allowed = _is_partial_allowed(cfg, current_ts)
    replay_binding_required = bool(cfg.get("replay_binding_required", False))

    if revocation_status == "revoked_confirmed":
        drift_vector = DriftVector(1.0, 0.0, 0.0, 0.0)
        status = "revoked_confirmed"
        failure_type = "revoked_confirmed"
    elif not _verify_signature_local(
        claims=claims,
        signature_b64=signature_b64,
        signer=signer,
        config=cfg,
    ):
        drift_vector = DriftVector(0.0, 1.0, 0.0, 0.0)
        status = "invalid"
        failure_type = "signature_invalid"
    elif claim_psid_full != psid_full_local:
        drift_vector = DriftVector(1.0, 0.0, 0.0, 0.0)
        status = "invalid"
        failure_type = "psid_full_mismatch"
    else:
        replay_binding_failure = _resolve_replay_binding_failure(
            required=replay_binding_required,
            claim_action_digest=claim_action_digest,
            action_digest_local=action_digest_local,
            claim_nonce=claim_nonce,
            execution_nonce=execution_nonce,
            claim_session_id=claim_session_id,
            session_id=session_id,
        )
        if replay_binding_failure is not None:
            drift_vector = DriftVector(1.0, 0.0, 0.0, 0.0)
            status = "invalid"
            failure_type = replay_binding_failure
        elif claim_observable_digest != observable_digest_local:
            drift_vector = DriftVector(0.0, 0.0, 1.0, 0.0)
            status = "invalid"
            failure_type = "observable_digest_mismatch"
        elif observable_refs_local is not None and claim_observable_digest_list is not None:
            local_observable_digest_list = compute_observable_digests(observable_refs_local)
            if claim_observable_digest_list != local_observable_digest_list:
                drift_vector = DriftVector(0.0, 0.0, 1.0, 0.0)
                status = "invalid"
                failure_type = "observable_digest_list_mismatch"
            elif replay_cache is not None and binding_key in replay_cache:
                drift_vector = DriftVector(1.0, 0.0, 0.0, 0.0)
                status = "invalid"
                failure_type = "replay_detected"
            elif claim_expiry_ts is not None and current_ts > claim_expiry_ts:
                drift_vector = DriftVector(0.0, 0.0, 0.0, 1.0)
                status = "stale"
                failure_type = "expired_token"
            elif revocation_status == "revoked_pending":
                drift_vector = DriftVector(0.6, 0.0, 0.0, 0.0)
                status = "revoked_pending"
                failure_type = "revocation_pending"
            elif bool(cfg.get("allow_partial_validation", False)):
                drift_vector = DriftVector(0.3, 0.0, 0.0, 0.0)
                status = "partial"
                failure_type = "partial_validation_mode"
            else:
                temporal_drift = 0.0
                failure_type = None
                skew_tolerance = int(cfg.get("timestamp_skew_tolerance_seconds", 30))
                if issuance_ts_local is not None and claim_issuance_ts is not None:
                    if abs(claim_issuance_ts - issuance_ts_local) > skew_tolerance:
                        temporal_drift = 1.0
                        failure_type = "timestamp_skew_exceeded"
                if expiry_ts_local is not None and claim_expiry_ts is not None:
                    if abs(claim_expiry_ts - expiry_ts_local) > skew_tolerance:
                        temporal_drift = max(temporal_drift, 1.0)
                        failure_type = failure_type or "timestamp_skew_exceeded"
                if temporal_drift == 0.0 and issuance_ts_local is not None and claim_issuance_ts is not None:
                    if claim_issuance_ts != issuance_ts_local:
                        temporal_drift = 0.4
                        failure_type = "timestamp_skew_within_tolerance"
                drift_vector = DriftVector(0.0, 0.0, 0.0, temporal_drift)
                status = "invalid" if failure_type == "timestamp_skew_exceeded" else "valid"
        elif replay_cache is not None and binding_key in replay_cache:
            drift_vector = DriftVector(1.0, 0.0, 0.0, 0.0)
            status = "invalid"
            failure_type = "replay_detected"
        elif claim_expiry_ts is not None and current_ts > claim_expiry_ts:
            drift_vector = DriftVector(0.0, 0.0, 0.0, 1.0)
            status = "stale"
            failure_type = "expired_token"
        elif revocation_status == "revoked_pending":
            drift_vector = DriftVector(0.6, 0.0, 0.0, 0.0)
            status = "revoked_pending"
            failure_type = "revocation_pending"
        elif bool(cfg.get("allow_partial_validation", False)):
            drift_vector = DriftVector(0.3, 0.0, 0.0, 0.0)
            status = "partial"
            failure_type = "partial_validation_mode"
        else:
            temporal_drift = 0.0
            failure_type = None
            skew_tolerance = int(cfg.get("timestamp_skew_tolerance_seconds", 30))
            if issuance_ts_local is not None and claim_issuance_ts is not None:
                if abs(claim_issuance_ts - issuance_ts_local) > skew_tolerance:
                    temporal_drift = 1.0
                    failure_type = "timestamp_skew_exceeded"
            if expiry_ts_local is not None and claim_expiry_ts is not None:
                if abs(claim_expiry_ts - expiry_ts_local) > skew_tolerance:
                    temporal_drift = max(temporal_drift, 1.0)
                    failure_type = failure_type or "timestamp_skew_exceeded"
            if temporal_drift == 0.0 and issuance_ts_local is not None and claim_issuance_ts is not None:
                if claim_issuance_ts != issuance_ts_local:
                    temporal_drift = 0.4
                    failure_type = "timestamp_skew_within_tolerance"
            drift_vector = DriftVector(0.0, 0.0, 0.0, temporal_drift)
            status = "invalid" if failure_type == "timestamp_skew_exceeded" else "valid"

    if replay_cache is not None and status in {"valid", "partial", "revoked_pending"}:
        replay_cache.add(binding_key)

    drift_score = score_drift(
        drift_vector,
        cfg.get("drift_weights"),
        cfg.get("drift_thresholds"),
    )
    admissibility_state = resolve_admissibility_state(
        validation_status=status,
        drift_score=drift_score,
        partial_allowed=partial_allowed,
        pending_is_warning=bool(cfg.get("degrade_on_pending", True)),
    )

    if status == "partial" and not partial_allowed:
        failure_type = "partial_validation_timebox_expired"

    event_name = f"wat.local.{status}"
    result = VerifierResult(
        validation_status=status,
        admissibility_state=admissibility_state,
        failure_type=failure_type,
        drift_vector=drift_vector,
        audit_event_ref=_build_audit_event_ref(
            validation_status=status,
            failure_type=failure_type,
            binding_key=binding_key,
        ),
        mission_control_event_name=event_name,
        operator_message="",
    )
    operator_message = build_operator_message(result)
    result = VerifierResult(
        validation_status=result.validation_status,
        admissibility_state=result.admissibility_state,
        failure_type=result.failure_type,
        drift_vector=result.drift_vector,
        audit_event_ref=result.audit_event_ref,
        mission_control_event_name=result.mission_control_event_name,
        operator_message=operator_message,
    )
    return result.to_dict()
