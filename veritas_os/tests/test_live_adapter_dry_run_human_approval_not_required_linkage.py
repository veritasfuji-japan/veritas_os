from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import BaseModel, ConfigDict

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.policy import human_approval_requirement_resolution as resolution
from veritas_os.policy import live_adapter_dry_run_human_approval_not_required_linkage as linkage


class _AuthorityLinkageResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    all_required_references_present: bool = True
    all_references_structurally_linked: bool = True
    all_binding_claims_matched: bool = True


class _AuthorityPacket(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    live_adapter_dry_run_authority_evidence_linkage_review_id: str = "authority-linkage-1"
    live_adapter_dry_run_authority_evidence_linkage_review_hash: str = "a" * 64
    execution_intent: dict = {"intended_action": "payments.transfer"}
    execution_intent_id: str = "execution-intent-1"
    execution_intent_hash: str = "b" * 64
    authority_evidence_reference_bundle: dict = {
        "bundle_scope": ["payments:transfer"]
    }
    authority_evidence_linkage_result: _AuthorityLinkageResult = (
        _AuthorityLinkageResult()
    )
    request_dispatch_state: str = "NOT_DISPATCHED"
    request_dispatched: bool = False
    bind_state: str = "NOT_BOUND"
    bind_invoked: bool = False
    authority_state: str = "NOT_AUTHORIZED"
    fail_closed: bool = False


def _contract(*, required: bool) -> ActionClassContract:
    return ActionClassContract(
        id="payments.transfer",
        version="1",
        domain="payments",
        action_class="payment_transfer",
        description="approval-not-required linkage test",
        declared_intent="transfer funds",
        allowed_scope=["payments:transfer"],
        prohibited_scope=["payments:admin"],
        authority_sources=["benchmark-authority"],
        required_evidence=[],
        evidence_freshness={},
        irreversibility={"level": "low"},
        human_approval_rules={
            "required": required,
            "minimum_approvals": 1 if required else 0,
        },
        refusal_conditions=[],
        escalation_conditions=[],
        default_failure_mode="deny",
        metadata={"regulated": False},
    )


def _patch_source_verifier(monkeypatch: pytest.MonkeyPatch) -> None:
    def verify(value):
        if isinstance(value, _AuthorityPacket):
            return value
        return _AuthorityPacket.model_validate(value)

    monkeypatch.setattr(
        resolution,
        "verify_live_adapter_dry_run_authority_evidence_linkage_review_packet",
        verify,
    )
    monkeypatch.setattr(
        linkage,
        "verify_live_adapter_dry_run_authority_evidence_linkage_review_packet",
        verify,
    )


def _resolution(
    monkeypatch: pytest.MonkeyPatch,
    *,
    required: bool = False,
    source: _AuthorityPacket | None = None,
):
    _patch_source_verifier(monkeypatch)
    return resolution.build_human_approval_requirement_resolution_packet(
        source or _AuthorityPacket(),
        _contract(required=required),
        datetime(2026, 9, 5, 5, 0, tzinfo=timezone.utc),
    )


def test_not_required_resolution_links_without_fabricated_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _AuthorityPacket()
    requirement = _resolution(monkeypatch, source=source)

    packet = linkage.build_live_adapter_dry_run_human_approval_not_required_linkage_packet(
        source,
        requirement,
        datetime(2026, 9, 5, 5, 1, tzinfo=timezone.utc),
    )

    assert packet.human_approval_requirement_state == (
        "NOT_REQUIRED_BY_ACTION_CONTRACT"
    )
    assert packet.human_approval_state == "NOT_REQUIRED"
    assert packet.human_approval_reference_count == 0
    assert packet.human_approval_created is False
    assert packet.execution_authority_created is False
    assert packet.bind_authorization_created is False
    assert packet.bind_invoked is False
    assert packet.network_used is False
    assert packet.external_effect_occurred is False
    assert (
        linkage.verify_live_adapter_dry_run_human_approval_not_required_linkage_packet(
            packet
        )
        == packet
    )


def test_required_resolution_cannot_use_no_approval_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _AuthorityPacket()
    requirement = _resolution(monkeypatch, required=True, source=source)

    with pytest.raises(
        linkage.LiveAdapterDryRunHumanApprovalNotRequiredLinkageError,
        match="LADHANR_APPROVAL_IS_REQUIRED",
    ):
        linkage.build_live_adapter_dry_run_human_approval_not_required_linkage_packet(
            source,
            requirement,
            datetime(2026, 9, 5, 5, 2, tzinfo=timezone.utc),
        )


def test_resolution_bound_to_other_source_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = _AuthorityPacket()
    requirement = _resolution(monkeypatch, source=original)
    other = original.model_copy(
        update={
            "live_adapter_dry_run_authority_evidence_linkage_review_id": (
                "authority-linkage-2"
            ),
            "live_adapter_dry_run_authority_evidence_linkage_review_hash": "c" * 64,
        }
    )

    with pytest.raises(
        linkage.LiveAdapterDryRunHumanApprovalNotRequiredLinkageError,
        match="LADHANR_SOURCE_RESOLUTION_MISMATCH",
    ):
        linkage.build_live_adapter_dry_run_human_approval_not_required_linkage_packet(
            other,
            requirement,
            datetime(2026, 9, 5, 5, 3, tzinfo=timezone.utc),
        )


def test_tampered_linkage_packet_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _AuthorityPacket()
    requirement = _resolution(monkeypatch, source=source)
    packet = linkage.build_live_adapter_dry_run_human_approval_not_required_linkage_packet(
        source,
        requirement,
        datetime(2026, 9, 5, 5, 4, tzinfo=timezone.utc),
    )
    raw = packet.model_dump(mode="python")
    raw["linkage_recorded_at"] = "2026-09-05T05:05:00+00:00"

    with pytest.raises(
        linkage.LiveAdapterDryRunHumanApprovalNotRequiredLinkageError,
        match="LADHANR_HASH_MISMATCH",
    ):
        linkage.verify_live_adapter_dry_run_human_approval_not_required_linkage_packet(
            raw
        )
