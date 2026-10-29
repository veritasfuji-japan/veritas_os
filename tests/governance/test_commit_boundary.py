"""Tests for irreversible CommitBoundaryEvaluator."""

from __future__ import annotations

from datetime import datetime
from dataclasses import replace
from types import SimpleNamespace

import pytest

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.governance.authority_evidence import AuthorityEvidence, VerificationResult
from veritas_os.governance.commit_boundary import CommitBoundaryEvaluator
from veritas_os.governance.runtime_authority import (
    RuntimeAuthorityValidationResult,
    RuntimeAuthorityValidator,
)


FIXED_NOW = datetime.fromisoformat("2026-04-26T00:00:00+00:00")


def _contract(**overrides: object) -> ActionClassContract:
    base = {
        "id": "aml_kyc_customer_risk_escalation",
        "version": "1.0.0",
        "domain": "aml",
        "action_class": "customer_risk_escalation",
        "description": "Escalate customer risk decisions under AML/KYC policy.",
        "declared_intent": "Escalate suspicious customer risk for review.",
        "allowed_scope": ["customer:risk_escalation", "customer:case_note"],
        "prohibited_scope": ["account:freeze", "customer:notification"],
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
        "scope_limitations": ["account:freeze", "customer:notification"],
        "validity_window": {
            "issued_at": "2026-04-25T00:00:00+00:00",
            "valid_from": "2026-04-25T00:00:00+00:00",
            "valid_until": "2026-04-30T00:00:00+00:00",
        },
        "issued_at": "2026-04-25T00:00:00+00:00",
        "valid_from": "2026-04-25T00:00:00+00:00",
        "valid_until": "2026-04-30T00:00:00+00:00",
        "revalidated_at": "2026-04-26T00:00:00+00:00",
        "policy_snapshot_id": "policy-snapshot-001",
        "evidence_hash": "hash-001",
        "verification_result": VerificationResult.VALID,
        "failure_reasons": [],
        "metadata": {"issuer": "governance-control-plane"},
    }
    base.update(overrides)
    return AuthorityEvidence(**base)


def _required_evidence(present: bool = True) -> dict[str, dict[str, object]]:
    return {
        "kyc_status": {"present": present},
        "sanctions_screening": {"present": present},
    }


def _freshness(fresh: object = True) -> dict[str, dict[str, object]]:
    return {
        "kyc_status": {"fresh": fresh},
        "sanctions_screening": {"fresh": fresh},
    }


def _evaluate(**overrides: object):
    evaluator = CommitBoundaryEvaluator()
    payload = {
        "execution_intent": {
            "action_class": "customer_risk_escalation",
            "admissible": True,
        },
        "action_contract": _contract(),
        "authority_evidence": _authority(),
        "requested_scope": ["customer:risk_escalation"],
        "required_evidence_metadata": _required_evidence(),
        "evidence_freshness_metadata": _freshness(),
        "policy_snapshot_id": "policy-snapshot-001",
        "actor_identity": "operator:alice",
        "human_approval_state": {"approved": True},
        "bind_context_metadata": {"session_id": "bind-001"},
        "now": FIXED_NOW,
    }
    payload.update(overrides)
    return evaluator.evaluate(**payload)


def test_allowed_internal_escalation_commits() -> None:
    result = _evaluate(human_approval_state={"approved": False})

    assert result.commit_boundary_result == "commit"


def test_missing_action_contract_blocks() -> None:
    result = _evaluate(action_contract=None)

    assert result.commit_boundary_result == "block"


def test_invalid_action_contract_blocks() -> None:
    result = _evaluate(action_contract=_contract(id=""))

    assert result.commit_boundary_result == "block"


def test_missing_authority_evidence_blocks() -> None:
    result = _evaluate(authority_evidence=None)

    assert result.commit_boundary_result == "block"


def test_expired_authority_blocks() -> None:
    result = _evaluate(authority_evidence=_authority(
        issued_at="2026-03-01T00:00:00+00:00",
        valid_from="2026-03-01T00:00:00+00:00",
        valid_until="2026-04-01T00:00:00+00:00",
        validity_window={
            "issued_at": "2026-03-01T00:00:00+00:00",
            "valid_from": "2026-03-01T00:00:00+00:00",
            "valid_until": "2026-04-01T00:00:00+00:00",
        },
    ))

    assert result.commit_boundary_result == "block"


