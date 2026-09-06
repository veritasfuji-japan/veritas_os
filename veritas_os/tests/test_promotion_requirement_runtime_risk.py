"""Trusted risk evidence and full requirement chain remain mandatory."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator
import pytest

from veritas_os.policy import promotion_requirement_runtime_risk as module
from veritas_os.policy.canonical_verified_decision_promotion import (
    build_canonical_verified_decision_promotion_packet,
)
from veritas_os.tests.helpers.native_approval_source import (
    build_native_authority_source,
)
from veritas_os.tests.test_promotion_requirement_final_rechecks import _complete
from veritas_os.tests.test_promotion_human_approval_requirement_satisfaction import (
    native as native_fixture,
    _contract,
    authority,
    sources,
)

pytestmark = pytest.mark.slow
native = native_fixture


def _decision(final, now, **changes):
    expected = final.execution_intent.get("expected_state_fingerprint")
    value = {
        "review_id": "risk:test:1",
        "reviewer_id": "reviewer:test",
        "risk_reason": "Explicit synthetic pre-authorization risk input.",
        "reviewed_at": (now + timedelta(seconds=1)).isoformat(),
        "valid_until": (now + timedelta(seconds=30)).isoformat(),
        "source_final_recheck_id": final.packet_id,
        "source_final_recheck_hash": final.packet_hash,
        "bind_context_hash": final.bind_context_hash,
        "action_contract_digest": final.exact_bind_context.action_contract_digest,
        "expected_state_fingerprint": expected,
        "observed_state_fingerprint": expected,
        "runtime_risk_signal": True,
        "runtime_risk_evidence_refs": ["synthetic:risk:1"],
        "acknowledged_caller_evidence_only": True,
        "acknowledged_no_authorization": True,
        "acknowledged_bind_time_risk_recheck_required": True,
    }
    return {**value, **changes}


def _risk_chain(source, contract, now):
    _, _, final, anchors = _complete(source, contract, now)
    anchors = {**anchors, "expected_rechecked_at": now}
    decision = _decision(final, now)
    recorded = now + timedelta(seconds=2)
    packet = module.build_promotion_requirement_runtime_risk_packet(
        final, decision, recorded, **anchors
    )
    verification = {
        **anchors,
        "expected_risk_decision": decision,
        "expected_recorded_at": recorded,
        "verification_now": now + timedelta(seconds=3),
    }
    return final, packet, verification


@pytest.fixture(scope="module")
def chain(native):
    source, contract, _, now = native
    return _risk_chain(source, contract, now)


def test_pass_preserves_compact_source_binding_and_schema(chain):
    final, packet, inputs = chain
    verified = module.require_promotion_requirement_runtime_risk_pass(
        packet, final, **inputs
    )
    assert verified == packet and verified is not packet
    assert "source_packet" not in verified.model_dump(mode="json")
    assert verified.source_final_recheck_hash == final.packet_hash
    assert (
        verified.future_authorization_requirements
        == final.future_authorization_requirements[1:]
    )
    assert (
        verified.future_invocation_requirements == final.future_invocation_requirements
    )
    assert verified.bind_time_runtime_risk_recheck_required
    for name in module.ABSENT_FIELDS:
        assert getattr(verified, name) is False
    assert not verified.risk_result.external_evidence_authenticity_claimed
    schema = (
        Path(__file__).resolve().parents[2]
        / "schemas/promotion-requirement-runtime-risk-v1.schema.json"
    )
    Draft202012Validator(json.loads(schema.read_text())).validate(
        verified.model_dump(mode="json")
    )


@pytest.mark.parametrize(
    "changes,outcome",
    [
        ({"runtime_risk_signal": False}, "BLOCKED_BY_RUNTIME_RISK"),
        ({"runtime_risk_signal": None}, "INDETERMINATE_FAIL_CLOSED"),
        ({"observed_state_fingerprint": None}, "INDETERMINATE_FAIL_CLOSED"),
        ({"observed_state_fingerprint": "changed-state"}, "BLOCKED_BY_RUNTIME_RISK"),
    ],
)
def test_risk_block_and_missing_evidence_cannot_enter_downstream(
    chain, changes, outcome
):
    final, _, inputs = chain
    decision = {**inputs["expected_risk_decision"], **changes}
    anchors = {
        k: v
        for k, v in inputs.items()
        if k
        not in {"expected_risk_decision", "expected_recorded_at", "verification_now"}
    }
    packet = module.build_promotion_requirement_runtime_risk_packet(
        final, decision, inputs["expected_recorded_at"], **anchors
    )
    current = {**inputs, "expected_risk_decision": decision}
    verified = module.verify_promotion_requirement_runtime_risk_packet(
        packet, final, **current
    )
    assert verified.fail_closed and verified.risk_result.outcome == outcome
    assert (
        verified.future_authorization_requirements
        == final.future_authorization_requirements
    )
    with pytest.raises(ValueError, match="PRRR_RISK_NOT_ACCEPTABLE"):
        module.require_promotion_requirement_runtime_risk_pass(packet, final, **current)


def test_rehashed_positive_decision_cannot_replace_external_negative_decision(chain):
    final, passing, inputs = chain
    trusted_negative = {
        **inputs["expected_risk_decision"],
        "runtime_risk_signal": False,
    }
    with pytest.raises(ValueError, match="PRRR_RECONSTRUCTION_MISMATCH"):
        module.require_promotion_requirement_runtime_risk_pass(
            passing, final, **{**inputs, "expected_risk_decision": trusted_negative}
        )


@pytest.mark.parametrize(
    "rules",
    [
        {"required": False, "minimum_approvals": 0},
        {"required": True, "minimum_approvals": 2},
        {"required": True, "minimum_approvals": 1, "approver_role": "attacker"},
    ],
)
def test_fully_rebuilt_same_id_version_policy_substitution_is_rejected(native, rules):
    source, trusted, _, now = native
    attacker = replace(trusted, human_approval_rules=rules)
    assert (attacker.id, attacker.version) == (trusted.id, trusted.version)
    final, packet, inputs = _risk_chain(source, attacker, now)
    with pytest.raises(ValueError):
        module.verify_promotion_requirement_runtime_risk_packet(
            packet, final, **{**inputs, "expected_contract": trusted}
        )


def test_fully_rebuilt_source_substitution_is_rejected(native):
    source, contract, _, now = native
    bundle = source.authority_evidence_reference_bundle.model_dump(mode="json")
    bundle["bundle_declared_by"] = "attacker"
    other = authority(
        source.source_bind_pre_dispatch_review_packet, bundle, sources.RECORDED_AT
    )
    final, packet, inputs = _risk_chain(other, contract, now)
    with pytest.raises(ValueError):
        module.verify_promotion_requirement_runtime_risk_packet(
            packet, final, **{**inputs, "expected_source": source}
        )


@pytest.mark.parametrize(
    "field",
    [
        "bind_context_hash",
        "action_contract_digest",
        "source_final_recheck_hash",
        "required_human_approval",
        "fail_closed",
        "future_authorization_requirements",
        "risk_result",
    ],
)
def test_rehashed_packet_tampering_is_rejected(chain, field):
    final, packet, inputs = chain
    raw = packet.model_dump(mode="json")
    if field == "risk_result":
        raw[field]["reason_codes"] = ["attacker"]
    elif isinstance(raw[field], bool):
        raw[field] = not raw[field]
    elif isinstance(raw[field], list):
        raw[field] = []
    else:
        raw[field] = "0" * 64
    with pytest.raises(ValueError):
        module.verify_promotion_requirement_runtime_risk_packet(
            module._seal(raw), final, **inputs
        )


@pytest.mark.parametrize(
    "field",
    [
        "source_final_recheck_id",
        "source_final_recheck_hash",
        "bind_context_hash",
        "action_contract_digest",
        "expected_state_fingerprint",
    ],
)
def test_review_must_bind_exact_verified_source(chain, field):
    final, packet, inputs = chain
    decision = {**inputs["expected_risk_decision"], field: "wrong"}
    with pytest.raises(ValueError, match="PRRR_DECISION_BINDING_MISMATCH"):
        module.verify_promotion_requirement_runtime_risk_packet(
            packet, final, **{**inputs, "expected_risk_decision": decision}
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("runtime_risk_signal", 1),
        ("runtime_risk_signal", "true"),
        ("runtime_risk_evidence_refs", []),
        ("runtime_risk_evidence_refs", [" "]),
        ("runtime_risk_evidence_refs", ["duplicate", "duplicate"]),
        ("acknowledged_no_authorization", False),
    ],
)
def test_ambiguous_or_missing_review_inputs_fail(chain, field, value):
    final, packet, inputs = chain
    with pytest.raises(ValueError):
        module.verify_promotion_requirement_runtime_risk_packet(
            packet,
            final,
            **{
                **inputs,
                "expected_risk_decision": {
                    **inputs["expected_risk_decision"],
                    field: value,
                },
            },
        )


@pytest.mark.parametrize("which", ["before_record", "expiry", "after_expiry", "naive"])
def test_verification_clock_rechecks_validity_without_rehash(chain, which):
    final, packet, inputs = chain
    expiry = datetime.fromisoformat(packet.risk_decision.valid_until)
    now = {
        "before_record": inputs["expected_recorded_at"] - timedelta(seconds=1),
        "expiry": expiry,
        "after_expiry": expiry + timedelta(seconds=1),
        "naive": inputs["verification_now"].replace(tzinfo=None),
    }[which]
    with pytest.raises(ValueError):
        module.verify_promotion_requirement_runtime_risk_packet(
            packet, final, **{**inputs, "verification_now": now}
        )


@pytest.mark.parametrize(
    "missing",
    [
        "expected_source",
        "expected_contract",
        "current_endpoint",
        "current_credential_reference",
        "required_credential_scope",
        "expected_verified_at",
        "expected_rechecked_at",
        "expected_risk_decision",
        "expected_recorded_at",
        "verification_now",
    ],
)
def test_all_independent_verifier_inputs_are_mandatory(chain, missing):
    final, packet, original = chain
    inputs = dict(original)
    del inputs[missing]
    with pytest.raises(TypeError):
        module.verify_promotion_requirement_runtime_risk_packet(packet, final, **inputs)


@pytest.mark.parametrize(
    "field",
    ["current_endpoint", "current_credential_reference", "required_credential_scope"],
)
def test_current_metadata_is_rechecked_through_risk_boundary(chain, field):
    final, packet, inputs = chain
    value = deepcopy(inputs[field])
    if field == "current_endpoint":
        value["endpoint_host"] = "changed.invalid"
    elif field == "current_credential_reference":
        value["credential_scope"] = "changed"
    else:
        value = "*"
    with pytest.raises(ValueError):
        module.verify_promotion_requirement_runtime_risk_packet(
            packet, final, **{**inputs, field: value}
        )


@pytest.fixture(scope="module", params=[False, True])
def api_risk_source(request, tmp_path_factory):
    output = tmp_path_factory.mktemp("risk-api") / "capture.json"
    command = [
        sys.executable,
        "-m",
        "veritas_os.tests.helpers.live_decision_capture",
        str(output),
    ]
    if request.param:
        command.append("--human-required")
    subprocess.run(
        command,
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        timeout=180,
        capture_output=True,
        text=True,
    )
    captured = json.loads(output.read_text())
    assert captured["pipeline_ok"]
    assert all(value > 0 for value in captured["infrastructure_calls"].values())
    now = datetime.fromisoformat(captured["observed_at"])
    # Explicit caller inputs at the supported promotion boundary; returned API
    # CDA/candidate data is never edited and no actual state sensor is claimed.
    promotion = build_canonical_verified_decision_promotion_packet(
        captured["canonical_decision_artifact"],
        captured["candidate"],
        promoted_at=now,
        ttl_seconds=300,
        expected_state_fingerprint="synthetic:observed-state:one",
    )
    return build_native_authority_source(promotion, now), now, request.param, captured


def test_real_api_with_explicit_runtime_inputs_reaches_risk_pass(api_risk_source):
    source, now, required, _ = api_risk_source
    before = source.model_dump(mode="json")
    final, packet, inputs = _risk_chain(
        source, _contract(action="post_synthetic_review", required=required), now
    )
    verified = module.require_promotion_requirement_runtime_risk_pass(
        packet, final, **inputs
    )
    assert verified.required_human_approval is required
    assert (
        "human_approval_receipt_verification"
        in verified.future_authorization_requirements
    ) is required
    assert verified.execution_intent_id == source.execution_intent_id
    assert not verified.ready_for_real_bind
    assert source.model_dump(mode="json") == before


def test_real_api_missing_runtime_metadata_stays_indeterminate(api_risk_source):
    _, now, required, captured = api_risk_source
    promotion = build_canonical_verified_decision_promotion_packet(
        captured["canonical_decision_artifact"], captured["candidate"], promoted_at=now
    )
    source = build_native_authority_source(promotion, now)
    final, packet, inputs = _risk_chain(
        source, _contract(action="post_synthetic_review", required=required), now
    )
    assert packet.risk_result.outcome == "INDETERMINATE_FAIL_CLOSED"
    assert "CPLADRRR_INTENT_TTL_MISSING" in packet.risk_result.reason_codes
    assert "CPLADRRR_EXPECTED_STATE_FINGERPRINT_MISSING" in packet.risk_result.reason_codes
    with pytest.raises(ValueError, match="PRRR_RISK_NOT_ACCEPTABLE"):
        module.require_promotion_requirement_runtime_risk_pass(packet, final, **inputs)


@pytest.mark.parametrize("case", ["before_source", "too_long", "expired", "naive"])
def test_review_window_binding_is_enforced(chain, case):
    final, packet, inputs = chain
    decision = dict(inputs["expected_risk_decision"])
    if case == "before_source":
        decision["reviewed_at"] = (
            inputs["expected_rechecked_at"] - timedelta(seconds=1)
        ).isoformat()
    elif case == "too_long":
        decision["valid_until"] = (
            datetime.fromisoformat(decision["reviewed_at"]) + timedelta(seconds=301)
        ).isoformat()
    elif case == "expired":
        decision["valid_until"] = inputs["expected_recorded_at"].isoformat()
    else:
        decision["reviewed_at"] = datetime.fromisoformat(
            decision["reviewed_at"]
        ).replace(tzinfo=None).isoformat()
    with pytest.raises(ValueError):
        module.verify_promotion_requirement_runtime_risk_packet(
            packet, final, **{**inputs, "expected_risk_decision": decision}
        )
