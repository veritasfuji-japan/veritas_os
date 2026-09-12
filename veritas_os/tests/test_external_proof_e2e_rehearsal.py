from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.governance.authority_evidence_ingestion import (
    ingest_authority_evidence_payload,
)
from veritas_os.governance.external_proof_e2e_rehearsal import (
    run_external_proof_e2e_rehearsal,
)
from veritas_os.governance.human_approval_receipt import (
    HumanApprovalReceipt,
    build_human_approval_state,
)
from veritas_os.governance.neomundi_real_observation_poc import (
    NeoMundiRealObservationPocError,
)

NOW = datetime(2026, 9, 11, 10, 0, tzinfo=UTC)
POLICY_SNAPSHOT_ID = "policy-e2e-rehearsal-001"
REQUESTED_SCOPE = ["poc:review"]


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _payload_hash(artifact: dict[str, Any]) -> str:
    payload = {
        "identity": artifact["identity"],
        "provenance": artifact["provenance"],
        "observation": artifact["observation"],
        "governance": artifact["governance"],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _material(
    *, kid: str = "neomundi-e2e-key"
) -> tuple[Ed25519PrivateKey, dict[str, Any]]:
    private_key = Ed25519PrivateKey.generate()
    raw_public = private_key.public_key().public_bytes(
        Encoding.Raw,
        PublicFormat.Raw,
    )
    return private_key, {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "kid": kid,
                "alg": "EdDSA",
                "x": _b64url(raw_public),
            }
        ]
    }


def _artifact(timestamp: str = "2026-09-11T09:59:30+00:00") -> dict[str, Any]:
    return {
        "identity": {
            "schema_version": "0.2.0",
            "request_id": "req-neomundi-e2e-rehearsal-001",
            "trace_id": "00-" + ("c" * 32) + "-" + ("d" * 16) + "-01",
            "timestamp": timestamp,
            "system_id": "neomundi-e2e-rehearsal",
            "model": "local",
            "mode": "poc",
        },
        "provenance": {
            "measurement_version": "measurement-0.2",
            "normalizer_version": "normalizer-0.2",
            "checks_emitted": 4,
            "source_batch_id": None,
            "canonicalization_method": "sorted-json-utf8",
        },
        "observation": {
            "runtime_scope": "single_request",
            "observation_window": None,
            "measurement_status": "complete",
            "measurement_coverage": 1.0,
            "observed_signals": {
                "stability_score": 0.91,
                "coherence_score": 0.88,
                "factual_hallucination_score": None,
                "semantic_instability_score": 0.12,
                "semantic_risk": 0.20,
                "signal_status": {
                    "stability_score": "measured",
                    "coherence_score": "measured",
                    "factual_hallucination_score": "not_measured",
                    "semantic_instability_score": "measured",
                    "semantic_risk": "measured",
                },
                "observation_class": "within_bounds",
                "confidence": 0.93,
            },
            "limitations": ["single request observation only"],
            "measurement_boundary": "declared runtime output signals",
        },
        "governance": {
            "governance_boundary": {
                "authorization_status": "not_applicable",
                "execution_permission_changed": False,
            },
            "advisory": {
                "review_recommendation": "not_indicated",
                "review_trigger": [],
                "recommended_review_type": [],
                "interpretation_policy": {
                    "policy_id": "neomundi-reference",
                    "policy_version": "0.2",
                },
            },
        },
        "integrity": {
            "payload_hash": "",
            "hash_algorithm": "sha256",
            "canonicalization": "sorted-json-utf8",
            "signature": "",
            "signer_identity": "neomundi-e2e-signer",
            "key_id": "neomundi-e2e-key",
            "confidentiality_class": "controlled",
            "retention_reference": None,
        },
    }


