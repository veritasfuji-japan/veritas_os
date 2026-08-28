"""Fail-closed tests for promotion-native adapter contract selection."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

import pytest

from veritas_os.policy.bind_adapter_contract_selection import (
    ADAPTER_METHODS,
    DESCRIPTOR_SCOPE_LIMITATIONS,
    EFFECT_PROFILE,
    PROHIBITED_DURING_SELECTION,
    verify_bind_adapter_contract_descriptor,
)
from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_bind_adapter_contract_selection import (
    FUTURE_BIND_DRY_RUN_REQUIREMENTS,
    LOCAL_SELECTION_CHECKS,
    SCOPE_LIMITATIONS,
    CanonicalPromotionBindAdapterContractSelectionError,
    build_canonical_promotion_bind_adapter_contract_selection_packet,
    verify_canonical_promotion_bind_adapter_contract_selection_packet,
)
from veritas_os.tests.test_canonical_promotion_bind_preflight_adjudication import (
    ADJUDICATED_AT,
    _packet as preflight_packet,
)
from veritas_os.tests.test_canonical_promotion_execution_intent_readiness import (
    _promotion,
)

SELECTED_AT = ADJUDICATED_AT + timedelta(seconds=1)


def _descriptor() -> dict:
    source = preflight_packet()
    return {
        "adapter_contract_version": "bind-adapter-contract/v1",
        "adapter_kind": "reference",
        "adapter_name": "promotion-native-inert-reference",
        "target_system": source.execution_intent["target_system"],
        "target_resource_scope": source.execution_intent["target_resource"],
        "supported_methods": list(ADAPTER_METHODS),
        "required_methods": list(ADAPTER_METHODS),
        "prohibited_during_selection": list(PROHIBITED_DURING_SELECTION),
        "effect_profile": EFFECT_PROFILE,
        "declared_by": "local-test",
        "declared_at": ADJUDICATED_AT.isoformat(),
        "descriptor_scope_limitations": list(DESCRIPTOR_SCOPE_LIMITATIONS),
    }


def _packet():
    return build_canonical_promotion_bind_adapter_contract_selection_packet(
        preflight_packet(), _descriptor(), SELECTED_AT
    )


def _set_path(raw: dict, path: str, value: object) -> None:
    target = raw
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value


def test_full_chain_preserves_exact_intent_and_no_effect_approval_order() -> None:
    promotion = _promotion(required_human_approval=True)
    source = preflight_packet()
    packet = verify_canonical_promotion_bind_adapter_contract_selection_packet(
        build_canonical_promotion_bind_adapter_contract_selection_packet(
            source, _descriptor(), SELECTED_AT
        )
    )
    intent = ExecutionIntent(**packet.execution_intent)

    assert packet.execution_intent == source.execution_intent
    assert packet.execution_intent == promotion.exact_execution_intent
    assert intent.to_dict() == promotion.exact_execution_intent
    assert packet.execution_intent_id == source.execution_intent_id
    assert packet.execution_intent_id == promotion.execution_intent_id
    assert packet.execution_intent_hash == source.execution_intent_hash
    assert packet.execution_intent_hash == promotion.execution_intent_hash
    assert packet.execution_intent_hash == hash_execution_intent(intent)
    assert packet.adapter_contract_descriptor["target_system"] == intent.target_system
    assert (
        packet.adapter_contract_descriptor["target_resource_scope"]
        == intent.target_resource
    )
    assert packet.approval_context == {
        "required_human_approval": True,
        "policy_context_refs": ["policy-context:one"],
    }
    assert packet.policy_lineage == intent.policy_lineage
    assert packet.local_selection_checks == LOCAL_SELECTION_CHECKS
    assert packet.future_bind_dry_run_requirements == FUTURE_BIND_DRY_RUN_REQUIREMENTS
    assert packet.scope_limitations == SCOPE_LIMITATIONS
    raw = packet.model_dump(mode="json")
    assert "human_approval_proven" not in raw
    assert "human_approval_receipt_ref" not in raw
    assert "adapter_instance" not in raw
    assert "bind_receipt" not in raw


def test_legacy_and_promotion_paths_share_exact_descriptor_address() -> None:
    intent = ExecutionIntent(**preflight_packet().execution_intent)
    legacy_verified = verify_bind_adapter_contract_descriptor(_descriptor(), intent)
    promotion_verified = _packet().adapter_contract_descriptor

    assert promotion_verified["adapter_contract_hash"] == (
        legacy_verified.adapter_contract_hash
    )
    assert promotion_verified["adapter_contract_id"] == (
        legacy_verified.adapter_contract_id
    )


def test_builder_rejects_malformed_source_and_timeline() -> None:
    malformed = preflight_packet().model_dump(mode="json")
    malformed["bind_preflight_adjudication_hash"] = "0" * 64
    with pytest.raises(
        CanonicalPromotionBindAdapterContractSelectionError,
        match="PBAC_BIND_PREFLIGHT_INVALID",
    ):
        build_canonical_promotion_bind_adapter_contract_selection_packet(
            malformed, _descriptor(), SELECTED_AT
        )
    with pytest.raises(
        CanonicalPromotionBindAdapterContractSelectionError,
        match="PBAC_SELECTED_AT_INVALID",
    ):
        build_canonical_promotion_bind_adapter_contract_selection_packet(
            preflight_packet(), _descriptor(), SELECTED_AT.replace(tzinfo=None)
        )
    with pytest.raises(
        CanonicalPromotionBindAdapterContractSelectionError,
        match="PBAC_SELECTED_BEFORE_BIND_PREFLIGHT",
    ):
        build_canonical_promotion_bind_adapter_contract_selection_packet(
            preflight_packet(), _descriptor(), ADJUDICATED_AT - timedelta(seconds=1)
        )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("source_bind_preflight_adjudication_id", "pbpa:v1:sha256:" + "0" * 64),
        ("source_bind_preflight_adjudication_hash", "0" * 64),
        (
            "source_bind_preflight_adjudication_packet.bind_preflight_adjudication_hash",
            "0" * 64,
        ),
        ("source_pre_bind_validation_id", "ppbv:v1:sha256:" + "0" * 64),
        ("source_pre_bind_validation_hash", "0" * 64),
        ("source_readiness_id", "peir:v1:sha256:" + "0" * 64),
        ("source_readiness_hash", "0" * 64),
        ("source_promotion_id", "cvdp:v1:sha256:" + "0" * 64),
        ("source_promotion_hash", "0" * 64),
        ("source_decision_identity.decision_id", "decision:substituted"),
        ("candidate_identity.candidate_id", "candidate:substituted"),
        ("selected_action_lineage.selected_action_evidence_hash", "0" * 64),
        ("policy_snapshot_lineage.policy_snapshot_evidence_hash", "0" * 64),
        ("execution_intent", {}),
        ("execution_intent_id", "ei:v1:sha256:" + "0" * 64),
        ("execution_intent_hash", "0" * 64),
        ("execution_intent.actor_identity", "actor:substituted"),
        ("execution_intent.target_system", "system:substituted"),
        ("execution_intent.target_resource", "resource:substituted"),
        ("execution_intent.intended_action", "action:substituted"),
        ("approval_context.required_human_approval", False),
        ("approval_context.policy_context_refs", []),
        ("policy_lineage.version", "policy:substituted"),
        ("policy_lineage.signer_id", "signer:substituted"),
        ("adapter_contract_descriptor.target_system", "wrong-system"),
        ("adapter_contract_descriptor.target_resource_scope", "wrong-resource"),
        ("adapter_contract_descriptor.adapter_contract_hash", "0" * 64),
        (
            "adapter_contract_descriptor.adapter_contract_id",
            "adapter-contract:v1:sha256:" + "0" * 64,
        ),
        ("adapter_contract_descriptor.adapter_contract_version", "wrong-version"),
        ("adapter_contract_descriptor.supported_methods", ["apply"]),
        ("adapter_contract_descriptor.required_methods", ["apply"]),
        ("adapter_contract_descriptor.prohibited_during_selection", ["apply"]),
        ("adapter_contract_descriptor.effect_profile.network_allowed", True),
        ("adapter_contract_descriptor.descriptor_scope_limitations", []),
        ("selected_at", "malformed"),
        ("selected_at", "2026-08-27T00:00:00+00:00"),
        ("local_selection_checks.no_adapter_invocation", False),
        ("local_selection_checks_digest", "0" * 64),
        ("future_bind_dry_run_requirements.adapter_instance_required", False),
        ("future_bind_dry_run_requirements_digest", "0" * 64),
        ("scope_limitations", []),
        ("adapter_contract_selection_hash", "0" * 64),
        ("adapter_contract_selection_id", "pbac:v1:sha256:" + "0" * 64),
    ],
)
def test_packet_substitutions_fail_closed(path: str, value: object) -> None:
    raw = deepcopy(_packet().model_dump(mode="json"))
    _set_path(raw, path, value)

    with pytest.raises(CanonicalPromotionBindAdapterContractSelectionError):
        verify_canonical_promotion_bind_adapter_contract_selection_packet(raw)


def test_unknown_preverification_shortcut_fails_closed() -> None:
    raw = _packet().model_dump(mode="json")
    raw["descriptor_preverified"] = True
    with pytest.raises(CanonicalPromotionBindAdapterContractSelectionError):
        verify_canonical_promotion_bind_adapter_contract_selection_packet(raw)
