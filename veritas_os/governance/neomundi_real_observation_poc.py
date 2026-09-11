"""Reproducible NeoMundi RGC v0.2 real-observation PoC runner.

The runner composes the provider-specific NeoMundi verifier with the generic
ExternalMeasurementEvidence trust boundary. It is intentionally evidence-only:
it never creates AuthorityEvidence, HumanApproval, BindAuthorization, a
GovernanceDecision, credentials, or an external effect.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from veritas_os.governance.external_measurement_evidence import (
    ApprovedExternalMeasurementProvider,
    ExternalMeasurementProviderVerificationResult,
    ExternalMeasurementTrustPolicy,
    VerifiedExternalMeasurementEvidence,
    validate_verified_external_measurement_evidence,
    verify_external_measurement_artifact_to_evidence,
)
from veritas_os.governance.neomundi_rgc_v02 import (
    NEOMUNDI_PROVIDER_ID,
    NeoMundiRgcV02Verifier,
)
from veritas_os.security.hash import sha256_of_canonical_json

POC_MANIFEST_VERSION = "1.0"
POC_PURPOSE = "neomundi_rgc_v02_real_observation_poc"


class NeoMundiRealObservationPocError(ValueError):
    """Fail-closed PoC verification error with a serializable report."""

    def __init__(self, reason: str, *, report: dict[str, Any]) -> None:
        super().__init__(reason)
        self.reason = reason
        self.report = report


class FileExternalMeasurementReplayGuard:
    """Local-filesystem, durable single-use replay guard for PoC execution.

    Marker creation uses O_EXCL so one local filesystem namespace accepts a
    replay key only once. This is not a distributed production replay service.
    """

    def __init__(self, state_dir: str | Path) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def consume_once(self, replay_key: str, *, observed_at: datetime) -> bool:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("neomundi_poc_replay_observed_at_timezone_required")
        marker_name = hashlib.sha256(replay_key.encode("utf-8")).hexdigest() + ".json"
        marker = self.state_dir / marker_name
        payload = {
            "replay_key": replay_key,
            "observed_at": observed_at.isoformat(),
        }
        try:
            fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return False
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            # Fail closed: the marker remains consumed if persistence is partial.
            raise
        return True


@dataclass(frozen=True)
class _StaticProviderVerifier:
    """Reuse one already-computed provider verification result exactly once."""

    result: ExternalMeasurementProviderVerificationResult

    def verify(
        self, artifact: dict[str, Any]
    ) -> ExternalMeasurementProviderVerificationResult:
        del artifact
        return self.result


def _provider_result_to_dict(
    result: ExternalMeasurementProviderVerificationResult,
) -> dict[str, Any]:
    return {
        "verified": result.verified,
        "semantic_consistent": result.semantic_consistent,
        "verifier_id": result.verifier_id,
        "verifier_trust_level": result.verifier_trust_level,
        "verifier_policy_id": result.verifier_policy_id,
        "verifier_policy_hash": result.verifier_policy_hash,
        "key_id": result.key_id,
        "algorithm": result.algorithm,
        "reason": result.reason,
        "normalized_evidence": (
            result.evidence.to_dict() if result.evidence is not None else None
        ),
    }


def verified_external_measurement_to_dict(
    proof: VerifiedExternalMeasurementEvidence,
) -> dict[str, Any]:
    """Serialize the sealed generic proof without adding authority semantics."""
    return {
        "evidence": proof.evidence.to_dict(),
        "evidence_hash": proof.evidence_hash,
        "key_id": proof.key_id,
        "algorithm": proof.algorithm,
        "verifier_id": proof.verifier_id,
        "verifier_trust_level": proof.verifier_trust_level,
        "verifier_policy_id": proof.verifier_policy_id,
        "verifier_policy_hash": proof.verifier_policy_hash,
        "trust_policy_id": proof.trust_policy_id,
        "trust_policy_hash": proof.trust_policy_hash,
        "verified_at": proof.verified_at,
        "verification_reason": proof.verification_reason,
        "verification_source": proof.verification_source,
        "replay_key": proof.replay_key,
        "verification_proof_hash": proof.verification_proof_hash,
    }


def _failure_report(
    *,
    stage: str,
    reason: str,
    provider_result: ExternalMeasurementProviderVerificationResult | None = None,
) -> dict[str, Any]:
    return {
        "status": "failed",
        "stage": stage,
        "reason": reason,
        "provider_verification": (
            _provider_result_to_dict(provider_result)
            if provider_result is not None
            else None
        ),
        "claim_boundary": {
            "measurement_only": True,
            "authority_created": False,
            "human_approval_created": False,
            "bind_authorization_created": False,
            "governance_decision_created": False,
            "external_effect_performed": False,
        },
    }


def run_neomundi_real_observation_poc(
    artifact: dict[str, Any],
    *,
    trusted_jwks: dict[str, Any],
    replay_state_dir: str | Path,
    verifier_policy_id: str,
    verifier_trust_level: str,
    trust_policy_id: str,
    max_age_seconds: int,
    max_future_skew_seconds: int = 60,
    allow_no_expiry: bool = False,
    now: datetime | None = None,
    source_artifact_file_sha256: str | None = None,
    trusted_jwks_file_sha256: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Verify one RGC v0.2 observation and build reproducible PoC outputs."""
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        report = _failure_report(
            stage="configuration",
            reason="neomundi_poc_now_timezone_required",
        )
        raise NeoMundiRealObservationPocError(report["reason"], report=report)
    if max_age_seconds < 0 or max_future_skew_seconds < 0:
        report = _failure_report(
            stage="configuration",
            reason="neomundi_poc_trust_window_invalid",
        )
        raise NeoMundiRealObservationPocError(report["reason"], report=report)

    try:
        verifier = NeoMundiRgcV02Verifier(
            trusted_jwks=trusted_jwks,
            verifier_policy_id=verifier_policy_id,
            verifier_trust_level=verifier_trust_level,
        )
    except ValueError as exc:
        report = _failure_report(stage="verifier_configuration", reason=str(exc))
        raise NeoMundiRealObservationPocError(str(exc), report=report) from exc

    provider_result = verifier.verify(artifact)
    if not provider_result.verified:
        reason = str(provider_result.reason or "neomundi_poc_provider_verification_failed")
        report = _failure_report(
            stage="provider_verification",
            reason=reason,
            provider_result=provider_result,
        )
        raise NeoMundiRealObservationPocError(reason, report=report)

    approved = ApprovedExternalMeasurementProvider(
        provider_id=NEOMUNDI_PROVIDER_ID,
        verifier_id=verifier.verifier_id,
        verifier_trust_level=verifier.verifier_trust_level,
        verifier_policy_id=verifier.verifier_policy_id,
        verifier_policy_hash=verifier.verifier_policy_hash,
    )
    trust_policy = ExternalMeasurementTrustPolicy(
        policy_id=trust_policy_id,
        approved_providers=[approved],
        max_age_seconds=max_age_seconds,
        max_future_skew_seconds=max_future_skew_seconds,
        require_expiry=not allow_no_expiry,
    )
    replay_guard = FileExternalMeasurementReplayGuard(replay_state_dir)

    try:
        proof = verify_external_measurement_artifact_to_evidence(
            artifact,
            provider_verifier=_StaticProviderVerifier(provider_result),
            trust_policy=trust_policy,
            replay_guard=replay_guard,
            now=current,
        )
    except ValueError as exc:
        report = _failure_report(
            stage="generic_external_measurement_boundary",
            reason=str(exc),
            provider_result=provider_result,
        )
        raise NeoMundiRealObservationPocError(str(exc), report=report) from exc

    revalidation_failures = validate_verified_external_measurement_evidence(
        proof,
        trust_policy=trust_policy,
        now=current,
    )
    if revalidation_failures:
        reason = "neomundi_poc_sealed_proof_revalidation_failed"
        report = _failure_report(
            stage="sealed_proof_revalidation",
            reason=reason,
            provider_result=provider_result,
        )
        report["revalidation_failures"] = list(revalidation_failures)
        raise NeoMundiRealObservationPocError(reason, report=report)

    provider_report = _provider_result_to_dict(provider_result)
    proof_dict = verified_external_measurement_to_dict(proof)
    verification_report = {
        "status": "verified",
        "stage": "complete",
        "reason": "neomundi_real_observation_poc_verified",
        "provider_verification": provider_report,
        "generic_boundary": {
            "accepted": True,
            "trust_policy_id": trust_policy.policy_id,
            "trust_policy_hash": trust_policy.deterministic_hash(),
            "require_expiry": trust_policy.require_expiry,
            "max_age_seconds": trust_policy.max_age_seconds,
            "max_future_skew_seconds": trust_policy.max_future_skew_seconds,
            "revalidation_failures": [],
        },
        "claim_boundary": {
            "measurement_only": True,
            "authority_created": False,
            "human_approval_created": False,
            "bind_authorization_created": False,
            "governance_decision_created": False,
            "external_effect_performed": False,
        },
    }

    manifest = {
        "manifest_version": POC_MANIFEST_VERSION,
        "purpose": POC_PURPOSE,
        "verified_at": proof.verified_at,
        "inputs": {
            "provider_id": NEOMUNDI_PROVIDER_ID,
            "artifact_id": proof.evidence.artifact_id,
            "artifact_version": proof.evidence.artifact_version,
            "artifact_payload_hash": proof.evidence.payload_hash,
            "artifact_canonical_sha256": sha256_of_canonical_json(artifact),
            "artifact_file_sha256": source_artifact_file_sha256,
            "trusted_jwks_canonical_sha256": sha256_of_canonical_json(trusted_jwks),
            "trusted_jwks_file_sha256": trusted_jwks_file_sha256,
        },
        "verification": {
            "key_id": proof.key_id,
            "algorithm": proof.algorithm,
            "verifier_id": proof.verifier_id,
            "verifier_policy_id": proof.verifier_policy_id,
            "verifier_policy_hash": proof.verifier_policy_hash,
            "trust_policy_id": proof.trust_policy_id,
            "trust_policy_hash": proof.trust_policy_hash,
            "evidence_hash": proof.evidence_hash,
            "verification_proof_hash": proof.verification_proof_hash,
            "replay_key": proof.replay_key,
        },
        "outputs": {
            "verification_report": "verification_report.json",
            "verification_report_canonical_sha256": sha256_of_canonical_json(
                verification_report
            ),
            "verified_external_measurement_evidence": (
                "verified_external_measurement_evidence.json"
            ),
            "verified_external_measurement_evidence_canonical_sha256": (
                sha256_of_canonical_json(proof_dict)
            ),
        },
        "claim_boundary": verification_report["claim_boundary"],
        "non_claims": [
            "not production validation",
            "not third-party certification",
            "not execution authority",
            "not a governance ALLOW/DENY decision",
            "not an external effect",
        ],
    }

    return {
        "verification_report": verification_report,
        "verified_external_measurement_evidence": proof_dict,
        "evidence_manifest": manifest,
    }
