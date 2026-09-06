"""Independent policy, time, endpoint and credential anchors at final recheck."""

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from veritas_os.policy import promotion_requirement_final_rechecks as module
from veritas_os.policy import promotion_requirement_bind_readiness as reviews
from veritas_os.tests.test_promotion_requirement_bind_readiness import _chain, _decision
from veritas_os.tests.test_promotion_human_approval_requirement_satisfaction import (
    api_source as captured_api_source,
    native as native_source,
    _contract,
    authority,
    sources,
)

pytestmark = pytest.mark.slow
api_source = captured_api_source
native = native_source


def _inputs(source, contract, now):
    reference = deepcopy(source.credential_reference)
    return {
        "expected_source": source,
        "expected_contract": contract,
        "expected_verified_at": now,
        "current_endpoint": deepcopy(source.endpoint_candidate),
        "current_credential_reference": reference,
        "required_credential_scope": reference["credential_scope"],
    }


def _complete(source, contract, now):
    _, gate = _chain(source, contract, now)
    fresh = module.build_promotion_requirement_fresh_source_packet(
        gate, now, expected_source=source, expected_contract=contract
    )
    inputs = _inputs(source, contract, now)
    final = module.build_promotion_requirement_final_recheck_packet(
        fresh, now, **inputs
    )
    return gate, fresh, final, inputs


@pytest.fixture(scope="module")
def complete(native):
    source, contract, _, now = native
    return _complete(source, contract, now)


def _verify(stage, packet, inputs):
    if stage == "fresh":
        return module.verify_promotion_requirement_fresh_source_packet(
            packet,
            **{
                k: inputs[k]
                for k in (
                    "expected_source",
                    "expected_contract",
                    "expected_verified_at",
                )
            },
        )
    return module.verify_promotion_requirement_final_recheck_packet(
        packet, expected_rechecked_at=inputs["expected_verified_at"], **inputs
    )


@pytest.mark.parametrize("required", [False, True])
def test_both_approval_states_reach_exact_final_rechecks(native, complete, required):
    source, _, _, now = native
    gate, fresh, final, inputs = (
        complete if required else _complete(source, _contract(required=False), now)
    )
    for stage, packet in (("fresh", fresh), ("final", final)):
        verified = _verify(stage, packet.model_dump(mode="json"), inputs)
        assert verified == packet and verified is not packet
        assert verified.required_human_approval is required
        assert verified.execution_intent == source.execution_intent
        for name in (
            *module.ABSENT_FIELDS,
            "external_policy_freshness_verified",
            "revocation_verified",
            "tls_peer_verified",
            "credential_provider_verified",
        ):
            assert getattr(verified, name) is False
        schema = (
            Path(__file__).resolve().parents[2]
            / "schemas"
            / (packet.format_version.replace("/", "-") + ".schema.json")
        )
        Draft202012Validator(json.loads(schema.read_text())).validate(
            verified.model_dump(mode="json")
        )
    assert fresh.source_packet == gate.model_dump(mode="json")
    assert final.source_packet == fresh.model_dump(mode="json")
    assert final.bind_context_hash == fresh.bind_context_hash
    assert final.exact_bind_context == fresh.exact_bind_context
    assert final.exact_bind_context.gate_packet_hash == gate.packet_hash
    assert fresh.future_authorization_requirements[:2] == [
        "final_endpoint_identity_recheck",
        "final_credential_scope_recheck",
    ]
    assert final.future_authorization_requirements[0] == "runtime_risk_review"
    assert (
        "human_approval_receipt_verification" in final.future_authorization_requirements
    ) is required
    assert final.future_invocation_requirements == gate.future_invocation_requirements
    assert final.endpoint_rechecked and final.credential_scope_rechecked


