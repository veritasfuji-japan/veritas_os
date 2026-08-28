"""Fail-closed tests for promotion-native no-effect adapter dry-run plans."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

import pytest

from veritas_os.policy.adapter_dry_run_plan import build_adapter_dry_run_plan_packet
from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_adapter_dry_run_plan import (
    FUTURE_DRY_RUN_EXECUTION_REQUIREMENTS,
    LOCAL_PLAN_CHECKS,
    CanonicalPromotionAdapterDryRunPlanError,
    build_canonical_promotion_adapter_dry_run_plan_packet,
    verify_canonical_promotion_adapter_dry_run_plan_packet,
)
from veritas_os.tests.test_adapter_dry_run_plan import (
    PLANNED_AT as LEGACY_PLANNED_AT,
)
from veritas_os.tests.test_bind_adapter_contract_selection import (
    _packet as legacy_selection_packet,
)
from veritas_os.tests.test_canonical_promotion_bind_adapter_contract_selection import (
    SELECTED_AT,
    _packet as selection_packet,
)
from veritas_os.tests.test_canonical_promotion_execution_intent_readiness import (
    _promotion,
)

PLANNED_AT = SELECTED_AT + timedelta(seconds=1)


def _packet():
    return build_canonical_promotion_adapter_dry_run_plan_packet(
        selection_packet(), PLANNED_AT
    )


def _set_path(raw: dict, path: str, value: object) -> None:
    target = raw
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    if isinstance(target, list):
        target[int(parts[-1])] = value
    else:
        target[parts[-1]] = value


def test_full_chain_preserves_exact_intent_descriptor_and_approval_order() -> None:
    promotion = _promotion(required_human_approval=True)
    selection = selection_packet()
    packet = verify_canonical_promotion_adapter_dry_run_plan_packet(_packet())
    intent = ExecutionIntent(**packet.execution_intent)

    assert packet.execution_intent == selection.execution_intent
    assert packet.execution_intent == promotion.exact_execution_intent
    assert intent.to_dict() == packet.execution_intent
    assert packet.execution_intent_id == selection.execution_intent_id
    assert packet.execution_intent_id == promotion.execution_intent_id
    assert packet.execution_intent_hash == selection.execution_intent_hash
    assert packet.execution_intent_hash == promotion.execution_intent_hash
    assert packet.execution_intent_hash == hash_execution_intent(intent)
    assert packet.adapter_contract_id == selection.adapter_contract_id
    assert packet.adapter_contract_hash == selection.adapter_contract_hash
    assert packet.approval_context == selection.approval_context
    assert packet.approval_context["required_human_approval"] is True
    assert packet.policy_lineage == selection.policy_lineage
    assert packet.local_plan_checks == LOCAL_PLAN_CHECKS
    assert (
        packet.future_dry_run_execution_requirements
        == FUTURE_DRY_RUN_EXECUTION_REQUIREMENTS
    )
    raw = packet.model_dump(mode="json")
    assert "human_approval_proven" not in raw
    assert "human_approval_receipt_ref" not in raw
    assert "human_approval_receipt_hash" not in raw
    assert "adapter_instance" not in raw
    assert "source_formation_hash" not in raw
    assert "source_handoff_hash" not in raw


def test_legacy_and_promotion_plans_share_exact_step_semantics() -> None:
    legacy = build_adapter_dry_run_plan_packet(
        legacy_selection_packet(), LEGACY_PLANNED_AT
    )
    promotion = _packet()
    fields = (
        "ordinal",
        "phase",
        "planned_adapter_method",
        "execution_mode",
        "expected_output_ref",
        "refusal_if_missing_later",
        "effect_policy",
        "step_scope_limitations",
    )

    assert [
        tuple(getattr(step, field) for field in fields)
        for step in promotion.planned_steps
    ] == [
        tuple(getattr(step, field) for field in fields) for step in legacy.planned_steps
    ]
    methods = [step.planned_adapter_method for step in promotion.planned_steps]
    assert methods == [
        "describe_target",
        "build_idempotency_key",
        "snapshot",
        "fingerprint_state",
        "validate_authority",
        "validate_constraints",
        "assess_runtime_risk",
    ]
    assert set(methods).isdisjoint({"apply", "verify_postconditions", "revert"})


def test_builder_rejects_malformed_source_and_timeline() -> None:
    malformed = selection_packet().model_dump(mode="json")
    malformed["adapter_contract_selection_hash"] = "0" * 64
    with pytest.raises(
        CanonicalPromotionAdapterDryRunPlanError,
        match="PADP_ADAPTER_SELECTION_INVALID",
    ):
        build_canonical_promotion_adapter_dry_run_plan_packet(malformed, PLANNED_AT)
    with pytest.raises(
        CanonicalPromotionAdapterDryRunPlanError,
        match="PADP_PLANNED_AT_INVALID",
    ):
        build_canonical_promotion_adapter_dry_run_plan_packet(
            selection_packet(), PLANNED_AT.replace(tzinfo=None)
        )
    with pytest.raises(
        CanonicalPromotionAdapterDryRunPlanError,
        match="PADP_PLANNED_BEFORE_SELECTION",
    ):
        build_canonical_promotion_adapter_dry_run_plan_packet(
            selection_packet(), SELECTED_AT - timedelta(seconds=1)
        )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("source_adapter_contract_selection_id", "pbac:v1:sha256:" + "0" * 64),
        ("source_adapter_contract_selection_hash", "0" * 64),
        (
            "source_adapter_contract_selection_packet.adapter_contract_selection_hash",
            "0" * 64,
        ),
        ("source_bind_preflight_adjudication_id", "pbpa:v1:sha256:" + "0" * 64),
        ("source_bind_preflight_adjudication_hash", "0" * 64),
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
        ("execution_intent.actor_identity", "actor:substituted"),
        ("execution_intent_id", "ei:v1:sha256:" + "0" * 64),
        ("execution_intent_hash", "0" * 64),
        ("adapter_contract_descriptor.target_system", "wrong-system"),
        ("adapter_contract_descriptor.adapter_contract_hash", "0" * 64),
        ("adapter_contract_id", "adapter-contract:v1:sha256:" + "0" * 64),
        ("adapter_contract_hash", "0" * 64),
        ("approval_context.required_human_approval", False),
        ("policy_lineage.version", "policy:substituted"),
        ("planned_steps.0.ordinal", 2),
        ("planned_steps.0.planned_adapter_method", "snapshot"),
        ("planned_steps.0.effect_policy.network_allowed", True),
        ("planned_steps.0.refusal_if_missing_later", "SUBSTITUTED"),
        ("planned_steps.0.step_scope_limitations", []),
        ("planned_steps", []),
        ("planned_at", "malformed"),
        ("planned_at", "2026-08-27T00:00:00+00:00"),
        ("local_plan_checks.no_adapter_invocation", False),
        ("local_plan_checks_digest", "0" * 64),
        ("future_dry_run_execution_requirements.apply_still_forbidden", False),
        ("future_dry_run_execution_requirements_digest", "0" * 64),
        ("scope_limitations", []),
        ("adapter_dry_run_plan_hash", "0" * 64),
        ("adapter_dry_run_plan_id", "padp:v1:sha256:" + "0" * 64),
    ],
)
def test_packet_substitutions_fail_closed(path: str, value: object) -> None:
    raw = deepcopy(_packet().model_dump(mode="json"))
    _set_path(raw, path, value)

    with pytest.raises(CanonicalPromotionAdapterDryRunPlanError):
        verify_canonical_promotion_adapter_dry_run_plan_packet(raw)


def test_apply_step_and_unknown_proof_shortcuts_fail_closed() -> None:
    raw = _packet().model_dump(mode="json")
    apply_step = deepcopy(raw["planned_steps"][0])
    apply_step["planned_adapter_method"] = "apply"
    raw["planned_steps"].append(apply_step)
    with pytest.raises(CanonicalPromotionAdapterDryRunPlanError):
        verify_canonical_promotion_adapter_dry_run_plan_packet(raw)

    raw = _packet().model_dump(mode="json")
    raw["planned_verified"] = True
    with pytest.raises(CanonicalPromotionAdapterDryRunPlanError):
        verify_canonical_promotion_adapter_dry_run_plan_packet(raw)
