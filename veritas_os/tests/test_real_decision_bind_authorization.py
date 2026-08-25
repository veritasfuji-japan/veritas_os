"""Tests for the verified decision-to-authorization composition boundary."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.real_decision_bind_authorization import (
    RealDecisionBindAuthorizationError,
    _require_exact_intent,
    issue_verified_real_decision_bind_authorization,
)


def _intent(**changes: object) -> ExecutionIntent:
    values = {
        "execution_intent_id": "intent-live-decision",
        "decision_id": "cda:v1:sha256:" + "a" * 64,
        "request_id": "request-live-decision",
        "policy_snapshot_id": "policy-live-v1",
        "actor_identity": "operator:live",
        "target_system": "billing",
        "target_resource": "https://api.example.invalid/v1/billing",
        "intended_action": "create_billing_effect",
        "evidence_refs": ["authority:live"],
        "decision_hash": "a" * 64,
        "decision_ts": "2026-08-25T00:00:00.000000Z",
    }
    values.update(changes)
    return ExecutionIntent(**values)


def test_exact_intent_accepts_object_id_and_content_hash() -> None:
    intent = _intent()
    _require_exact_intent(
        intent,
        intent.to_dict(),
        intent.execution_intent_id,
        hash_execution_intent(intent),
        boundary="SOURCE",
    )


@pytest.mark.parametrize(
    ("actual", "actual_id", "actual_hash"),
    [
        (_intent(decision_hash="b" * 64).to_dict(), "intent-live-decision", None),
        (_intent().to_dict(), "foreign-intent", None),
        (_intent().to_dict(), "intent-live-decision", "0" * 64),
        (
            _intent(target_resource="https://foreign.invalid/effect").to_dict(),
            "intent-live-decision",
            None,
        ),
    ],
)
def test_exact_intent_rejects_foreign_or_tampered_lineage(
    actual: dict[str, object],
    actual_id: str,
    actual_hash: str | None,
) -> None:
    expected = _intent()
    with pytest.raises(
        RealDecisionBindAuthorizationError,
        match="RDBA_SOURCE_EXECUTION_INTENT_MISMATCH",
    ):
        _require_exact_intent(
            expected,
            actual,
            actual_id,
            actual_hash or hash_execution_intent(ExecutionIntent(**actual)),
            boundary="SOURCE",
        )


def test_public_boundary_has_no_caller_lineage_override_parameters() -> None:
    parameters = inspect.signature(
        issue_verified_real_decision_bind_authorization
    ).parameters
    forbidden = {
        "decision_id",
        "decision_hash",
        "decision_ts",
        "request_id",
        "execution_intent_id",
        "execution_intent_hash",
    }
    assert forbidden.isdisjoint(parameters)


def test_decision_lineage_mismatch_stops_before_source_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cda = SimpleNamespace(
        decision_id="cda:v1:sha256:" + "a" * 64,
        decision_hash="a" * 64,
        decision_ts="2026-08-25T00:00:00.000000Z",
        request_id="request-live-decision",
    )
    foreign = _intent(decision_hash="b" * 64)
    monkeypatch.setattr(
        "veritas_os.policy.real_decision_bind_authorization."
        "verify_canonical_decision_artifact",
        lambda value: SimpleNamespace(is_valid=True, artifact=cda),
    )
    monkeypatch.setattr(
        "veritas_os.policy.real_decision_bind_authorization."
        "try_promote_verified_canonical_decision_candidate_to_execution_intent",
        lambda *args, **kwargs: SimpleNamespace(
            promoted=True,
            execution_intent=foreign,
        ),
    )
    source_called = False

    def source_verifier(value: object) -> object:
        nonlocal source_called
        source_called = True
        return value

    monkeypatch.setattr(
        "veritas_os.policy.real_decision_bind_authorization."
        "verify_live_adapter_dry_run_bind_authorization_gate_review_packet",
        source_verifier,
    )
    with pytest.raises(
        RealDecisionBindAuthorizationError,
        match="RDBA_DECISION_LINEAGE_MISMATCH",
    ):
        issue_verified_real_decision_bind_authorization(
            canonical_decision_artifact={},
            candidate={},
            policy_snapshot_id="policy-live-v1",
            source_gate_review_packet={},
            signed_authorization_decision_artifact={},
            valid_from="2026-08-25T00:00:00Z",
            valid_until="2026-08-25T00:05:00Z",
            governance_inputs=SimpleNamespace(),
            trust_inputs=SimpleNamespace(),
            authorization_issuer_signer=SimpleNamespace(),
        )
    assert source_called is False
