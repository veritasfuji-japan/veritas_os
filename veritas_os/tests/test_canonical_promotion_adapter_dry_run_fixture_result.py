"""Fail-closed tests for promotion-native no-effect fixture results."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

import pytest

from veritas_os.policy.adapter_dry_run_result import (
    RESULT_LIMITATIONS as LEGACY_RESULT_LIMITATIONS,
    build_adapter_dry_run_fixture_result_packet,
)
from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_execution_intent
from veritas_os.policy.canonical_promotion_adapter_dry_run_fixture_result import (
    RESULT_LIMITATIONS,
    VALUE_DOMAIN,
    CanonicalPromotionAdapterDryRunFixtureResultError,
    _digest,
    build_canonical_promotion_adapter_dry_run_fixture_result_packet,
    verify_canonical_promotion_adapter_dry_run_fixture_result_packet,
)
from veritas_os.tests.test_adapter_dry_run_fixture_result import (
    RESULTED_AT as LEGACY_RESULTED_AT,
    _fixtures as legacy_fixtures,
)
from veritas_os.tests.test_adapter_dry_run_plan import _packet as legacy_plan
from veritas_os.tests.test_canonical_promotion_adapter_dry_run_plan import (
    PLANNED_AT,
    _packet as promotion_plan,
)

RESULTED_AT = PLANNED_AT + timedelta(seconds=1)


def _fixtures(plan=None):
    plan = plan or promotion_plan()
    return [
        {
            "step_result_id": (
                f"dry-run-fixture-result:v1:{step.ordinal}:"
                f"{step.planned_adapter_method.replace('_', '-')}"
            ),
            "planned_step_id": step.step_id,
            "ordinal": step.ordinal,
            "planned_adapter_method": step.planned_adapter_method,
            "result_mode": "fixture_no_effect",
            "result_source_kind": "unit_test_fixture",
            "live_observed": False,
            "adapter_instance_created": False,
            "adapter_method_called": False,
            "network_used": False,
            "filesystem_used": False,
            "external_effect_used": False,
            "trustlog_written": False,
            "bind_receipt_created": False,
            "fixture_input_ref": f"fixture:{step.planned_adapter_method}",
            "fixture_value_summary": {
                "status": "FIXTURE_RESULT_AVAILABLE",
                "semantic": "no_effect_fixture",
                "live_system_claim": False,
            },
            "matched_expected_output_ref": step.expected_output_ref,
            "refusal_if_missing_later": step.refusal_if_missing_later,
            "result_scope_limitations": RESULT_LIMITATIONS,
        }
        for step in plan.planned_steps
    ]


def _packet():
    plan = promotion_plan()
    return build_canonical_promotion_adapter_dry_run_fixture_result_packet(
        plan, _fixtures(plan), RESULTED_AT
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


def test_full_chain_preserves_authoritative_intent_descriptor_and_no_effects() -> None:
    source = promotion_plan()
    packet = verify_canonical_promotion_adapter_dry_run_fixture_result_packet(
        _packet()
    )
    intent = ExecutionIntent(**packet.execution_intent)

    assert packet.execution_intent == source.execution_intent == intent.to_dict()
    assert packet.execution_intent_id == source.execution_intent_id
    assert packet.execution_intent_id == intent.execution_intent_id
    assert packet.execution_intent_hash == source.execution_intent_hash
    assert packet.execution_intent_hash == hash_execution_intent(intent)
    assert packet.adapter_contract_descriptor == source.adapter_contract_descriptor
    assert packet.adapter_contract_id == source.adapter_contract_id
    assert packet.adapter_contract_hash == source.adapter_contract_hash
    assert packet.approval_context["required_human_approval"] is True
    assert len(packet.fixture_step_results) == 7
    raw = packet.model_dump(mode="json")
    forbidden = {
        "source_formation_hash",
        "source_eligibility_hash",
        "source_handoff_hash",
        "trusted_validation_context_hash",
        "validation_result_hash",
        "mapping_value_digest",
        "replay_summary",
        "human_approval_receipt_ref",
        "human_approval_receipt_hash",
        "apply",
        "verify_postconditions",
        "revert",
    }
    assert set(raw).isdisjoint(forbidden)
    for result in packet.fixture_step_results:
        assert result.live_observed is False
        assert result.adapter_instance_created is False
        assert result.adapter_method_called is False
        assert result.network_used is False
        assert result.filesystem_used is False
        assert result.external_effect_used is False
        assert result.fixture_value_digest == _digest(
            VALUE_DOMAIN, result.fixture_value_summary
        )


def test_legacy_and_promotion_fixture_steps_have_equal_semantics() -> None:
    legacy_source = legacy_plan()
    legacy = build_adapter_dry_run_fixture_result_packet(
        legacy_source, legacy_fixtures(legacy_source), LEGACY_RESULTED_AT
    )
    promotion = _packet()
    fields = (
        "ordinal",
        "planned_adapter_method",
        "result_mode",
        "live_observed",
        "adapter_instance_created",
        "adapter_method_called",
        "network_used",
        "filesystem_used",
        "external_effect_used",
        "matched_expected_output_ref",
        "refusal_if_missing_later",
    )
    assert [
        tuple(getattr(item, field) for field in fields)
        for item in promotion.fixture_step_results
    ] == [
        tuple(getattr(item, field) for field in fields)
        for item in legacy.fixture_step_results
    ]
    assert all(
        item.result_scope_limitations == RESULT_LIMITATIONS
        for item in promotion.fixture_step_results
    )
    assert all(
        item.result_scope_limitations == LEGACY_RESULT_LIMITATIONS
        for item in legacy.fixture_step_results
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("source_adapter_dry_run_plan_id", "padp:v1:sha256:" + "0" * 64),
        ("source_adapter_dry_run_plan_hash", "0" * 64),
        ("source_adapter_contract_selection_hash", "0" * 64),
        ("source_bind_preflight_adjudication_hash", "0" * 64),
        ("source_pre_bind_validation_hash", "0" * 64),
        ("source_readiness_hash", "0" * 64),
        ("source_promotion_hash", "0" * 64),
        ("execution_intent.actor_identity", "substitute"),
        ("execution_intent_id", "ei:v1:sha256:" + "0" * 64),
        ("execution_intent_hash", "0" * 64),
        ("adapter_contract_descriptor.target_system", "substitute"),
        ("adapter_contract_id", "adapter-contract:v1:sha256:" + "0" * 64),
        ("adapter_contract_hash", "0" * 64),
        ("planned_steps.0.ordinal", 2),
        ("fixture_step_results.0.ordinal", 2),
        ("fixture_step_results.0.planned_adapter_method", "snapshot"),
        ("fixture_step_results.0.fixture_value_digest", "0" * 64),
        ("fixture_step_results.0.live_observed", True),
        ("fixture_step_results.0.adapter_method_called", True),
        ("fixture_step_results.0.network_used", True),
        ("fixture_step_results.0.filesystem_used", True),
        ("fixture_step_results.0.external_effect_used", True),
        ("fixture_step_results.0.result_scope_limitations", []),
        ("approval_context.required_human_approval", False),
        ("policy_lineage.version", "substitute"),
        ("resulted_at", "2026-08-27T00:00:00+00:00"),
        ("local_result_checks.no_adapter_invocation", False),
        ("local_result_checks_digest", "0" * 64),
        ("scope_limitations", []),
        ("adapter_dry_run_fixture_result_hash", "0" * 64),
        ("adapter_dry_run_fixture_result_id", "padr:v1:sha256:" + "0" * 64),
    ],
)
def test_packet_tampering_fails_closed(path: str, value: object) -> None:
    raw = deepcopy(_packet().model_dump(mode="json"))
    _set_path(raw, path, value)
    with pytest.raises(CanonicalPromotionAdapterDryRunFixtureResultError):
        verify_canonical_promotion_adapter_dry_run_fixture_result_packet(raw)


def test_result_count_order_effect_insertion_and_shortcuts_fail_closed() -> None:
    for mutation in ("count", "order", "apply", "shortcut"):
        raw = deepcopy(_packet().model_dump(mode="json"))
        if mutation == "count":
            raw["fixture_step_results"].pop()
        elif mutation == "order":
            raw["fixture_step_results"][0:2] = reversed(
                raw["fixture_step_results"][0:2]
            )
        elif mutation == "apply":
            result = deepcopy(raw["fixture_step_results"][0])
            result["planned_adapter_method"] = "apply"
            raw["fixture_step_results"].append(result)
        else:
            raw["human_approval_proven"] = True
        with pytest.raises(CanonicalPromotionAdapterDryRunFixtureResultError):
            verify_canonical_promotion_adapter_dry_run_fixture_result_packet(raw)
