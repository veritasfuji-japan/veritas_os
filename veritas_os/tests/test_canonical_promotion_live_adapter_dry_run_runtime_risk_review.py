"""Fail-closed tests for promotion-native pre-authorization risk review."""

from __future__ import annotations

import ast
import inspect
import json
from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

import veritas_os.policy.canonical_promotion_live_adapter_dry_run_runtime_risk_review as risk_module
from veritas_os.policy.bind_core.core import execute_bind_adjudication
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck import (
    AUTHORIZATION_REQUIREMENTS,
    INVOCATION_REQUIREMENTS,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_runtime_risk_review import (
    BLOCK_OUTCOME,
    BLOCK_STATE,
    BLOCK_STATUS,
    INDETERMINATE_OUTCOME,
    MAX_REVIEW_VALIDITY_SECONDS,
    NO_EFFECT_FIELDS,
    PASS_OUTCOME,
    PASS_STATE,
    PASS_STATUS,
    CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewError,
    CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewPacket,
    build_canonical_promotion_live_adapter_dry_run_runtime_risk_review_packet,
    verify_canonical_promotion_live_adapter_dry_run_runtime_risk_review_packet,
)
from veritas_os.policy.canonical_promotion_real_bind_authorization_contract import (
    BIND_TIME_RISK_OWNER,
    NEXT_AUTHORIZATION_REQUIREMENT,
    project_verified_promotion_authorization_source,
)
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_final_credential_scope_recheck import (
    RECHECKED_AT as SOURCE_AT,
    _packet as credential_scope_packet,
)
from veritas_os.tests.test_canonical_promotion_live_adapter_dry_run_final_endpoint_identity_recheck import (
    _packet as endpoint_identity_packet,
    source_packet as bind_context_packet,
)

REVIEWED_AT = SOURCE_AT + timedelta(seconds=1)
VALID_UNTIL = REVIEWED_AT + timedelta(seconds=30)
RECORDED_AT = REVIEWED_AT + timedelta(seconds=1)
pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def source_packet():
    """Build the recursively verified final credential-scope packet once."""

    endpoint = endpoint_identity_packet(source=bind_context_packet())
    return credential_scope_packet(source=endpoint)


@pytest.fixture(scope="module")
def projection(source_packet):
    """Project the exact source bindings used by risk decisions."""

    return project_verified_promotion_authorization_source(source_packet)


def _decision(projection, **changes):
    expected = projection.execution_intent["expected_state_fingerprint"]
    value = {
        "runtime_risk_review_decision_id": "risk-review-decision:one",
        "reviewer_id": "reviewer:risk:one",
        "reviewer_role": "runtime-risk-reviewer",
        "reviewer_attestation": "reviewed exact pre-authorization runtime evidence",
        "reviewed_at": REVIEWED_AT.isoformat(),
        "valid_until": VALID_UNTIL.isoformat(),
        "source_final_credential_scope_recheck_id": (
            projection.source_final_credential_scope_recheck_id
        ),
        "source_final_credential_scope_recheck_hash": (
            projection.source_final_credential_scope_recheck_hash
        ),
        "execution_intent_id": projection.execution_intent_id,
        "execution_intent_hash": projection.execution_intent_hash,
        "adapter_contract_id": projection.adapter_contract_id,
        "adapter_contract_hash": projection.adapter_contract_hash,
        "bind_context_hash": projection.bind_context_hash,
        "final_endpoint_identity_binding_digest": (
            projection.final_endpoint_identity_binding_digest
        ),
        "final_credential_scope_binding_digest": (
            projection.final_credential_scope_binding_digest
        ),
        "expected_state_fingerprint": expected,
        "observed_state_fingerprint": expected,
        "runtime_risk_signal": True,
        "runtime_risk_evidence_refs": ["risk-evidence:one"],
        "risk_reason": "runtime risk is acceptable for continued authorization review",
        "assessment_input_mode": (
            "caller_supplied_pre_authorization_runtime_risk_evidence"
        ),
        "acknowledged_exact_bind_context_only": True,
        "acknowledged_runtime_risk_review_is_not_authority": True,
        "acknowledged_no_bind_authorization": True,
        "acknowledged_no_bind_invocation": True,
        "acknowledged_no_request_dispatch": True,
        "acknowledged_no_credential_material_access": True,
        "acknowledged_missing_stale_or_mismatched_evidence_blocks": True,
        "acknowledged_bind_time_runtime_risk_recheck_still_required": True,
    }
    value.update(changes)
    return value


def _packet(source_packet, projection, **decision_changes):
    decision = _decision(projection, **decision_changes)
    reviewed = datetime.fromisoformat(decision["reviewed_at"])
    recorded = reviewed + timedelta(seconds=1)
    return build_canonical_promotion_live_adapter_dry_run_runtime_risk_review_packet(
        source_packet,
        decision,
        recorded,
    )


@pytest.fixture(scope="module")
def valid_packet(source_packet, projection):
    """Build one passing compact risk-review packet."""

    return _packet(source_packet, projection)


def _rehash(raw: dict) -> None:
    digest = risk_module._packet_hash(raw)
    raw["promotion_live_adapter_dry_run_runtime_risk_review_hash"] = digest
    raw["promotion_live_adapter_dry_run_runtime_risk_review_id"] = (
        f"pladrrr:v1:sha256:{digest}"
    )


def test_passing_review_round_trips_against_independent_source(
    source_packet,
    projection,
    valid_packet,
):
    verified = (
        verify_canonical_promotion_live_adapter_dry_run_runtime_risk_review_packet(
            json.loads(valid_packet.model_dump_json()),
            source_packet,
        )
    )

    assert verified == valid_packet
    assert verified.source_authorization_projection == projection
    assert verified.runtime_risk_review_result.outcome == PASS_OUTCOME
    assert verified.runtime_risk_review_result.runtime_risk_acceptable is True
    assert verified.runtime_risk_review_status == PASS_STATUS
    assert verified.runtime_risk_review_state == PASS_STATE
    assert verified.fail_closed is False


def test_review_consumes_only_runtime_risk_requirement(valid_packet):
    remaining = tuple(
        route.requirement for route in valid_packet.remaining_authorization_routes
    )
    invocation = tuple(
        route.requirement for route in valid_packet.remaining_invocation_routes
    )

    assert remaining == AUTHORIZATION_REQUIREMENTS[1:]
    assert invocation == INVOCATION_REQUIREMENTS
    assert valid_packet.next_authorization_requirement == (
        "idempotency_and_replay_review"
    )
    assert valid_packet.runtime_risk_requirement_proof.requirement == (
        NEXT_AUTHORIZATION_REQUIREMENT
    )
    assert valid_packet.runtime_risk_requirement_proof.satisfied_by_this_packet
    assert valid_packet.runtime_risk_requirement_satisfied
    assert valid_packet.ready_for_remaining_real_bind_authorization_requirements


def test_passing_review_preserves_bind_time_independent_recheck(valid_packet):
    assert valid_packet.bind_time_runtime_risk_recheck_required is True
    assert valid_packet.bind_time_runtime_risk_owner == BIND_TIME_RISK_OWNER
    assert valid_packet.runtime_risk_requirement_proof.bind_time_recheck_required
    assert "adapter.assess_runtime_risk" in inspect.getsource(execute_bind_adjudication)


def test_review_is_compact_but_requires_full_source_for_verification(valid_packet):
    assert (
        "source_final_credential_scope_recheck_packet"
        not in CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewPacket.model_fields
    )
    assert valid_packet.source_final_credential_scope_recheck_hash
    assert valid_packet.source_authorization_projection.execution_intent_id


def test_caller_evidence_is_not_misrepresented_as_authenticated(valid_packet):
    result = valid_packet.runtime_risk_review_result

    assert result.caller_supplied_evidence_only is True
    assert result.external_evidence_authenticity_claimed is False
    assert result.creates_execution_authority is False
    assert result.creates_bind_authorization is False
    assert result.invokes_bind is False
    assert result.dispatches_request is False


def test_negative_runtime_risk_signal_blocks_and_keeps_requirement(
    source_packet,
    projection,
):
    packet = _packet(
        source_packet,
        projection,
        runtime_risk_signal=False,
        risk_reason="adapter runtime risk is unacceptable",
    )

    assert packet.runtime_risk_review_result.outcome == BLOCK_OUTCOME
    assert packet.runtime_risk_review_result.reason_codes[0] == (
        "CPLADRRR_RUNTIME_RISK_UNACCEPTABLE"
    )
    assert packet.runtime_risk_review_status == BLOCK_STATUS
    assert packet.runtime_risk_review_state == BLOCK_STATE
    assert packet.fail_closed is True
    assert packet.runtime_risk_requirement_satisfied is False
    assert packet.next_authorization_requirement == NEXT_AUTHORIZATION_REQUIREMENT
    assert (
        tuple(route.requirement for route in packet.remaining_authorization_routes)
        == AUTHORIZATION_REQUIREMENTS
    )


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        (
            {"runtime_risk_signal": None},
            "CPLADRRR_RUNTIME_RISK_SIGNAL_MISSING",
        ),
        (
            {"observed_state_fingerprint": None},
            "CPLADRRR_OBSERVED_STATE_FINGERPRINT_MISSING",
        ),
    ],
)
def test_missing_runtime_evidence_is_indeterminate_fail_closed(
    source_packet,
    projection,
    changes,
    reason,
):
    packet = _packet(source_packet, projection, **changes)

    assert packet.runtime_risk_review_result.outcome == INDETERMINATE_OUTCOME
    assert reason in packet.runtime_risk_review_result.reason_codes
    assert packet.fail_closed is True
    assert packet.ready_for_remaining_real_bind_authorization_requirements is False