def test_indeterminate_authority_blocks() -> None:
    result = _evaluate(
        authority_evidence=_authority(verification_result=VerificationResult.INDETERMINATE)
    )

    assert result.commit_boundary_result == "block"


def test_prohibited_account_freeze_blocks() -> None:
    result = _evaluate(requested_scope=["account:freeze"])

    assert result.commit_boundary_result == "block"


def test_prohibited_customer_notification_blocks() -> None:
    result = _evaluate(requested_scope=["customer:notification"])

    assert result.commit_boundary_result == "block"


def test_missing_evidence_blocks() -> None:
    result = _evaluate(required_evidence_metadata=_required_evidence(present=False))

    assert result.commit_boundary_result == "block"


def test_stale_evidence_escalates_if_contract_permits() -> None:
    result = _evaluate(
        action_contract=_contract(escalation_conditions=["stale_evidence"]),
        evidence_freshness_metadata=_freshness(fresh=False),
    )

    assert result.commit_boundary_result == "escalate"


def test_stale_evidence_blocks_without_escalation_path() -> None:
    result = _evaluate(evidence_freshness_metadata=_freshness(fresh=False))

    assert result.commit_boundary_result == "block"


def test_missing_human_approval_blocks_high_irreversibility_action() -> None:
    result = _evaluate(
        action_contract=_contract(
            irreversibility={"boundary": "funds_committed", "level": "high"},
            human_approval_rules={"minimum_approvals": 1},
        ),
        human_approval_state={"approved": False},
    )

    assert result.commit_boundary_result == "block"


def test_undefined_irreversibility_boundary_blocks() -> None:
    result = _evaluate(action_contract=_contract(irreversibility={"boundary": "", "level": "high"}))

    assert result.commit_boundary_result == "block"


def test_validator_exception_blocks() -> None:
    result = _evaluate(authority_evidence=_authority(valid_until="invalid-date"))

    assert result.commit_boundary_result == "block"


def test_repeated_evaluation_is_deterministic() -> None:
    first = _evaluate()
    second = _evaluate()

    assert first == second


def test_predicate_order_is_deterministic() -> None:
    result = _evaluate()
    predicate_ids = [item.predicate_id for item in result.admissibility_predicates]

    assert predicate_ids == sorted(predicate_ids)


def _valid_validator_result() -> RuntimeAuthorityValidationResult:
    """Use the real validator's passing predicates as the injection control."""
    evaluation = _evaluate()
    assert evaluation.commit_boundary_result == "commit"
    return RuntimeAuthorityValidationResult(
        status="pass", recommended_outcome="commit",
        passed_predicates=evaluation.admissibility_predicates,
    )


@pytest.mark.parametrize("recommendation", [None, "", "allow", "COMMIT", True, 0, [], {}])
def test_unknown_validator_recommendation_refuses(monkeypatch, recommendation) -> None:
    result = replace(_valid_validator_result(), recommended_outcome=recommendation)
    monkeypatch.setattr(RuntimeAuthorityValidator, "validate", lambda *_a, **_k: result)
    assert _evaluate().commit_boundary_result == "refuse"


def test_missing_validator_recommendation_refuses(monkeypatch) -> None:
    values = vars(_valid_validator_result()).copy()
    values.pop("recommended_outcome")
    result = SimpleNamespace(**values)
    monkeypatch.setattr(RuntimeAuthorityValidator, "validate", lambda *_a, **_k: result)
    assert _evaluate().commit_boundary_result == "refuse"


@pytest.mark.parametrize("status", ["fail", None, "", "PASS", True, 0])
def test_commit_requires_explicit_passing_validator_status(monkeypatch, status) -> None:
    result = replace(_valid_validator_result(), status=status)
    monkeypatch.setattr(RuntimeAuthorityValidator, "validate", lambda *_a, **_k: result)
    assert _evaluate().commit_boundary_result == "refuse"


@pytest.mark.parametrize("bucket, status", [
    ("failed_predicates", "fail"), ("stale_predicates", "stale"),
    ("missing_predicates", "missing"), ("indeterminate_predicates", "indeterminate"),
])
def test_commit_cannot_override_negative_predicates(monkeypatch, bucket, status) -> None:
    result = _valid_validator_result()
    negative = replace(result.passed_predicates[0], status=status)
    result = replace(result, **{bucket: [negative]})
    monkeypatch.setattr(RuntimeAuthorityValidator, "validate", lambda *_a, **_k: result)
    evaluation = _evaluate()
    assert negative in evaluation.admissibility_predicates
    assert evaluation.commit_boundary_result == "refuse"


