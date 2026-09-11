from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.governance.authority_evidence_ingestion import (
    ingest_authority_evidence_payload,
)
from veritas_os.governance.external_measurement_evidence import (
    ApprovedExternalMeasurementProvider,
    ExternalMeasurementEvidence,
    ExternalMeasurementProviderVerificationResult,
    ExternalMeasurementTrustPolicy,
    verify_external_measurement_artifact_to_evidence,
)
from veritas_os.governance.external_measurement_governance_closure import (
    ExternalMeasurementGovernanceClosureError,
    close_verified_external_measurement_governance,
)
from veritas_os.governance.human_approval_receipt import (
    HumanApprovalReceipt,
    build_human_approval_state,
)
from veritas_os.security.hash import sha256_of_canonical_json

NOW = datetime(2026, 9, 11, 10, 0, tzinfo=UTC)
POLICY_SNAPSHOT_ID = "policy-closure-001"
REQUESTED_SCOPE = ["poc:review"]


class _ReplayGuard:
    def __init__(self) -> None:
        self.used: set[str] = set()

    def consume_once(self, replay_key: str, *, observed_at: datetime) -> bool:
        del observed_at
        if replay_key in self.used:
            return False
        self.used.add(replay_key)
        return True


class _ProviderVerifier:
    verifier_id = "fixture-external-measurement-verifier"
    verifier_trust_level = "test"
    verifier_policy_id = "fixture-external-measurement-policy"
    verifier_policy_hash = sha256_of_canonical_json(
        {"policy_id": verifier_policy_id, "fixture_only": True}
    )

    def verify(
        self, artifact: dict[str, Any]
    ) -> ExternalMeasurementProviderVerificationResult:
        del artifact
        evidence = ExternalMeasurementEvidence(
            evidence_id="eme-closure-001",
            provider_id="fixture-provider",
            artifact_id="fixture-observation-001",
            artifact_type="fixture_measurement",
            artifact_version="1.0",
            payload_hash="a" * 64,
            observed_at="2026-09-11T09:55:00+00:00",
            issued_at="2026-09-11T09:55:00+00:00",
            expires_at="2026-09-11T11:00:00+00:00",
            replay_token="fixture-replay-001",
            measured_scope={"system": "fixture", "scope": "runtime_state"},
            measurement_coverage=1.0,
            semantic_facts={"status": "within_bounds", "advisory_only": True},
            provenance={"fixture": True},
            metadata={
                "measurement_only": True,
                "execution_permission_changed": False,
            },
        )
        return ExternalMeasurementProviderVerificationResult(
            verified=True,
            evidence=evidence,
            verifier_id=self.verifier_id,
            verifier_trust_level=self.verifier_trust_level,
            verifier_policy_id=self.verifier_policy_id,
            verifier_policy_hash=self.verifier_policy_hash,
            key_id="fixture-key-001",
            algorithm="fixture-signature",
            semantic_consistent=True,
            reason="fixture_verified",
        )


def _verified_measurement() -> tuple[Any, ExternalMeasurementTrustPolicy]:
    verifier = _ProviderVerifier()
    policy = ExternalMeasurementTrustPolicy(
        policy_id="external-measurement-closure-trust-policy",
        approved_providers=[
            ApprovedExternalMeasurementProvider(
                provider_id="fixture-provider",
                verifier_id=verifier.verifier_id,
                verifier_trust_level=verifier.verifier_trust_level,
                verifier_policy_id=verifier.verifier_policy_id,
                verifier_policy_hash=verifier.verifier_policy_hash,
            )
        ],
        max_age_seconds=3600,
        max_future_skew_seconds=60,
        require_expiry=True,
    )
    proof = verify_external_measurement_artifact_to_evidence(
        {"fixture": "measurement"},
        provider_verifier=verifier,
        trust_policy=policy,
        replay_guard=_ReplayGuard(),
        now=NOW,
    )
    return proof, policy


