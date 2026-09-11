"""NeoMundi RGC v0.2 provider adapter for external measurement evidence.

This module verifies NeoMundi Measurement Interoperability Contracts as
measurement evidence only.  A valid contract never becomes AuthorityEvidence,
HumanApproval, BindAuthorization, or a GovernanceDecision.
"""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import re
from datetime import datetime
from typing import Any

from veritas_os.governance.external_measurement_evidence import (
    ExternalMeasurementEvidence,
    ExternalMeasurementProviderVerificationResult,
)
from veritas_os.security.hash import sha256_of_canonical_json

NEOMUNDI_PROVIDER_ID = "neomundi"
NEOMUNDI_RGC_V02_VERIFIER_ID = "neomundi_rgc_v02"
NEOMUNDI_RGC_V02_SCHEMA_VERSION = "0.2.0"
NEOMUNDI_RGC_ARTIFACT_TYPE = "neomundi_rgc"
NEOMUNDI_RGC_HASH_ALGORITHM = "sha256"
NEOMUNDI_RGC_CANONICALIZATION = "sorted-json-utf8"
NEOMUNDI_RGC_JWS_ALGORITHM = "EdDSA"

_SIGNAL_NAMES = (
    "stability_score",
    "coherence_score",
    "factual_hallucination_score",
    "semantic_instability_score",
    "semantic_risk",
)
_SIGNAL_STATES = {"measured", "not_measured", "insufficient_coverage"}
_OBSERVATION_CLASSES = {"within_bounds", "flagged", "not_assessed"}
_REVIEW_RECOMMENDATIONS = {"not_indicated", "recommended", "required"}
_B64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class _NeoMundiVerificationError(ValueError):
    """Internal deterministic verification failure."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _fail(reason: str) -> None:
    raise _NeoMundiVerificationError(reason)


def _require_dict(parent: dict[str, Any], key: str, reason: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        _fail(reason)
    return value


def _require_nonempty_string(
    parent: dict[str, Any], key: str, reason: str
) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value.strip():
        _fail(reason)
    return value


def _require_number(value: Any, reason: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(reason)
    numeric = float(value)
    if not 0.0 <= numeric <= 1.0:
        _fail(reason)
    return numeric


def _strict_json_object(raw: bytes, reason: str) -> dict[str, Any]:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail(reason)
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        _fail(reason)
    if not isinstance(value, dict):
        _fail(reason)
    return value


def _strict_b64url_decode(value: str, reason: str) -> bytes:
    if not isinstance(value, str) or not value or not _B64URL_RE.fullmatch(value):
        _fail(reason)
    try:
        return base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError):
        _fail(reason)


def _canonical_payload_hash(artifact: dict[str, Any]) -> str:
    """Match NeoMundi's published sorted compact JSON reference consumer."""
    sections = {
        "identity": artifact["identity"],
        "provenance": artifact["provenance"],
        "observation": artifact["observation"],
        "governance": artifact["governance"],
    }
    canonical = json.dumps(sections, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        _fail("neomundi_rgc_timestamp_invalid")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail("neomundi_rgc_timestamp_timezone_required")


def _validate_structure_and_semantics(
    artifact: dict[str, Any],
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    if not isinstance(artifact, dict):
        _fail("neomundi_rgc_artifact_invalid")

    identity = _require_dict(artifact, "identity", "neomundi_rgc_identity_missing")
    provenance = _require_dict(
        artifact, "provenance", "neomundi_rgc_provenance_missing"
    )
    observation = _require_dict(
        artifact, "observation", "neomundi_rgc_observation_missing"
    )
    governance = _require_dict(
        artifact, "governance", "neomundi_rgc_governance_missing"
    )
    integrity = _require_dict(
        artifact, "integrity", "neomundi_rgc_integrity_missing"
    )

    schema_version = identity.get("schema_version")
    if schema_version != NEOMUNDI_RGC_V02_SCHEMA_VERSION:
        _fail("neomundi_rgc_version_unsupported")

    for key in ("request_id", "trace_id", "system_id", "model", "mode"):
        _require_nonempty_string(identity, key, f"neomundi_rgc_identity_{key}_invalid")
    timestamp = _require_nonempty_string(
        identity, "timestamp", "neomundi_rgc_timestamp_invalid"
    )
    _validate_timestamp(timestamp)

    _require_nonempty_string(
        provenance,
        "measurement_version",
        "neomundi_rgc_provenance_measurement_version_invalid",
    )
    _require_nonempty_string(
        provenance,
        "normalizer_version",
        "neomundi_rgc_provenance_normalizer_version_invalid",
    )

    runtime_scope = _require_nonempty_string(
        observation, "runtime_scope", "neomundi_rgc_runtime_scope_missing"
    )
    if runtime_scope == "single_request" and observation.get("observation_window") not in (
        None,
        "",
    ):
        # A single-request observation may carry an informational window, but the
        # adapter never turns it into persistence/trend semantics. No rejection.
        pass

    measurement_status = observation.get("measurement_status")
    if measurement_status not in {"complete", "partial"}:
        _fail("neomundi_rgc_measurement_status_invalid")
    coverage = _require_number(
        observation.get("measurement_coverage"),
        "neomundi_rgc_measurement_coverage_invalid",
    )
    if measurement_status == "complete" and coverage != 1.0:
        _fail("neomundi_rgc_measurement_semantics_invalid")
    if measurement_status == "partial" and coverage >= 1.0:
        _fail("neomundi_rgc_measurement_semantics_invalid")

    limitations = observation.get("limitations")
    if (
        not isinstance(limitations, list)
        or not limitations
        or any(not isinstance(item, str) or not item.strip() for item in limitations)
    ):
        _fail("neomundi_rgc_limitations_missing")
    _require_nonempty_string(
        observation,
        "measurement_boundary",
        "neomundi_rgc_measurement_boundary_missing",
    )

    observed_signals = _require_dict(
        observation, "observed_signals", "neomundi_rgc_observed_signals_missing"
    )
    signal_status = _require_dict(
        observed_signals,
        "signal_status",
        "neomundi_rgc_signal_status_missing",
    )
    for name in _SIGNAL_NAMES:
        if name not in observed_signals or name not in signal_status:
            _fail("neomundi_rgc_signal_missing")
        state = signal_status[name]
        if state not in _SIGNAL_STATES:
            _fail("neomundi_rgc_signal_status_invalid")
        value = observed_signals[name]
        if state == "measured":
            _require_number(value, "neomundi_rgc_measured_signal_invalid")
        elif value is not None:
            _fail("neomundi_rgc_unmeasured_signal_must_be_null")

    if observed_signals.get("observation_class") not in _OBSERVATION_CLASSES:
        _fail("neomundi_rgc_observation_class_invalid")
    _require_number(
        observed_signals.get("confidence"),
        "neomundi_rgc_confidence_invalid",
    )

    governance_boundary = _require_dict(
        governance,
        "governance_boundary",
        "neomundi_rgc_governance_boundary_missing",
    )
    if "execution_permission_changed" not in governance_boundary:
        _fail("neomundi_rgc_execution_permission_missing")
    if governance_boundary["execution_permission_changed"] is not False:
        _fail("neomundi_rgc_execution_permission_invalid")
    if governance_boundary.get("authorization_status") != "not_applicable":
        _fail("neomundi_rgc_authorization_status_invalid")

    advisory = _require_dict(
        governance, "advisory", "neomundi_rgc_advisory_missing"
    )
    if advisory.get("review_recommendation") not in _REVIEW_RECOMMENDATIONS:
        _fail("neomundi_rgc_review_recommendation_invalid")
    interpretation_policy = _require_dict(
        advisory,
        "interpretation_policy",
        "neomundi_rgc_interpretation_policy_missing",
    )
    _require_nonempty_string(
        interpretation_policy,
        "policy_id",
        "neomundi_rgc_interpretation_policy_invalid",
    )
    _require_nonempty_string(
        interpretation_policy,
        "policy_version",
        "neomundi_rgc_interpretation_policy_invalid",
    )

    if "hash_algorithm" not in integrity:
        _fail("neomundi_rgc_hash_algorithm_missing")
    if integrity.get("hash_algorithm") != NEOMUNDI_RGC_HASH_ALGORITHM:
        _fail("neomundi_rgc_hash_algorithm_invalid")
    if "canonicalization" not in integrity:
        _fail("neomundi_rgc_canonicalization_missing")
    if integrity.get("canonicalization") != NEOMUNDI_RGC_CANONICALIZATION:
        _fail("neomundi_rgc_canonicalization_invalid")

    payload_hash = _require_nonempty_string(
        integrity, "payload_hash", "neomundi_rgc_payload_hash_invalid"
    )
    if not re.fullmatch(r"[0-9a-f]{64}", payload_hash):
        _fail("neomundi_rgc_payload_hash_invalid")
    _require_nonempty_string(
        integrity, "signature", "neomundi_rgc_signature_missing"
    )
    _require_nonempty_string(
        integrity, "signer_identity", "neomundi_rgc_signer_identity_missing"
    )
    _require_nonempty_string(integrity, "key_id", "neomundi_rgc_key_id_missing")

    return identity, provenance, observation, governance, integrity


class NeoMundiRgcV02Verifier:
    """VERITAS-controlled verifier for NeoMundi RGC JSON v0.2 artifacts."""

    verifier_id = NEOMUNDI_RGC_V02_VERIFIER_ID

    def __init__(
        self,
        *,
        trusted_jwks: dict[str, Any],
        verifier_policy_id: str,
        verifier_trust_level: str = "cryptographic",
    ) -> None:
        if not isinstance(verifier_policy_id, str) or not verifier_policy_id.strip():
            raise ValueError("neomundi_rgc_verifier_policy_id_invalid")
        if not isinstance(verifier_trust_level, str) or not verifier_trust_level.strip():
            raise ValueError("neomundi_rgc_verifier_trust_level_invalid")
        if not isinstance(trusted_jwks, dict) or not isinstance(
            trusted_jwks.get("keys"), list
        ):
            raise ValueError("neomundi_rgc_trusted_jwks_invalid")

        keys_by_id: dict[str, dict[str, Any]] = {}
        policy_keys: list[dict[str, Any]] = []
        for item in trusted_jwks["keys"]:
            if not isinstance(item, dict):
                raise ValueError("neomundi_rgc_trusted_jwks_invalid")
            if "d" in item:
                raise ValueError("neomundi_rgc_private_jwk_not_allowed")
            kid = item.get("kid")
            if not isinstance(kid, str) or not kid.strip() or kid in keys_by_id:
                raise ValueError("neomundi_rgc_trusted_jwks_invalid")
            keys_by_id[kid] = copy.deepcopy(item)
            policy_keys.append(copy.deepcopy(item))

        if not keys_by_id:
            raise ValueError("neomundi_rgc_trusted_jwks_empty")

        self._keys_by_id = keys_by_id
        self.verifier_policy_id = verifier_policy_id
        self.verifier_trust_level = verifier_trust_level
        self.verifier_policy_hash = sha256_of_canonical_json(
            {
                "provider_id": NEOMUNDI_PROVIDER_ID,
                "verifier_id": self.verifier_id,
                "verifier_policy_id": verifier_policy_id,
                "verifier_trust_level": verifier_trust_level,
                "trusted_jwks": sorted(policy_keys, key=lambda item: item["kid"]),
                "schema_version": NEOMUNDI_RGC_V02_SCHEMA_VERSION,
                "hash_algorithm": NEOMUNDI_RGC_HASH_ALGORITHM,
                "canonicalization": NEOMUNDI_RGC_CANONICALIZATION,
                "jws_algorithm": NEOMUNDI_RGC_JWS_ALGORITHM,
            }
        )

    def _failure(
        self, reason: str, *, key_id: str | None = None
    ) -> ExternalMeasurementProviderVerificationResult:
        return ExternalMeasurementProviderVerificationResult(
            verified=False,
            evidence=None,
            verifier_id=self.verifier_id,
            verifier_trust_level=self.verifier_trust_level,
            verifier_policy_id=self.verifier_policy_id,
            verifier_policy_hash=self.verifier_policy_hash,
            key_id=key_id,
            algorithm=NEOMUNDI_RGC_JWS_ALGORITHM,
            semantic_consistent=False,
            reason=reason,
        )

    def _verify_jws(
        self,
        signature: str,
        *,
        key_id: str,
        expected_claims: dict[str, Any],
    ) -> None:
        key = self._keys_by_id.get(key_id)
        if key is None:
            _fail("neomundi_rgc_key_untrusted")
        if key.get("kty") != "OKP" or key.get("crv") != "Ed25519":
            _fail("neomundi_rgc_key_invalid")

        try:
            protected_segment, payload_segment, signature_segment = signature.split(".")
        except ValueError:
            _fail("neomundi_rgc_jws_malformed")

        header = _strict_json_object(
            _strict_b64url_decode(
                protected_segment, "neomundi_rgc_jws_header_invalid"
            ),
            "neomundi_rgc_jws_header_invalid",
        )
        if header.get("alg") != NEOMUNDI_RGC_JWS_ALGORITHM:
            _fail("neomundi_rgc_jws_algorithm_invalid")
        if header.get("kid") is not None and header.get("kid") != key_id:
            _fail("neomundi_rgc_jws_kid_mismatch")

        claims = _strict_json_object(
            _strict_b64url_decode(
                payload_segment, "neomundi_rgc_jws_payload_invalid"
            ),
            "neomundi_rgc_jws_payload_invalid",
        )
        for claim, expected in expected_claims.items():
            if claims.get(claim) != expected:
                _fail(f"neomundi_rgc_signed_claim_{claim}_mismatch")

        raw_signature = _strict_b64url_decode(
            signature_segment, "neomundi_rgc_jws_signature_invalid"
        )
        public_x = key.get("x")
        if not isinstance(public_x, str):
            _fail("neomundi_rgc_key_invalid")
        raw_public_key = _strict_b64url_decode(
            public_x, "neomundi_rgc_key_invalid"
        )
        if len(raw_public_key) != 32 or len(raw_signature) != 64:
            _fail("neomundi_rgc_signature_invalid")

        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey,
            )
        except ImportError:
            _fail("neomundi_rgc_crypto_unavailable")

        try:
            public_key = Ed25519PublicKey.from_public_bytes(raw_public_key)
            public_key.verify(
                raw_signature,
                f"{protected_segment}.{payload_segment}".encode("ascii"),
            )
        except InvalidSignature:
            _fail("neomundi_rgc_signature_invalid")
        except (TypeError, ValueError):
            _fail("neomundi_rgc_key_invalid")

    def verify(
        self, artifact: dict[str, Any]
    ) -> ExternalMeasurementProviderVerificationResult:
        key_id: str | None = None
        try:
            (
                identity,
                provenance,
                observation,
                governance,
                integrity,
            ) = _validate_structure_and_semantics(artifact)
            key_id = integrity["key_id"]

            recomputed_hash = _canonical_payload_hash(artifact)
            if recomputed_hash != integrity["payload_hash"]:
                _fail("neomundi_rgc_payload_hash_mismatch")

            expected_claims = {
                "payload_hash": integrity["payload_hash"],
                "hash_algorithm": integrity["hash_algorithm"],
                "schema_version": identity["schema_version"],
                "request_id": identity["request_id"],
                "timestamp": identity["timestamp"],
            }
            self._verify_jws(
                integrity["signature"],
                key_id=key_id,
                expected_claims=expected_claims,
            )

            governance_boundary = governance["governance_boundary"]
            observed_signals = observation["observed_signals"]
            replay_token = sha256_of_canonical_json(
                {
                    "provider_id": NEOMUNDI_PROVIDER_ID,
                    "request_id": identity["request_id"],
                    "trace_id": identity["trace_id"],
                    "payload_hash": recomputed_hash,
                }
            )
            evidence_id = "external-measurement:" + sha256_of_canonical_json(
                {
                    "provider_id": NEOMUNDI_PROVIDER_ID,
                    "artifact_id": identity["request_id"],
                    "payload_hash": recomputed_hash,
                }
            )

            evidence = ExternalMeasurementEvidence(
                evidence_id=evidence_id,
                provider_id=NEOMUNDI_PROVIDER_ID,
                artifact_id=identity["request_id"],
                artifact_type=NEOMUNDI_RGC_ARTIFACT_TYPE,
                artifact_version=identity["schema_version"],
                payload_hash=recomputed_hash,
                observed_at=identity["timestamp"],
                issued_at=identity["timestamp"],
                expires_at=None,
                replay_token=replay_token,
                measured_scope={
                    "runtime_scope": observation["runtime_scope"],
                    "observation_window": observation.get("observation_window"),
                    "measurement_boundary": observation["measurement_boundary"],
                },
                measurement_coverage=float(observation["measurement_coverage"]),
                semantic_facts={
                    "measurement_status": observation["measurement_status"],
                    "observation_class": observed_signals["observation_class"],
                    "confidence": float(observed_signals["confidence"]),
                    "observed_signals": copy.deepcopy(observed_signals),
                    "limitations": list(observation["limitations"]),
                    "advisory": copy.deepcopy(governance["advisory"]),
                    "governance_boundary": {
                        "authorization_status": governance_boundary[
                            "authorization_status"
                        ],
                        "execution_permission_changed": governance_boundary[
                            "execution_permission_changed"
                        ],
                    },
                },
                provenance={
                    **copy.deepcopy(provenance),
                    "request_id": identity["request_id"],
                    "trace_id": identity["trace_id"],
                    "system_id": identity["system_id"],
                    "model": identity["model"],
                    "mode": identity["mode"],
                    "signer_identity": integrity["signer_identity"],
                    "key_id": key_id,
                    "hash_algorithm": integrity["hash_algorithm"],
                    "canonicalization": integrity["canonicalization"],
                },
                metadata={
                    "adapter": self.verifier_id,
                    "schema_version": NEOMUNDI_RGC_V02_SCHEMA_VERSION,
                    "evidence_role": "measurement_only",
                    "authority_imported": False,
                    "approval_imported": False,
                    "execution_permission_imported": False,
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
                algorithm=NEOMUNDI_RGC_JWS_ALGORITHM,
                semantic_consistent=True,
                reason="neomundi_rgc_v02_verified",
            )
        except _NeoMundiVerificationError as exc:
            return self._failure(exc.reason, key_id=key_id)
        except (KeyError, TypeError, ValueError):
            return self._failure("neomundi_rgc_artifact_invalid", key_id=key_id)