@pytest.mark.parametrize("status", ["fail", "stale", "missing", "indeterminate", "unknown"])
def test_passed_bucket_must_contain_only_passing_predicates(monkeypatch, status) -> None:
    result = _valid_validator_result()
    result = replace(result, passed_predicates=[
        replace(result.passed_predicates[0], status=status),
        *result.passed_predicates[1:],
    ])
    monkeypatch.setattr(RuntimeAuthorityValidator, "validate", lambda *_a, **_k: result)
    assert _evaluate().commit_boundary_result == "refuse"


@pytest.mark.parametrize("basis", ["refusal_basis", "escalation_basis"])
def test_commit_cannot_override_deny_basis(monkeypatch, basis) -> None:
    result = replace(_valid_validator_result(), **{basis: ["review-required"]})
    monkeypatch.setattr(RuntimeAuthorityValidator, "validate", lambda *_a, **_k: result)
    assert _evaluate().commit_boundary_result == "refuse"


def test_empty_passing_validator_result_does_not_commit(monkeypatch) -> None:
    result = RuntimeAuthorityValidationResult(status="pass", recommended_outcome="commit")
    monkeypatch.setattr(RuntimeAuthorityValidator, "validate", lambda *_a, **_k: result)
    assert _evaluate().commit_boundary_result == "refuse"


@pytest.mark.parametrize("recommendation", ["commit", "block", "refuse", "escalate"])
def test_known_validator_outcomes_keep_their_meaning(monkeypatch, recommendation) -> None:
    result = replace(_valid_validator_result(), recommended_outcome=recommendation)
    monkeypatch.setattr(RuntimeAuthorityValidator, "validate", lambda *_a, **_k: result)
    assert _evaluate().commit_boundary_result == recommendation


@pytest.mark.parametrize("flag", ["false", "true", "", None, 0, 1, [], {}])
def test_present_admissible_flag_requires_boolean_true(flag) -> None:
    evaluation = _evaluate(execution_intent={
        "action_class": "customer_risk_escalation", "admissible": flag,
    })
    assert evaluation.commit_boundary_result == "refuse"


@pytest.mark.parametrize("intent", [None, [], ["action"], 0, True])
def test_unsupported_intent_shape_refuses(intent) -> None:
    assert _evaluate(execution_intent=intent).commit_boundary_result == "refuse"


@pytest.mark.parametrize("intent, expected", [
    ({"action_class": "customer_risk_escalation", "admissible": True}, "commit"),
    ({"action_class": "customer_risk_escalation", "admissible": False}, "refuse"),
    ({"action_class": "other_action", "admissible": True}, "refuse"),
    ({"admissible": True}, "commit"),
    ({"execution_intent_id": "legacy-intent"}, "commit"),
    ("legacy-intent", "commit"), ("", "refuse"), ("   ", "refuse"),
])
def test_intent_controls_and_legacy_omission(intent, expected) -> None:
    assert _evaluate(execution_intent=intent).commit_boundary_result == expected


@pytest.mark.parametrize("missing_authority", [False, True])
def test_real_validator_mixed_stale_and_failed_conditions_never_commit(missing_authority) -> None:
    overrides = {"authority_evidence": None} if missing_authority else {
        "requested_scope": ["account:freeze"],
    }
    evaluation = _evaluate(
        action_contract=_contract(escalation_conditions=["stale_evidence"]),
        evidence_freshness_metadata=_freshness(fresh=False), **overrides,
    )
    assert evaluation.stale_predicates
    assert evaluation.failed_predicates or evaluation.missing_predicates
    assert evaluation.commit_boundary_result == "escalate"


@pytest.mark.parametrize("fresh, expected", [(True, "commit"), (False, "block")])
def test_explicit_freshness_metadata_wins_over_required_metadata(fresh, expected) -> None:
    required = {name: {"present": True, "fresh": not fresh} for name in _required_evidence()}
    evaluation = _evaluate(
        required_evidence_metadata=required, evidence_freshness_metadata=_freshness(fresh),
    )
    assert evaluation.commit_boundary_result == expected