def test_observed_state_drift_blocks(source_packet, projection):
    packet = _packet(
        source_packet,
        projection,
        observed_state_fingerprint="state:drifted",
    )

    assert packet.runtime_risk_review_result.outcome == BLOCK_OUTCOME
    assert "CPLADRRR_STATE_DRIFT_DETECTED" in (
        packet.runtime_risk_review_result.reason_codes
    )
    assert packet.runtime_risk_review_result.state_fingerprint_matches is False
    assert packet.fail_closed is True


def test_expired_intent_blocks_even_with_positive_risk_signal(
    source_packet,
    projection,
):
    decision_at = datetime.fromisoformat(
        projection.execution_intent["decision_ts"].replace("Z", "+00:00")
    )
    reviewed_at = decision_at + timedelta(
        seconds=projection.execution_intent["ttl_seconds"] + 1
    )
    packet = _packet(
        source_packet,
        projection,
        reviewed_at=reviewed_at.isoformat(),
        valid_until=(reviewed_at + timedelta(seconds=10)).isoformat(),
    )

    assert packet.runtime_risk_review_result.outcome == BLOCK_OUTCOME
    assert "CPLADRRR_INTENT_NOT_FRESH_FOR_REVIEW_WINDOW" in (
        packet.runtime_risk_review_result.reason_codes
    )
    assert packet.fail_closed is True


