"""Explicit historical NeoMundi RGC v0.1.0 COMPLETE-only verification profile.

This opt-in provider verifier does not relabel a signed RGC v0.1.0 as v0.2.
It preserves the original signed payload and does not create execution
authority, approval, a governance decision, or a live-interoperability claim.
"""

from __future__ import annotations

import copy
import re
from datetime import datetime
from typing import Any

from veritas_os.governance.external_measurement_evidence import (
    ExternalMeasurementEvidence,
    ExternalMeasurementProviderVerificationResult,
)
from veritas_os.governance.neomundi_rgc_v02 import (
    NEOMUNDI_PROVIDER_ID,
    NEOMUNDI_RGC_ARTIFACT_TYPE,
    NeoMundiRgcV02Verifier,
    _canonical_payload_hash,
)
from veritas_os.governance.neomundi_rgc_v01_s1_schema import (
    SCHEMA_SHA256,
    validate_neomundi_rgc_v01_s1,
)
from veritas_os.security.hash import sha256_of_canonical_json

NEOMUNDI_RGC_V01_COMPLETE_VERIFIER_ID = "neomundi_rgc_v01_complete"
NEOMUNDI_RGC_V01_SCHEMA_VERSION = "0.1.0"
_SIGNAL_NAMES = (
    "stability_score",
    "coherence_score",
    "factual_hallucination_score",
    "semantic_instability_score",
    "semantic_risk",
)


class _LegacyRgcInvalid(ValueError):
    """A v0.1.0 historical profile constraint was not met."""


