"""End-to-end non-executing rehearsal for the first external proof path.

This module composes the NeoMundi real-observation verification runtime seam
with the external-measurement governance closure harness in one trusted process.
The runtime-sealed ``VerifiedExternalMeasurementEvidence`` object is forwarded
directly; its JSON serialization is emitted for audit only and is never
reinterpreted as trusted runtime state.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.governance.authority_evidence import AuthorityEvidence
from veritas_os.governance.external_measurement_governance_closure import (
    close_verified_external_measurement_governance,
)
from veritas_os.governance.neomundi_real_observation_poc import (
    verify_neomundi_real_observation_runtime,
)
from veritas_os.security.hash import sha256_of_canonical_json

E2E_REHEARSAL_VERSION = "external-proof-e2e-rehearsal-v1"


def run_external_proof_e2e_rehearsal(
    artifact: dict[str, Any],
    *,
    trusted_jwks: dict[str, Any],
    replay_state_dir: str | Path,
    verifier_policy_id: str,
    verifier_trust_level: str,
    trust_policy_id: str,
    max_age_seconds: int,
    action_contract: ActionClassContract,
    authority_evidence: AuthorityEvidence | None,
    human_approval_state: dict[str, Any],
    policy_evaluation: dict[str, Any],
    requested_scope: list[str],
    required_evidence_metadata: dict[str, Any],
    evidence_freshness_metadata: dict[str, Any],
    actor_identity: str,
    max_future_skew_seconds: int = 60,
    allow_no_expiry: bool = False,
    now: datetime | None = None,
    source_artifact_file_sha256: str | None = None,
    trusted_jwks_file_sha256: str | None = None,
) -> dict[str, Any]:
    """Run the signed-observation-to-governance path without execution.

    This function deliberately does not issue BindAuthorization, resolve or
    access credentials, dispatch network traffic, or perform an external effect.
    A ``commit`` governance outcome means only that the supplied independent
    governance inputs are admissible at the non-executing review boundary.
    """
    runtime = verify_neomundi_real_observation_runtime(
        artifact,
        trusted_jwks=trusted_jwks,
        replay_state_dir=replay_state_dir,
        verifier_policy_id=verifier_policy_id,
        verifier_trust_level=verifier_trust_level,
        trust_policy_id=trust_policy_id,
        max_age_seconds=max_age_seconds,
        max_future_skew_seconds=max_future_skew_seconds,
        allow_no_expiry=allow_no_expiry,
        now=now,
        source_artifact_file_sha256=source_artifact_file_sha256,
        trusted_jwks_file_sha256=trusted_jwks_file_sha256,
    )

    closure = close_verified_external_measurement_governance(
        verified_measurement=runtime.verified_measurement,
        measurement_trust_policy=runtime.trust_policy,
        action_contract=action_contract,
        authority_evidence=authority_evidence,
        human_approval_state=human_approval_state,
        policy_evaluation=policy_evaluation,
        requested_scope=requested_scope,
        required_evidence_metadata=required_evidence_metadata,
        evidence_freshness_metadata=evidence_freshness_metadata,
        actor_identity=actor_identity,
        now=now,
    )

    measurement_outputs = runtime.to_outputs()
    closure_output = closure.to_dict()
    chain_material = {
        "measurement_evidence_hash": runtime.verified_measurement.evidence_hash,
        "measurement_verification_proof_hash": (
            runtime.verified_measurement.verification_proof_hash
        ),
        "measurement_trust_policy_hash": (
            runtime.verified_measurement.trust_policy_hash
        ),
        "governance_packet_hash": closure.packet_hash,
        "governance_outcome": closure.governance_outcome,
    }
    chain_hash = sha256_of_canonical_json(chain_material)

    rehearsal_manifest = {
        "version": E2E_REHEARSAL_VERSION,
        "purpose": "external_measurement_to_non_executing_governance_rehearsal",
        "composition": {
            "same_process_sealed_proof_forwarded": True,
            "serialized_measurement_retrusted": False,
            "provider_verification": "NeoMundiRgcV02Verifier",
            "generic_measurement_boundary": True,
            "governance_closure": "CommitBoundaryEvaluator",
        },
        "chain": {**chain_material, "chain_hash": chain_hash},
        "outputs": {
            "measurement_verification_canonical_sha256": sha256_of_canonical_json(
                measurement_outputs
            ),
            "governance_closure_canonical_sha256": sha256_of_canonical_json(
                closure_output
            ),
        },
        "claim_boundary": {
            "measurement_converted_to_authority": False,
            "measurement_converted_to_human_approval": False,
            "measurement_converted_to_bind_authorization": False,
            "bind_authorization_created": False,
            "credentials_accessed": False,
            "network_dispatch_performed": False,
            "external_effect_performed": False,
            "governance_evaluation_non_executing": True,
        },
        "non_claims": [
            "not live interoperability by synthetic rehearsal alone",
            "not production validation",
            "not customer deployment",
            "not certification",
            "not execution authority",
            "not an external effect",
        ],
    }

    return {
        "measurement_verification": measurement_outputs,
        "governance_closure": closure_output,
        "rehearsal_manifest": rehearsal_manifest,
    }