def test_review_window_longer_than_five_minutes_is_rejected(
    source_packet,
    projection,
):
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewError,
        match="CPLADRRR_REVIEW_WINDOW_INVALID",
    ):
        _packet(
            source_packet,
            projection,
            valid_until=(
                REVIEWED_AT + timedelta(seconds=MAX_REVIEW_VALIDITY_SECONDS + 1)
            ).isoformat(),
        )


@pytest.mark.parametrize(
    "field",
    (
        "source_final_credential_scope_recheck_id",
        "source_final_credential_scope_recheck_hash",
        "execution_intent_id",
        "execution_intent_hash",
        "adapter_contract_id",
        "adapter_contract_hash",
        "bind_context_hash",
        "final_endpoint_identity_binding_digest",
        "final_credential_scope_binding_digest",
        "expected_state_fingerprint",
    ),
)
def test_any_exact_context_substitution_fails_closed(
    source_packet,
    projection,
    field,
):
    value = "0" * 64 if field.endswith(("hash", "digest")) else "substitute"
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewError,
        match="CPLADRRR_DECISION_BINDING_MISMATCH",
    ):
        _packet(source_packet, projection, **{field: value})


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"runtime_risk_signal": "true"}, "CPLADRRR_RUNTIME_RISK_SIGNAL_INVALID"),
        ({"runtime_risk_evidence_refs": []}, "CPLADRRR_EVIDENCE_REFS_INVALID"),
        (
            {"runtime_risk_evidence_refs": ["risk:one", "risk:one"]},
            "CPLADRRR_EVIDENCE_REFS_INVALID",
        ),
    ],
)
def test_open_or_ambiguous_decision_inputs_are_rejected(
    source_packet,
    projection,
    changes,
    code,
):
    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewError,
        match=code,
    ):
        _packet(source_packet, projection, **changes)