@pytest.mark.parametrize(
    "rules",
    [
        {"required": False, "minimum_approvals": 0},
        {"required": True, "minimum_approvals": 2},
        {"required": True, "minimum_approvals": 1, "approver_role": "attacker"},
    ],
)
def test_full_chain_rehash_cannot_replace_same_id_version_contract(native, rules):
    source, trusted, _, now = native
    attacker = replace(trusted, human_approval_rules=rules)
    assert (attacker.id, attacker.version) == (trusted.id, trusted.version)
    _, fresh, final, inputs = _complete(source, attacker, now)
    inputs["expected_contract"] = trusted
    for stage, packet in (("fresh", fresh), ("final", final)):
        with pytest.raises(ValueError):
            _verify(stage, packet, inputs)


def test_full_chain_rehash_cannot_replace_external_source(native):
    source, contract, _, now = native
    bundle = source.authority_evidence_reference_bundle.model_dump(mode="json")
    bundle["bundle_declared_by"] = "attacker"
    other = authority(
        source.source_bind_pre_dispatch_review_packet, bundle, sources.RECORDED_AT
    )
    _, fresh, final, inputs = _complete(other, contract, now)
    inputs["expected_source"] = source
    for stage, packet in (("fresh", fresh), ("final", final)):
        with pytest.raises(ValueError):
            _verify(stage, packet, inputs)


@pytest.mark.parametrize(
    "field",
    [
        "endpoint_candidate_id",
        "adapter_contract_id",
        "target_system",
        "target_resource_scope",
        "declared_by",
    ],
)
def test_current_endpoint_drift_rejects_previously_valid_packet(complete, field):
    _, fresh, final, original = complete
    inputs = dict(original)
    inputs["current_endpoint"] = {**original["current_endpoint"], field: "changed"}
    with pytest.raises(ValueError):
        _verify("final", final, inputs)
    with pytest.raises(ValueError):
        module.build_promotion_requirement_final_recheck_packet(
            fresh, inputs["expected_verified_at"], **inputs
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("endpoint_kind", "changed"),
        ("endpoint_scheme", "http"),
        ("endpoint_host", "changed.invalid"),
        ("endpoint_port", 4444),
        ("endpoint_path_prefix", "/changed"),
        ("endpoint_environment", "changed"),
        ("endpoint_purpose", "changed"),
    ],
)
def test_current_endpoint_transport_change_fails(complete, field, value):
    _, _, final, original = complete
    assert original["current_endpoint"][field] != value
    inputs = {
        **original,
        "current_endpoint": {**original["current_endpoint"], field: value},
    }
    with pytest.raises(ValueError, match="PRRC_ENDPOINT_MISMATCH"):
        _verify("final", final, inputs)


@pytest.mark.parametrize(
    "field",
    [
        "credential_reference_id",
        "credential_kind",
        "credential_provider_type",
        "credential_scope",
        "credential_environment",
        "credential_purpose",
        "adapter_contract_id",
        "endpoint_candidate_id",
        "target_system",
        "target_resource_scope",
    ],
)
def test_current_credential_drift_rejects_previously_valid_packet(complete, field):
    _, _, final, original = complete
    inputs = dict(original)
    inputs["current_credential_reference"] = {
        **original["current_credential_reference"],
        field: "changed",
    }
    with pytest.raises(ValueError, match="PRRC_CREDENTIAL_MISMATCH"):
        _verify("final", final, inputs)


@pytest.mark.parametrize("scope", ["*", "read", "write", "", None])
def test_exact_required_scope_never_infers_containment(complete, scope):
    _, _, final, inputs = complete
    with pytest.raises(ValueError):
        _verify("final", final, {**inputs, "required_credential_scope": scope})


@pytest.mark.parametrize(
    "missing",
    [
        "expected_source",
        "expected_contract",
        "expected_verified_at",
        "expected_rechecked_at",
        "current_endpoint",
        "current_credential_reference",
        "required_credential_scope",
    ],
)
def test_final_verifier_requires_every_independent_input(complete, missing):
    _, _, final, original = complete
    inputs = {**original, "expected_rechecked_at": original["expected_verified_at"]}
    del inputs[missing]
    with pytest.raises(TypeError):
        module.verify_promotion_requirement_final_recheck_packet(final, **inputs)
    inputs[missing] = None
    with pytest.raises(ValueError):
        module.verify_promotion_requirement_final_recheck_packet(final, **inputs)


