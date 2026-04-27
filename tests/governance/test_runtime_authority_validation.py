"""Tests for deterministic runtime authority validation."""

from __future__ import annotations

from datetime import datetime

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.governance.authority_evidence import AuthorityEvidence, VerificationResult
from veritas_os.governance.predicates import PredicateResult
from veritas_os.governance.runtime_authority import RuntimeAuthorityValidator


def _contract(**overrides: object) -> ActionClassContract:
    base = {
        "id": "aml_kyc_customer_risk_escalation",
        "version": "1.0.0",
        "domain": "aml",
        "action_class": "customer_risk_escalation",
        "description": "Escalate customer risk decisions under AML/KYC policy.",
        "declared_intent": "Escalate suspicious customer risk for review.",
        "allowed_scope": ["customer:risk_escalation", "customer:case_note"],
        "prohibited_scope": ["customer:fund_transfer"],
        "authority_sources": ["policy.register.aml"],
        "required_evidence": ["kyc_status", "sanctions_screening"],
        "evidence_freshness": {"kyc_status": "P30D", "sanctions_screening": "P1D"},
        "irreversibility": {"boundary": "escalation_dispatch", "level": "medium"},
        "human_approval_rules": {"minimum_approvals": 0},
        "refusal_conditions": ["authority_indeterminate"],
        "escalation_conditions": ["high_risk_flag"],
        "default_failure_mode": "fail_closed",
        "metadata": {"regulated": True},
    }
    base.update(overrides)
    return ActionClassContract(**base)


def _authority(**overrides: object) -> AuthorityEvidence:
    base = {
        "authority_evidence_id": "aev-001",
        "action_contract_id": "aml_kyc_customer_risk_escalation",
        "action_contract_version": "1.0.0",
        "actor_identity": "operator:alice",
        "actor_role": "aml_reviewer",
        "authority_source_refs": ["policy.register.aml"],
        "role_or_policy_basis": ["role:aml_reviewer"],
        "scope_grants": ["customer:risk_escalation", "customer:case_note"],
        "scope_limitations": ["customer:fund_transfer"],
        "validity_window": {
            "issued_at": "2026-04-25T00:00:00",
            "valid_from": "2026-04-25T00:00:00",
            "valid_until": "2026-04-30T00:00:00",
        },
        "issued_at": "2026-04-25T00:00:00",
        "valid_from": "2026-04-25T00:00:00",
        "valid_until": "2026-04-30T00:00:00",
        "revalidated_at": "2026-04-26T00:00:00",
        "policy_snapshot_id": "policy-snapshot-001",
        "evidence_hash": "",
        "verification_result": VerificationResult.VALID,
        "failure_reasons": [],
        "metadata": {"issuer": "governance-control-plane"},
    }
    base.update(overrides)
    return AuthorityEvidence(**base)


def _required_evidence(fresh: object = True, present: bool = True) -> dict[str, dict[str, object]]:
    return {
        "kyc_status": {"present": present, "fresh": fresh},
        "sanctions_screening": {"present": present, "fresh": fresh},
    }


def _validate(**overrides: object):
    validator = RuntimeAuthorityValidator()
    payload = {
        "action_contract": _contract(),
        "authority_evidence": _authority(),
        "requested_scope": ["customer:risk_escalation"],
        "required_evidence_metadata": _required_evidence(),
        "policy_snapshot_id": "policy-snapshot-001",
        "actor_identity": "operator:alice",
        "human_approval_state": {"approved": True},
        "bind_context_metadata": {"session_id": "bind-001"},
        "now": datetime.fromisoformat("2026-04-26T00:00:00"),
    }
    payload.update(overrides)
    return validator.validate(**payload)


def test_valid_internal_escalation_is_commit_recommendation() -> None:
    result = _validate(human_approval_state={"approved": False})

    assert result.status == "pass"
    assert result.recommended_outcome == "commit"


def test_missing_action_contract_is_block() -> None:
    result = _validate(action_contract=None)

    assert result.recommended_outcome == "block"


def test_invalid_action_contract_is_block() -> None:
    result = _validate(authority_evidence=_authority(action_contract_version="2.0.0"))

    assert result.recommended_outcome == "block"


def test_missing_authority_evidence_is_block() -> None:
    result = _validate(authority_evidence=None)

    assert result.recommended_outcome == "block"


def test_expired_authority_is_block() -> None:
    result = _validate(authority_evidence=_authority(valid_until="2026-04-01T00:00:00"))

    assert result.recommended_outcome == "block"


def test_prohibited_scope_is_block() -> None:
    result = _validate(requested_scope=["customer:fund_transfer"])

    assert result.recommended_outcome == "block"


def test_scope_expansion_is_block() -> None:
    result = _validate(requested_scope=["customer:unlisted_scope"])

    assert result.recommended_outcome == "block"


def test_missing_required_evidence_is_block() -> None:
    result = _validate(required_evidence_metadata=_required_evidence(present=False))

    assert result.recommended_outcome == "block"


def test_stale_evidence_escalate_or_block_by_contract() -> None:
    result_escalate = _validate(
        action_contract=_contract(escalation_conditions=["stale_evidence"]),
        required_evidence_metadata=_required_evidence(fresh=False),
    )
    result_block = _validate(required_evidence_metadata=_required_evidence(fresh=False))

    assert result_escalate.recommended_outcome == "escalate"
    assert result_block.recommended_outcome == "block"


def test_unresolved_policy_snapshot_is_block() -> None:
    result = _validate(policy_snapshot_id="")

    assert result.recommended_outcome == "block"


def test_missing_actor_identity_is_block() -> None:
    result = _validate(actor_identity="")

    assert result.recommended_outcome == "block"


def test_high_irreversibility_missing_human_approval_is_block() -> None:
    result = _validate(
        action_contract=_contract(
            irreversibility={"boundary": "funds_committed", "level": "high"},
            human_approval_rules={"minimum_approvals": 1},
        ),
        human_approval_state={"approved": False},
    )

    assert result.recommended_outcome == "block"


def test_validator_exception_is_fail_closed() -> None:
    result = _validate(authority_evidence=_authority(valid_until="invalid-date"))

    assert result.status == "fail"
    assert result.recommended_outcome == "block"
    assert "validator_exception" in result.refusal_basis


def test_unknown_critical_predicate_is_fail_closed_block() -> None:
    validator = RuntimeAuthorityValidator()
    result = validator._build_result(
        predicates=[
            PredicateResult(
                predicate_id="p-unknown-critical",
                predicate_type="unknown_predicate_type",  # type: ignore[arg-type]
                status="pass",
                reason="unknown_runtime_signal",
                severity="critical",
                metadata={"runtime_predicate_type": "unknown_predicate_type"},
            ),
            PredicateResult(
                predicate_id="p-known",
                predicate_type="action_contract_valid",
                status="pass",
                reason="action_contract_valid",
            ),
        ],
        action_contract=_contract(),
    )

    assert result.status == "fail"
    assert result.recommended_outcome == "block"
    assert "unknown_critical_predicate" in result.reason_summary
