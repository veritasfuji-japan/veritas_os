from __future__ import annotations

from datetime import datetime, timezone

import pytest

from veritas_os.policy import human_approval_requirement_resolution as resolution
from veritas_os.policy import live_adapter_dry_run_bind_authorization_gate_review_v2 as gate_v2
from veritas_os.policy import live_adapter_dry_run_final_bind_authorization_readiness_v2 as final_v2
from veritas_os.policy import live_adapter_dry_run_human_approval_not_required_linkage as linkage
from veritas_os.policy.live_adapter_dry_run_bind_authorization_gate_review import (
    ACKNOWLEDGEMENTS as GATE_ACKNOWLEDGEMENTS,
    OUTCOMES as GATE_OUTCOMES,
)
from veritas_os.policy.live_adapter_dry_run_final_bind_authorization_readiness import (
    ACKNOWLEDGEMENTS as FINAL_ACKNOWLEDGEMENTS,
    OUTCOMES as FINAL_OUTCOMES,
)
from veritas_os.tests.test_live_adapter_dry_run_human_approval_not_required_linkage import (
    _AuthorityPacket,
    _contract,
    _patch_source_verifier,
)

T0 = datetime(2026, 9, 5, 5, 10, tzinfo=timezone.utc)


def _final_decision(*, accepted: bool = True, **changes):
    value = {
        "final_bind_authorization_readiness_review_decision_id": (
            "final-review:no-approval:v2"
        ),
        "reviewer_id": "operator:alice",
        "reviewer_role": "bind-readiness-reviewer",
        "reviewer_attestation": "I reviewed local no-approval readiness only.",
        "reviewed_at": T0.isoformat(),
        "review_outcome": FINAL_OUTCOMES[0] if accepted else FINAL_OUTCOMES[1],
        "review_reason": "contract-bound no-approval route reviewed",
        **{field: True for field in FINAL_ACKNOWLEDGEMENTS},
    }
    value.update(changes)
    return value


def _gate_decision(*, passed: bool = True, **changes):
    value = {
        "bind_authorization_gate_review_decision_id": "gate-review:no-approval:v2",
        "reviewer_id": "operator:alice",
        "reviewer_role": "bind-gate-reviewer",
        "reviewer_attestation": "I reviewed local no-approval gate evidence only.",
        "reviewed_at": T0.isoformat(),
        "review_outcome": GATE_OUTCOMES[0] if passed else GATE_OUTCOMES[1],
        "review_reason": "deterministic local no-approval gate review",
        **{field: True for field in GATE_ACKNOWLEDGEMENTS},
    }
    value.update(changes)
    return value


def _no_approval_linkage(monkeypatch: pytest.MonkeyPatch):
    _patch_source_verifier(monkeypatch)
    source = _AuthorityPacket()
    requirement = resolution.build_human_approval_requirement_resolution_packet(
        source,
        _contract(required=False),
        T0,
    )
    return linkage.build_live_adapter_dry_run_human_approval_not_required_linkage_packet(
        source,
        requirement,
        T0,
    )


def _final(monkeypatch: pytest.MonkeyPatch, *, accepted: bool = True):
    return final_v2.build_live_adapter_dry_run_final_bind_authorization_readiness_v2_packet(
        _no_approval_linkage(monkeypatch),
        _final_decision(accepted=accepted),
        T0,
    )


def test_contract_bound_no_approval_route_reaches_native_v2_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final = _final(monkeypatch)
    gate = gate_v2.build_live_adapter_dry_run_bind_authorization_gate_review_v2_packet(
        final,
        _gate_decision(),
        T0,
    )

    assert final.human_approval_state == "NOT_REQUIRED"
    assert final.final_readiness_state == "READY_FOR_FUTURE_BIND_AUTHORIZATION_GATE"
    assert gate.human_approval_state == "NOT_REQUIRED"
    assert gate.gate_review_state == (
        "PASSED_FOR_FUTURE_BIND_AUTHORIZATION_ARTIFACT"
    )
    assert gate.bind_authorization_gate_review_result.gate_review_passed is True
    assert (
        gate.bind_authorization_gate_review_result
        .source_human_approval_not_required_by_action_contract
        is True
    )
    assert gate.human_approval_created is False
    assert gate.execution_authority_created is False
    assert gate.bind_authorization_created is False
    assert gate.bind_invoked is False
    assert gate.bind_receipt_created is False
    assert gate.credential_material_accessed is False
    assert gate.authorization_header_constructed is False
    assert gate.request_dispatched is False
    assert gate.network_used is False
    assert gate.external_effect_occurred is False
    assert (
        gate_v2.verify_live_adapter_dry_run_bind_authorization_gate_review_v2_packet(
            gate
        )
        == gate
    )


def test_rejected_final_readiness_cannot_reach_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final = _final(monkeypatch, accepted=False)
    assert final.fail_closed is True
    assert final.final_readiness_state == (
        "NOT_READY_FOR_FUTURE_BIND_AUTHORIZATION_GATE"
    )

    with pytest.raises(
        gate_v2.LiveAdapterDryRunBindAuthorizationGateReviewV2Error,
        match="LADBAGRV2_SOURCE_REJECTED",
    ):
        gate_v2.build_live_adapter_dry_run_bind_authorization_gate_review_v2_packet(
            final,
            _gate_decision(),
            T0,
        )


def test_rejected_gate_is_valid_fail_closed_non_effect_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = gate_v2.build_live_adapter_dry_run_bind_authorization_gate_review_v2_packet(
        _final(monkeypatch),
        _gate_decision(passed=False),
        T0,
    )

    assert gate.fail_closed is True
    assert gate.gate_review_state == (
        "FAILED_FOR_FUTURE_BIND_AUTHORIZATION_ARTIFACT"
    )
    assert gate.bind_authorization_created is False
    assert gate.execution_authority_created is False
    assert gate.external_effect_occurred is False


def test_final_packet_hash_tamper_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final = _final(monkeypatch)
    raw = final.model_dump(mode="python")
    raw["final_bind_authorization_readiness_recorded_at"] = (
        "2026-09-05T05:11:00+00:00"
    )

    with pytest.raises(
        final_v2.LiveAdapterDryRunFinalBindAuthorizationReadinessV2Error,
        match="LADFBARV2_HASH_MISMATCH",
    ):
        final_v2.verify_live_adapter_dry_run_final_bind_authorization_readiness_v2_packet(
            raw
        )


def test_gate_packet_hash_tamper_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = gate_v2.build_live_adapter_dry_run_bind_authorization_gate_review_v2_packet(
        _final(monkeypatch),
        _gate_decision(),
        T0,
    )
    raw = gate.model_dump(mode="python")
    raw["bind_authorization_gate_review_recorded_at"] = (
        "2026-09-05T05:12:00+00:00"
    )

    with pytest.raises(
        gate_v2.LiveAdapterDryRunBindAuthorizationGateReviewV2Error,
        match="LADBAGRV2_HASH_MISMATCH",
    ):
        gate_v2.verify_live_adapter_dry_run_bind_authorization_gate_review_v2_packet(
            raw
        )