@pytest.mark.parametrize("stage", ["fresh", "final"])
@pytest.mark.parametrize(
    "field",
    [
        "required_human_approval",
        "bind_context_hash",
        "source_packet_hash",
        "future_authorization_requirements",
        "execution_intent",
    ],
)
def test_rehashed_derived_fields_fail_closed(complete, stage, field):
    _, fresh, final, inputs = complete
    raw = (fresh if stage == "fresh" else final).model_dump(mode="json")
    raw[field] = (
        False
        if isinstance(raw[field], bool)
        else []
        if isinstance(raw[field], list)
        else {}
        if isinstance(raw[field], dict)
        else "0" * 64
    )
    raw = module._seal(raw)
    with pytest.raises(ValueError, match="PRRC_RECONSTRUCTION_MISMATCH"):
        _verify(stage, raw, inputs)


@pytest.mark.parametrize(
    "field",
    [
        "action_contract_digest",
        "credential_scope_binding_digest",
        "endpoint_identity_binding_digest",
    ],
)
def test_rehashed_bind_context_cannot_replace_verified_bindings(complete, field):
    _, _, final, inputs = complete
    raw = final.model_dump(mode="json")
    raw["exact_bind_context"][field] = "0" * 64
    raw["bind_context_hash"] = module._digest(
        "veritas.requirement-exact-bind-context/v1", raw["exact_bind_context"]
    )
    with pytest.raises(ValueError, match="PRRC_RECONSTRUCTION_MISMATCH"):
        _verify("final", module._seal(raw), inputs)


@pytest.mark.parametrize("field", ["fresh_verified_at", "rechecked_at"])
def test_rehashed_time_is_bound_to_external_time(complete, field):
    _, fresh, final, inputs = complete
    stage = "fresh" if field == "fresh_verified_at" else "final"
    raw = (fresh if stage == "fresh" else final).model_dump(mode="json")
    raw[field] = (inputs["expected_verified_at"] + timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError):
        _verify(stage, module._seal(raw), inputs)


def test_rejected_gate_and_backwards_or_naive_times_fail(complete):
    gate, fresh, _, inputs = complete
    now = inputs["expected_verified_at"]
    anchors = {k: inputs[k] for k in ("expected_source", "expected_contract")}
    rejected = reviews.build_promotion_requirement_bind_gate_packet(
        gate.source_packet, _decision(now, False), now, **anchors
    )
    with pytest.raises(ValueError, match="PRRC_GATE_REJECTED"):
        module.build_promotion_requirement_fresh_source_packet(rejected, now, **anchors)
    for invalid in (now - timedelta(seconds=1), now.replace(tzinfo=None)):
        with pytest.raises(ValueError):
            module.build_promotion_requirement_fresh_source_packet(
                gate, invalid, **anchors
            )
        with pytest.raises(ValueError):
            module.build_promotion_requirement_final_recheck_packet(
                fresh, invalid, **inputs
            )


@pytest.mark.parametrize("key", ["current_endpoint", "current_credential_reference"])
def test_sensitive_metadata_is_rejected(complete, key):
    _, _, final, original = complete
    inputs = {
        **original,
        key: {**original[key], "authorization": "test-only-forbidden"},
    }
    with pytest.raises(ValueError):
        _verify("final", final, inputs)


def test_requirement_order_helper_rejects_skipped_checks():
    with pytest.raises(ValueError, match="PRRC_REQUIREMENT_ORDER"):
        module._remaining(["runtime_risk_review"], ("final_credential_scope_recheck",))


def test_real_authenticated_decision_reaches_final_metadata_rechecks(api_source):
    source, now, required = api_source
    before = source.model_dump(mode="json")
    contract = _contract(action="post_synthetic_review", required=required)
    _, _, final, inputs = _complete(source, contract, now)
    verified = _verify("final", final, inputs)
    assert verified.execution_intent == source.execution_intent
    assert verified.required_human_approval is required
    assert verified.endpoint_rechecked and verified.credential_scope_rechecked
    assert not verified.ready_for_real_bind
    assert source.model_dump(mode="json") == before