def test_tampered_full_source_fails_independent_verification(
    source_packet,
    valid_packet,
):
    raw_source = source_packet.model_dump(mode="json")
    raw_source["execution_intent_hash"] = "0" * 64

    with pytest.raises(
        CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewError,
        match="CPLADRRR_SOURCE_INVALID",
    ):
        verify_canonical_promotion_live_adapter_dry_run_runtime_risk_review_packet(
            valid_packet,
            raw_source,
        )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("runtime_risk_review_result", "outcome"), BLOCK_OUTCOME),
        (("runtime_risk_requirement_proof", "satisfied_by_this_packet"), False),
        (("remaining_authorization_routes", 0, "requirement"), "runtime_risk_review"),
        (("source_authorization_projection", "bind_context_hash"), "0" * 64),
        (("bind_time_runtime_risk_recheck_required",), False),
        (("execution_authorized",), True),
        (("network_used",), True),
    ],
)
def test_packet_tamper_fails_even_after_rehash(
    source_packet,
    valid_packet,
    path,
    value,
):
    raw = valid_packet.model_dump(mode="json")
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    _rehash(raw)

    with pytest.raises(CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewError):
        verify_canonical_promotion_live_adapter_dry_run_runtime_risk_review_packet(
            raw,
            source_packet,
        )


def test_packet_schema_is_closed_frozen_and_non_effecting(valid_packet):
    raw = valid_packet.model_dump(mode="json")
    raw["unexpected"] = True
    with pytest.raises(ValidationError):
        CanonicalPromotionLiveAdapterDryRunRuntimeRiskReviewPacket.model_validate(raw)
    with pytest.raises(ValidationError):
        valid_packet.fail_closed = True
    assert not any(getattr(valid_packet, field) for field in NO_EFFECT_FIELDS)
    assert valid_packet.ready_for_real_bind is False
    assert valid_packet.ready_for_network_dispatch is False


def test_module_has_no_adapter_or_io_effect_capabilities():
    tree = ast.parse(inspect.getsource(risk_module))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    )
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert not any(name.startswith("veritas_os.tests") for name in imported)
    assert not any(
        name.split(".")[0] in {"httpx", "requests", "socket", "subprocess", "urllib"}
        for name in imported
    )
    assert not called_names & {"open", "urlopen", "Popen"}
    assert not called_attributes & {
        "snapshot",
        "fingerprint_state",
        "assess_runtime_risk",
        "apply",
        "execute_bind_adjudication",
    }