def _contract() -> ActionClassContract:
    return ActionClassContract(
        id="external_measurement_closure",
        version="1.0.0",
        domain="poc",
        action_class="external_measurement_review",
        description="Review external measurement evidence under VERITAS governance.",
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
            "authority_evidence_id": "aev-closure-001",
            "action_contract_id": "external_measurement_closure",
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


def _approval_state(authority_id: str = "aev-closure-001") -> dict[str, Any]:
    receipt = HumanApprovalReceipt(
        approval_receipt_id="har-closure-001",
        decision_id="decision-closure-001",
        execution_intent_id="intent-closure-001",
        approver_identity="human:fixture-approver",
        approver_role="governance_reviewer",
        approved_action_class="external_measurement_review",
        approved_scope=list(REQUESTED_SCOPE),
        approval_basis_refs=["review:closure-001"],
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
        "evaluation_id": "policy-eval-closure-001",
        "policy_snapshot_id": POLICY_SNAPSHOT_ID,
        "admissible": admissible,
        "reasons": ["fixture_policy_evaluated_independently"],
    }


def _close(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authority: Any | None = None,
    approval_state: dict[str, Any] | None = None,
    admissible: bool = True,
) -> Any:
    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    proof, trust_policy = _verified_measurement()
    return close_verified_external_measurement_governance(
        verified_measurement=proof,
        measurement_trust_policy=trust_policy,
        action_contract=_contract(),
        authority_evidence=_authority() if authority is None else authority,
        human_approval_state=(
            _approval_state() if approval_state is None else approval_state
        ),
        policy_evaluation=_policy_evaluation(admissible=admissible),
        requested_scope=list(REQUESTED_SCOPE),
        required_evidence_metadata={"governance_case_record": {"present": True}},
        evidence_freshness_metadata={"governance_case_record": {"fresh": True}},
        actor_identity="agent:poc-reviewer",
        now=NOW,
    )


def test_valid_independent_governance_inputs_produce_non_executing_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _close(monkeypatch)

    assert result.governance_outcome == "commit"
    assert result.authority_validation_status == "pass"
    assert result.packet["governance_decision"]["execution_performed"] is False
    assert result.packet["claim_boundary"]["bind_authorization_created"] is False
    assert result.packet["claim_boundary"]["credentials_accessed"] is False
    assert result.packet["claim_boundary"]["network_dispatch_performed"] is False
    assert result.packet["claim_boundary"]["external_effect_performed"] is False
    assert result.packet["packet_hash"] == result.packet_hash


def test_verified_measurement_does_not_replace_missing_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    proof, trust_policy = _verified_measurement()
    result = close_verified_external_measurement_governance(
        verified_measurement=proof,
        measurement_trust_policy=trust_policy,
        action_contract=_contract(),
        authority_evidence=None,
        human_approval_state=_approval_state(),
        policy_evaluation=_policy_evaluation(),
        requested_scope=list(REQUESTED_SCOPE),
        required_evidence_metadata={"governance_case_record": {"present": True}},
        evidence_freshness_metadata={"governance_case_record": {"fresh": True}},
        actor_identity="agent:poc-reviewer",
        now=NOW,
    )

    assert result.governance_outcome == "block"
    assert result.authority_validation_status == "fail"
    assert result.packet["authority"]["authority_evidence_id"] is None
    assert (
        result.packet["claim_boundary"]["external_measurement_converted_to_authority"]
        is False
    )


def test_verified_measurement_does_not_replace_missing_human_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_approval = build_human_approval_state(
        None,
        requested_scope=list(REQUESTED_SCOPE),
    )
    result = _close(monkeypatch, approval_state=missing_approval)

    assert result.governance_outcome == "block"
    assert result.packet["human_approval"]["approved"] is False
    assert (
        result.packet["claim_boundary"][
            "external_measurement_converted_to_human_approval"
        ]
        is False
    )


def test_independent_policy_refusal_is_not_overridden_by_measurement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _close(monkeypatch, admissible=False)

    assert result.governance_outcome == "refuse"
    assert result.packet["policy_evaluation"]["admissible"] is False
    assert (
        result.packet["claim_boundary"][
            "external_measurement_directly_controls_governance_outcome"
        ]
        is False
    )


def test_tampered_runtime_sealed_measurement_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERITAS_POSTURE", "dev")
    proof, trust_policy = _verified_measurement()
    tampered = replace(proof, evidence_hash="0" * 64)

    with pytest.raises(
        ExternalMeasurementGovernanceClosureError,
        match="external_measurement_closure_measurement_invalid",
    ):
        close_verified_external_measurement_governance(
            verified_measurement=tampered,
            measurement_trust_policy=trust_policy,
            action_contract=_contract(),
            authority_evidence=_authority(),
            human_approval_state=_approval_state(),
            policy_evaluation=_policy_evaluation(),
            requested_scope=list(REQUESTED_SCOPE),
            required_evidence_metadata={
                "governance_case_record": {"present": True}
            },
            evidence_freshness_metadata={
                "governance_case_record": {"fresh": True}
            },
            actor_identity="agent:poc-reviewer",
            now=NOW,
        )