def _require_object(parent: dict[str, Any], key: str, reason: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise _LegacyRgcInvalid(reason)
    return value


def _require_text(parent: dict[str, Any], key: str, reason: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value.strip():
        raise _LegacyRgcInvalid(reason)
    return value


def _require_score(value: Any, reason: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _LegacyRgcInvalid(reason)
    try:
        numeric = float(value)
    except (OverflowError, ValueError) as exc:
        raise _LegacyRgcInvalid(reason) from exc
    if not 0.0 <= numeric <= 1.0:
        raise _LegacyRgcInvalid(reason)
    return numeric


def _historical_complete_sections(
    artifact: dict[str, Any],
    *,
    accepted_measurement_versions: tuple[str, ...],
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    identity = _require_object(artifact, "identity", "neomundi_v01_identity_missing")
    provenance = _require_object(
        artifact, "provenance", "neomundi_v01_provenance_missing"
    )
    observation = _require_object(
        artifact, "observation", "neomundi_v01_observation_missing"
    )
    governance = _require_object(
        artifact, "governance", "neomundi_v01_governance_missing"
    )
    integrity = _require_object(artifact, "integrity", "neomundi_v01_integrity_missing")

    if identity.get("schema_version") != NEOMUNDI_RGC_V01_SCHEMA_VERSION:
        raise _LegacyRgcInvalid("neomundi_v01_schema_version_unsupported")
    for field in ("request_id", "trace_id", "system_id", "model", "mode"):
        _require_text(identity, field, "neomundi_v01_identity_invalid")
    if re.fullmatch(r"(local|model-[0-9a-f]{12})", identity["model"]) is None:
        raise _LegacyRgcInvalid("neomundi_v01_model_identifier_invalid")
    timestamp = _require_text(identity, "timestamp", "neomundi_v01_timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _LegacyRgcInvalid("neomundi_v01_timestamp_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _LegacyRgcInvalid("neomundi_v01_timestamp_timezone_required")

    measurement_version = _require_text(
        provenance, "measurement_version", "neomundi_v01_measurement_version_missing"
    )
    if measurement_version not in accepted_measurement_versions:
        raise _LegacyRgcInvalid("neomundi_v01_measurement_version_unapproved")
    _require_text(
        provenance, "normalizer_version", "neomundi_v01_normalizer_version_missing"
    )

    if observation.get("runtime_scope") != "single_request":
        raise _LegacyRgcInvalid("neomundi_v01_scope_unsupported")
    if observation.get("measurement_status") != "complete":
        raise _LegacyRgcInvalid("neomundi_v01_partial_or_unknown_forbidden")
    if (
        type(observation.get("measurement_coverage")) not in (float, int)
        or observation["measurement_coverage"] != 1.0
    ):
        raise _LegacyRgcInvalid("neomundi_v01_complete_coverage_invalid")
    temporal = _require_object(
        observation, "temporal_boundary", "neomundi_v01_temporal_boundary_missing"
    )
    if (
        temporal.get("record_scope") != "single_record"
        or temporal.get("establishes") != []
        or not isinstance(temporal.get("does_not_establish"), list)
        or not {"frequency", "persistence", "recurrence", "drift"}.issubset(
            set(temporal["does_not_establish"])
        )
    ):
        raise _LegacyRgcInvalid("neomundi_v01_temporal_overclaim")

    signals = _require_object(
        observation, "observed_signals", "neomundi_v01_signals_missing"
    )
    states = _require_object(
        signals, "signal_status", "neomundi_v01_signal_status_missing"
    )
    if set(states) != set(_SIGNAL_NAMES):
        raise _LegacyRgcInvalid("neomundi_v01_signal_status_incomplete")
    for name in _SIGNAL_NAMES:
        if states[name] != "measured":
            raise _LegacyRgcInvalid("neomundi_v01_unmeasured_forbidden")
        _require_score(signals.get(name), "neomundi_v01_measured_signal_invalid")
    if signals.get("observation_class") not in {"within_bounds", "flagged"}:
        raise _LegacyRgcInvalid("neomundi_v01_observation_class_invalid")
    if signals.get("observation_class_scope") != "measured_domain":
        raise _LegacyRgcInvalid("neomundi_v01_measurement_domain_missing")
    _require_score(signals.get("confidence"), "neomundi_v01_confidence_invalid")

    limitations = observation.get("limitations")
    if (
        not isinstance(limitations, list)
        or not limitations
        or any(not isinstance(x, str) or not x.strip() for x in limitations)
    ):
        raise _LegacyRgcInvalid("neomundi_v01_limitations_missing")
    _require_text(observation, "measurement_boundary", "neomundi_v01_boundary_missing")

    boundary = _require_object(
        governance, "governance_boundary", "neomundi_v01_governance_boundary_missing"
    )
    if (
        boundary.get("authorization_status") != "not_applicable"
        or boundary.get("execution_permission_changed") is not False
    ):
        raise _LegacyRgcInvalid("neomundi_v01_authority_boundary_invalid")
    advisory = _require_object(governance, "advisory", "neomundi_v01_advisory_missing")
    if advisory.get("review_recommendation") not in {
        "not_indicated",
        "recommended",
        "required",
    }:
        raise _LegacyRgcInvalid("neomundi_v01_advisory_invalid")
    policy = _require_object(
        advisory, "interpretation_policy", "neomundi_v01_advisory_policy_missing"
    )
    _require_text(policy, "policy_id", "neomundi_v01_advisory_policy_invalid")
    _require_text(policy, "policy_version", "neomundi_v01_advisory_policy_invalid")

    if (
        integrity.get("hash_algorithm") != "sha256"
        or integrity.get("canonicalization") != "sorted-json-utf8"
    ):
        raise _LegacyRgcInvalid("neomundi_v01_hash_profile_invalid")
    payload_hash = _require_text(
        integrity, "payload_hash", "neomundi_v01_payload_hash_missing"
    )
    if re.fullmatch(r"[0-9a-f]{64}", payload_hash) is None:
        raise _LegacyRgcInvalid("neomundi_v01_payload_hash_invalid")
    for field in ("signature", "signer_identity", "key_id"):
        _require_text(integrity, field, "neomundi_v01_integrity_field_missing")

    return identity, provenance, observation, governance, integrity


class NeoMundiRgcV01CompleteVerifier(NeoMundiRgcV02Verifier):
    """Opt-in complete-only legacy verifier with distinct policy identity.

    Inherits only the strictly bounded JWS verification implementation and
    trusted-JWKS configuration from the current v0.2 verifier. Version-specific
    validation, policy hashing, and evidence normalization remain separate.
    """

    verifier_id = NEOMUNDI_RGC_V01_COMPLETE_VERIFIER_ID

    def __init__(
        self,
        *,
        trusted_jwks: dict[str, Any],
        verifier_policy_id: str,
        accepted_measurement_versions: tuple[str, ...],
        verifier_trust_level: str = "cryptographic",
    ) -> None:
        if (
            not isinstance(accepted_measurement_versions, tuple)
            or not accepted_measurement_versions
            or any(
                not isinstance(v, str) or not v.strip()
                for v in accepted_measurement_versions
            )
            or len(set(accepted_measurement_versions))
            != len(accepted_measurement_versions)
        ):
            raise ValueError("neomundi_v01_measurement_allowlist_invalid")
        super().__init__(
            trusted_jwks=trusted_jwks,
            verifier_policy_id=verifier_policy_id,
            verifier_trust_level=verifier_trust_level,
        )
        self.accepted_measurement_versions = accepted_measurement_versions
        # The legacy policy MUST NOT share the v0.2 verifier's policy identity.
        self.verifier_policy_hash = sha256_of_canonical_json(
            {
                "provider_id": NEOMUNDI_PROVIDER_ID,
                "verifier_id": self.verifier_id,
                "verifier_policy_id": verifier_policy_id,
                "verifier_trust_level": verifier_trust_level,
                "profile": "rgc-v01-historical-complete-only",
                "contract_schema_profile": "production-S1",
                "contract_schema_sha256": SCHEMA_SHA256,
                "schema_version": NEOMUNDI_RGC_V01_SCHEMA_VERSION,
                "accepted_measurement_versions": sorted(accepted_measurement_versions),
                "trusted_jwks": sorted(
                    (copy.deepcopy(k) for k in self._keys_by_id.values()),
                    key=lambda k: k["kid"],
                ),
                "jws_algorithm": "EdDSA",
                "hash_algorithm": "sha256",
                "canonicalization": "sorted-json-utf8",
            }
        )

    def verify(
        self, artifact: dict[str, Any]
    ) -> ExternalMeasurementProviderVerificationResult:
        key_id: str | None = None
        try:
            if not isinstance(artifact, dict):
                raise _LegacyRgcInvalid("neomundi_v01_artifact_invalid")
            (
                identity,
                provenance,
                observation,
                governance,
                integrity,
            ) = _historical_complete_sections(
                artifact,
                accepted_measurement_versions=self.accepted_measurement_versions,
            )
            validate_neomundi_rgc_v01_s1(artifact)
            key_id = integrity["key_id"]
            recomputed = _canonical_payload_hash(artifact)
            if recomputed != integrity["payload_hash"]:
                raise _LegacyRgcInvalid("neomundi_v01_payload_hash_mismatch")
            self._verify_jws(
                integrity["signature"],
                key_id=key_id,
                expected_claims={
                    "payload_hash": integrity["payload_hash"],
                    "hash_algorithm": integrity["hash_algorithm"],
                    "schema_version": identity["schema_version"],
                    "request_id": identity["request_id"],
                    "timestamp": identity["timestamp"],
                },
            )

            signals = observation["observed_signals"]
            replay_token = sha256_of_canonical_json(
                {
                    "provider_id": NEOMUNDI_PROVIDER_ID,
                    "schema_version": NEOMUNDI_RGC_V01_SCHEMA_VERSION,
                    "request_id": identity["request_id"],
                    "trace_id": identity["trace_id"],
                    "payload_hash": recomputed,
                }
            )
            evidence_id = "external-measurement:" + sha256_of_canonical_json(
                {
                    "provider_id": NEOMUNDI_PROVIDER_ID,
                    "schema_version": NEOMUNDI_RGC_V01_SCHEMA_VERSION,
                    "artifact_id": identity["request_id"],
                    "payload_hash": recomputed,
                }
            )
            evidence = ExternalMeasurementEvidence(
                evidence_id=evidence_id,
                provider_id=NEOMUNDI_PROVIDER_ID,
                artifact_id=identity["request_id"],
                artifact_type=NEOMUNDI_RGC_ARTIFACT_TYPE,
                artifact_version=NEOMUNDI_RGC_V01_SCHEMA_VERSION,
                payload_hash=recomputed,
                observed_at=identity["timestamp"],
                issued_at=identity["timestamp"],
                expires_at=None,
                replay_token=replay_token,
                measured_scope={
                    "runtime_scope": "single_request",
                    "observation_window": observation.get("observation_window"),
                    "measurement_boundary": observation["measurement_boundary"],
                    "observation_class_scope": "measured_domain",
                },
                measurement_coverage=1.0,
                semantic_facts={
                    "measurement_status": "complete",
                    "observation_class": signals["observation_class"],
                    "confidence": float(signals["confidence"]),
                    "observed_signals": copy.deepcopy(signals),
                    "limitations": list(observation["limitations"]),
                    "advisory": copy.deepcopy(governance["advisory"]),
                    "governance_boundary": {
                        "authorization_status": "not_applicable",
                        "execution_permission_changed": False,
                    },
                    "temporal_boundary": copy.deepcopy(
                        observation["temporal_boundary"]
                    ),
                },
                provenance={
                    **copy.deepcopy(provenance),
                    "request_id": identity["request_id"],
                    "trace_id": identity["trace_id"],
                    "system_id": identity["system_id"],
                    "model": identity["model"],
                    "mode": identity["mode"],
                    "signer_identity_unverified_metadata": integrity["signer_identity"],
                    "key_id": key_id,
                },
                metadata={
                    "adapter": self.verifier_id,
                    "schema_version": NEOMUNDI_RGC_V01_SCHEMA_VERSION,
                    "legacy_profile": "historical-complete-only",
                    "measurement_only": True,
                    "authority_imported": False,
                    "approval_imported": False,
                    "execution_permission_imported": False,
                    "local_execution_established": False,
                    "factuality_certified": False,
                    "temporal_drift_established": False,
                },
            )
            return ExternalMeasurementProviderVerificationResult(
                verified=True,
                evidence=evidence,
                verifier_id=self.verifier_id,
                verifier_trust_level=self.verifier_trust_level,
                verifier_policy_id=self.verifier_policy_id,
                verifier_policy_hash=self.verifier_policy_hash,
                key_id=key_id,
                algorithm="EdDSA",
                semantic_consistent=True,
                reason="neomundi_rgc_v01_complete_verified",
            )
        except (ValueError, KeyError, TypeError) as exc:
            reason = (
                str(exc)
                if isinstance(exc, ValueError)
                else "neomundi_v01_artifact_invalid"
            )
            return self._failure(reason, key_id=key_id)