def _sign(artifact: dict[str, Any], private_key: Ed25519PrivateKey) -> dict[str, Any]:
    artifact["integrity"]["payload_hash"] = _payload_hash(artifact)
    claims = {
        "payload_hash": artifact["integrity"]["payload_hash"],
        "hash_algorithm": artifact["integrity"]["hash_algorithm"],
        "schema_version": artifact["identity"]["schema_version"],
        "request_id": artifact["identity"]["request_id"],
        "timestamp": artifact["identity"]["timestamp"],
    }
    header = {"alg": "EdDSA", "typ": "JWT", "kid": "neomundi-e2e-key"}
    protected = _b64url(
        json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    payload = _b64url(
        json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    signature = _b64url(
        private_key.sign(f"{protected}.{payload}".encode("ascii"))
    )
    artifact["integrity"]["signature"] = f"{protected}.{payload}.{signature}"
    return artifact


def _contract() -> ActionClassContract:
    return ActionClassContract(
        id="external_proof_e2e_rehearsal",
        version="1.0.0",
        domain="poc",
        action_class="external_measurement_review",
        description="Rehearse external measurement governance without execution.",
        declared_intent="Evaluate independent governance inputs without execution.",
        allowed_scope=["poc:review"],
        prohibited_scope=["poc:execute"],
        authority_sources=["policy.fixture_governance"],
        required_evidence=["governance_case_record"],
        evidence_freshness={"governance_case_record": "PT1H"},
        irreversibility={"boundary": "poc_non_executing_review", "level": "high"},
        human_approval_rules={"minimum_approvals": 1},
        refusal_conditions=["authority_indeterminate"],
        escalation_conditions=["evidence_stale"],
        default_failure_mode="fail_closed",
        metadata={"regulated": True, "fixture_only": True},
    )


def _authority() -> Any:
    return ingest_authority_evidence_payload(
        {
            "authority_evidence_id": "aev-e2e-rehearsal-001",
            "action_contract_id": "external_proof_e2e_rehearsal",
            "action_contract_version": "1.0.0",
            "actor_identity": "agent:poc-reviewer",
            "actor_role": "governance_operator",
            "authority_source_refs": ["policy.fixture_governance"],
            "role_or_policy_basis": ["role:governance_operator"],
            "scope_grants": ["poc:review"],
            "scope_limitations": ["poc:execute"],
            "issued_at": "2026-09-11T09:00:00+00:00",
            "valid_from": "2026-09-11T09:00:00+00:00",
            "valid_until": "2026-09-11T12:00:00+00:00",
            "policy_snapshot_id": POLICY_SNAPSHOT_ID,
            "verification_result": "valid",
            "metadata": {"source_type": "fixture_policy_registry"},
        }
    )


def _approval_state(
    authority_id: str = "aev-e2e-rehearsal-001",
) -> dict[str, Any]:
    receipt = HumanApprovalReceipt(
        approval_receipt_id="har-e2e-rehearsal-001",
        decision_id="decision-e2e-rehearsal-001",
        execution_intent_id="intent-e2e-rehearsal-001",
        approver_identity="human:fixture-approver",
        approver_role="governance_reviewer",
        approved_action_class="external_measurement_review",
        approved_scope=list(REQUESTED_SCOPE),
        approval_basis_refs=["review:e2e-rehearsal-001"],
        approved_at="2026-09-11T09:50:00+00:00",
        expires_at="2026-09-11T11:00:00+00:00",
        policy_snapshot_id=POLICY_SNAPSHOT_ID,
        authority_evidence_id=authority_id,
        approval_result="approved",
        signature_verified=True,
        receipt_hash="",
        metadata={"fixture_only": True},
    )
    return build_human_approval_state(
        receipt,
        requested_scope=list(REQUESTED_SCOPE),
        action_class="external_measurement_review",
        policy_snapshot_id=POLICY_SNAPSHOT_ID,
        now=NOW,
    )


def _policy_evaluation(*, admissible: bool = True) -> dict[str, Any]:
    return {
        "evaluation_id": "policy-eval-e2e-rehearsal-001",
        "policy_snapshot_id": POLICY_SNAPSHOT_ID,
        "admissible": admissible,
        "reasons": ["fixture_policy_evaluated_independently"],
    }


def _run(
    artifact: dict[str, Any],
    jwks: dict[str, Any],
    replay_dir: Path,
    *,
    include_authority: bool = True,
    approval_state: dict[str, Any] | None = None,
    admissible: bool = True,
    max_age_seconds: int = 3600,
) -> dict[str, Any]:
    return run_external_proof_e2e_rehearsal(
        artifact,
        trusted_jwks=jwks,
        replay_state_dir=replay_dir,
        verifier_policy_id="neomundi-rgc-v02-e2e-rehearsal",
        verifier_trust_level="external-poc",
        trust_policy_id="neomundi-rgc-v02-e2e-rehearsal-trust",
        max_age_seconds=max_age_seconds,
        max_future_skew_seconds=60,
        allow_no_expiry=True,
        action_contract=_contract(),
        authority_evidence=_authority() if include_authority else None,
        human_approval_state=(
            _approval_state() if approval_state is None else approval_state
        ),
        policy_evaluation=_policy_evaluation(admissible=admissible),
        requested_scope=list(REQUESTED_SCOPE),
        required_evidence_metadata={"governance_case_record": {"present": True}},
        evidence_freshness_metadata={"governance_case_record": {"fresh": True}},
        actor_identity="agent:poc-reviewer",
        now=NOW,
        source_artifact_file_sha256="a" * 64,
        trusted_jwks_file_sha256="b" * 64,
    )


def test_e2e_rehearsal_forwards_runtime_sealed_proof_without_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    private_key, jwks = _material()
    artifact = _sign(_artifact(), private_key)

    result = _run(artifact, jwks, tmp_path / "replay")

    measurement = result["measurement_verification"]
    closure = result["governance_closure"]
    manifest = result["rehearsal_manifest"]

    assert measurement["verification_report"]["status"] == "verified"
    assert closure["governance_outcome"] == "commit"
    assert closure["authority_validation_status"] == "pass"
    assert (
        closure["packet"]["external_measurement"]["verification_proof_hash"]
        == measurement["verified_external_measurement_evidence"][
            "verification_proof_hash"
        ]
    )
    assert manifest["composition"]["same_process_sealed_proof_forwarded"] is True
    assert manifest["composition"]["serialized_measurement_retrusted"] is False
    assert manifest["claim_boundary"]["bind_authorization_created"] is False
    assert manifest["claim_boundary"]["credentials_accessed"] is False
    assert manifest["claim_boundary"]["network_dispatch_performed"] is False
    assert manifest["claim_boundary"]["external_effect_performed"] is False
    assert manifest["chain"]["chain_hash"]


def test_e2e_rehearsal_measurement_does_not_replace_missing_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    private_key, jwks = _material()
    artifact = _sign(_artifact(), private_key)

    result = _run(
        artifact,
        jwks,
        tmp_path / "replay",
        include_authority=False,
    )

    closure = result["governance_closure"]
    assert closure["governance_outcome"] == "block"
    assert closure["authority_validation_status"] == "fail"
    assert closure["packet"]["authority"]["authority_evidence_id"] is None
    assert result["rehearsal_manifest"]["claim_boundary"][
        "measurement_converted_to_authority"
    ] is False


def test_e2e_rehearsal_measurement_does_not_replace_missing_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    private_key, jwks = _material()
    artifact = _sign(_artifact(), private_key)
    missing_approval = build_human_approval_state(
        None,
        requested_scope=list(REQUESTED_SCOPE),
    )

    result = _run(
        artifact,
        jwks,
        tmp_path / "replay",
        approval_state=missing_approval,
    )

    closure = result["governance_closure"]
    assert closure["governance_outcome"] == "block"
    assert closure["packet"]["human_approval"]["approved"] is False
    assert result["rehearsal_manifest"]["claim_boundary"][
        "measurement_converted_to_human_approval"
    ] is False


def test_e2e_rehearsal_policy_refusal_is_not_overridden(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    private_key, jwks = _material()
    artifact = _sign(_artifact(), private_key)

    result = _run(
        artifact,
        jwks,
        tmp_path / "replay",
        admissible=False,
    )

    assert result["governance_closure"]["governance_outcome"] == "refuse"
    assert result["governance_closure"]["packet"]["policy_evaluation"][
        "admissible"
    ] is False


def test_e2e_rehearsal_rejects_tampered_signed_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    private_key, jwks = _material()
    artifact = _sign(_artifact(), private_key)
    artifact["observation"]["measurement_boundary"] = "tampered after signing"

    with pytest.raises(NeoMundiRealObservationPocError) as caught:
        _run(artifact, jwks, tmp_path / "replay")

    assert caught.value.reason == "neomundi_rgc_payload_hash_mismatch"
    assert caught.value.report["stage"] == "provider_verification"


def test_e2e_rehearsal_rejects_stale_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    private_key, jwks = _material()
    stale = (NOW - timedelta(hours=2)).isoformat()
    artifact = _sign(_artifact(stale), private_key)

    with pytest.raises(NeoMundiRealObservationPocError) as caught:
        _run(
            artifact,
            jwks,
            tmp_path / "replay",
            max_age_seconds=3600,
        )

    assert caught.value.reason == "external_measurement_stale"
    assert caught.value.report["stage"] == "generic_external_measurement_boundary"


def test_e2e_rehearsal_rejects_replay_before_governance_closure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    private_key, jwks = _material()
    artifact = _sign(_artifact(), private_key)
    replay_dir = tmp_path / "replay"

    _run(artifact, jwks, replay_dir)

    with pytest.raises(NeoMundiRealObservationPocError) as caught:
        _run(artifact, jwks, replay_dir)

    assert caught.value.reason == "external_measurement_replay_detected"
    assert caught.value.report["stage"] == "generic_external_measurement_boundary"


def test_e2e_rehearsal_rejects_mismatched_trusted_jwks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    private_key, _ = _material()
    artifact = _sign(_artifact(), private_key)
    _, wrong_jwks = _material()

    with pytest.raises(NeoMundiRealObservationPocError) as caught:
        _run(artifact, wrong_jwks, tmp_path / "replay")

    assert caught.value.reason == "neomundi_rgc_signature_invalid"
    assert caught.value.report["stage"] == "provider_verification"
