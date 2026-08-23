"""Regression tests for deterministic Real Bind Authorization runtime proof digests."""

from __future__ import annotations

from veritas_os.governance.predicates import PredicateResult
from veritas_os.governance.runtime_authority import RuntimeAuthorityValidationResult
from veritas_os.policy.live_adapter_bind_authorization_governance import (
    _runtime_result_digest,
    _runtime_result_payload,
)

EVALUATED_AT = "2026-08-23T00:00:00+00:00"


def _result(*, aggregate_evaluated_at: str) -> RuntimeAuthorityValidationResult:
    predicate = PredicateResult(
        predicate_id="p-action-contract-present",
        predicate_type="action_contract_present",
        status="pass",
        reason="action_contract_present",
        evaluated_at=EVALUATED_AT,
    )
    return RuntimeAuthorityValidationResult(
        status="pass",
        recommended_outcome="commit",
        passed_predicates=[predicate],
        evaluated_at=aggregate_evaluated_at,
        reason_summary="all_predicates_passed",
    )


def test_runtime_governance_digest_uses_deterministic_predicate_evaluation_time() -> None:
    first = _result(aggregate_evaluated_at="2026-08-23T00:00:01+00:00")
    second = _result(aggregate_evaluated_at="2026-08-23T00:00:02+00:00")

    assert _runtime_result_payload(first)["evaluated_at"] == EVALUATED_AT
    assert _runtime_result_payload(second)["evaluated_at"] == EVALUATED_AT
    assert _runtime_result_digest(first) == _runtime_result_digest(second)
