"""Tests for deterministic local/offline authority evidence ingestion."""

from __future__ import annotations

from datetime import datetime

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.governance.authority_evidence import VerificationResult, validate_authority_evidence
from veritas_os.governance.authority_evidence_ingestion import ingest_authority_evidence_payload
from veritas_os.governance.commit_boundary import CommitBoundaryEvaluator
from veritas_os.governance.runtime_authority import RuntimeAuthorityValidator


FIXED_NOW = datetime.fromisoformat("2026-04-26T00:00:00")


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "authority_evidence_id": "aev-010",
        "action_contract_id": "aml_kyc_customer_risk_escalation",
        "action_contract_version": "1.0.0",
        "actor_identity": "operator:alice",
        "actor_role": "aml_reviewer",
        "authority_source_refs": ["policy.register.aml"],
        "role_or_policy_basis": ["role:aml_reviewer"],
        "scope_grants": ["customer:risk_escalation"],
        "scope_limitations": ["customer:fund_transfer"],
        "issued_at": "2026-04-25T00:00:00",
        "valid_from": "2026-04-25T00:00:00",
        "valid_until": "2026-04-30T00:00:00",
        "policy_snapshot_id": "policy-snapshot-001",
        "verification_result": "valid",
        "metadata": {
            "source_type": "mock_policy_registry",
            "issuer": "governance-control-plane",
        },
    }
    base.update(overrides)
    return base


def _contract() -> ActionClassContract:
    return ActionClassContract(
        id="aml_kyc_customer_risk_escalation",
        version="1.0.0",
        domain="aml",
        action_class="customer_risk_escalation",
        description="Escalate customer risk decisions under AML/KYC policy.",
        declared_intent="Escalate suspicious customer risk for review.",
        allowed_scope=["customer:risk_escalation", "customer:case_note"],
        prohibited_scope=["customer:fund_transfer"],
        authority_sources=["policy.register.aml"],
        required_evidence=["kyc_status"],
        evidence_freshness={"kyc_status": "P30D"},
        irreversibility={"boundary": "escalation_dispatch", "level": "medium"},
        human_approval_rules={"minimum_approvals": 0},
        refusal_conditions=["authority_indeterminate"],
        escalation_conditions=["high_risk_flag"],
        default_failure_mode="fail_closed",
        metadata={"regulated": True},
    )


def test_valid_payload_normalizes_to_authority_evidence() -> None:
    evidence = ingest_authority_evidence_payload(_payload())

    assert evidence.authority_evidence_id == "aev-010"
    assert evidence.verification_result == VerificationResult.VALID
    assert evidence.metadata["source_type"] == "mock_policy_registry"


def test_evidence_hash_is_populated_and_deterministic() -> None:
    payload = _payload()

    first = ingest_authority_evidence_payload(payload)
    second = ingest_authority_evidence_payload(payload)

    assert first.evidence_hash
    assert len(first.evidence_hash) == 64
    assert first == second


def test_alias_fields_are_mapped_correctly() -> None:
    alias_payload = _payload(metadata={})
    del alias_payload["authority_evidence_id"]
    del alias_payload["actor_identity"]
    del alias_payload["valid_until"]
    del alias_payload["scope_grants"]
    alias_payload.update(
        {
            "evidence_id": "aev-alias-001",
            "subject": "operator:bob",
            "expires_at": "2026-04-30T00:00:00",
            "authority_scope": ["customer:risk_escalation"],
            "issuer": "external-issuer",
            "source_type": "external-mock",
        }
    )
    evidence = ingest_authority_evidence_payload(alias_payload)

    assert evidence.authority_evidence_id == "aev-alias-001"
    assert evidence.actor_identity == "operator:bob"
    assert evidence.valid_until == "2026-04-30T00:00:00"
    assert evidence.scope_grants == ["customer:risk_escalation"]
    assert evidence.metadata["issuer"] == "external-issuer"
    assert evidence.metadata["source_type"] == "external-mock"


def test_missing_required_identity_or_action_fields_raise_value_error() -> None:
    invalid_payload = _payload(actor_identity="")

    try:
        ingest_authority_evidence_payload(invalid_payload)
    except ValueError as exc:
        assert "actor_identity_missing" in str(exc)
    else:
        raise AssertionError("expected ValueError for missing actor identity")


def test_unknown_verification_result_defaults_to_indeterminate() -> None:
    evidence = ingest_authority_evidence_payload(_payload(verification_result="not-a-state"))

    assert evidence.verification_result == VerificationResult.INDETERMINATE


def test_expired_evidence_normalizes_and_validation_marks_invalid() -> None:
    evidence = ingest_authority_evidence_payload(_payload(valid_until="2026-04-01T00:00:00"))

    result = validate_authority_evidence(evidence, now=FIXED_NOW)

    assert result.is_valid is False
    assert "authority_expired" in result.failure_reasons


def test_normalized_evidence_can_pass_runtime_and_commit_boundary() -> None:
    evidence = ingest_authority_evidence_payload(_payload())
    contract = _contract()

    validator_result = RuntimeAuthorityValidator().validate(
        action_contract=contract,
        authority_evidence=evidence,
        requested_scope=["customer:risk_escalation"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-snapshot-001",
        actor_identity="operator:alice",
        human_approval_state={"approved": True},
        bind_context_metadata={"session_id": "bind-001"},
        now=FIXED_NOW,
    )
    boundary_result = CommitBoundaryEvaluator().evaluate(
        execution_intent={"action_class": "customer_risk_escalation", "admissible": True},
        action_contract=contract,
        authority_evidence=evidence,
        requested_scope=["customer:risk_escalation"],
        required_evidence_metadata={"kyc_status": {"present": True}},
        evidence_freshness_metadata={"kyc_status": {"fresh": True}},
        policy_snapshot_id="policy-snapshot-001",
        actor_identity="operator:alice",
        human_approval_state={"approved": True},
        bind_context_metadata={"session_id": "bind-001"},
        now=FIXED_NOW,
    )

    assert validator_result.recommended_outcome == "commit"
    assert boundary_result.commit_boundary_result == "commit"


def test_invalid_or_indeterminate_evidence_blocks_runtime_authority() -> None:
    contract = _contract()
    indeterminate = ingest_authority_evidence_payload(_payload(verification_result="unknown"))

    validator_result = RuntimeAuthorityValidator().validate(
        action_contract=contract,
        authority_evidence=indeterminate,
        requested_scope=["customer:risk_escalation"],
        required_evidence_metadata={"kyc_status": {"present": True, "fresh": True}},
        policy_snapshot_id="policy-snapshot-001",
        actor_identity="operator:alice",
        human_approval_state={"approved": True},
        bind_context_metadata={"session_id": "bind-001"},
        now=FIXED_NOW,
    )

    assert validator_result.recommended_outcome == "block"
