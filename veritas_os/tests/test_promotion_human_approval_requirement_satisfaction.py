"""Independent anchors and adversarial native approval-requirement tests."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator

from veritas_os.governance.action_contracts import ActionClassContract
from veritas_os.policy.human_approval_requirement_resolution import (
    build_human_approval_requirement_resolution_packet as resolve,
    verify_human_approval_requirement_resolution_packet as verify_resolution,
    _digest as resolution_digest,
)
from veritas_os.policy.promotion_human_approval_requirement_satisfaction import (
    build_promotion_human_approval_requirement_satisfaction_packet as satisfy,
    verify_promotion_human_approval_requirement_satisfaction_packet as verify,
    _packet_hash,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_human_approval_linkage import (
    build_canonical_promotion_live_adapter_dry_run_human_approval_linkage_review_packet as link,
)
from veritas_os.policy.canonical_promotion_live_adapter_dry_run_authority_evidence_linkage import (
    build_canonical_promotion_live_adapter_dry_run_authority_evidence_linkage_review_packet as authority,
)
from veritas_os.tests import (
    test_canonical_promotion_live_adapter_dry_run_authority_evidence_linkage as sources,
)
from veritas_os.tests import (
    test_canonical_promotion_live_adapter_dry_run_human_approval_linkage as humans,
)
from veritas_os.governance.canonical_decision_artifact import (
    verify_canonical_decision_artifact,
)
from veritas_os.policy.canonical_verified_decision_promotion import (
    build_canonical_verified_decision_promotion_packet,
)
from veritas_os.tests.helpers.native_approval_source import (
    build_native_authority_source,
)

pytestmark = pytest.mark.slow


def _contract(action="set_state:one", required=True):
    return ActionClassContract(
        id=action,
        version="1",
        domain="local-native-test",
        action_class=action,
        description="Independent local action policy",
        declared_intent="Test one declared operation",
        allowed_scope=["bind-request"],
        prohibited_scope=["admin"],
        authority_sources=["authority:local-reference-only"],
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
        metadata={},
    )


def _link(source, now):
    bundle = humans._bundle(source)
    bundle["bundle_declared_at"] = now.isoformat()
    for item in bundle["human_approval_references"]:
        item["approval_issued_at"] = (now - timedelta(seconds=1)).isoformat()
        item["approval_expires_at"] = (now + timedelta(minutes=5)).isoformat()
    return link(source, bundle, now)


@pytest.fixture(scope="module")
def native():
    source = sources._packet()
    now = humans.RECORDED_AT + timedelta(seconds=1)
    return source, _contract(), _link(source, now), now


@pytest.mark.parametrize("required", [False, True])
def test_native_requirement_preserves_complete_source_and_no_authority(
    native, required
):
    source, _, linkage, now = native
    contract = _contract(required=required)
    resolution = resolve(source, contract, now)
    assert verify_resolution(resolution, source, contract) == resolution
    packet = satisfy(source, resolution, contract, linkage if required else None, now)
    verified = verify(packet, expected_source=source, expected_contract=contract)
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "schemas/promotion-human-approval-requirement-satisfaction-v1.schema.json"
    )
    Draft202012Validator(json.loads(schema_path.read_text())).validate(
        verified.model_dump(mode="json")
    )
    assert verified == packet and verified is not packet
    assert verified.execution_intent == source.execution_intent
    assert verified.execution_intent_id == source.execution_intent_id
    assert verified.execution_intent_hash == source.execution_intent_hash
    assert (
        verified.source_authority_evidence_linkage_review_packet
        == source.model_dump(mode="json")
    )
    assert verified.required_human_approval is required
    assert (
        verified.human_approval_requirement_resolution_packet
        == resolution.model_dump(mode="json")
    )
    for field in (
        "human_approval_created",
        "human_approval_proven",
        "authority_evidence_proven",
        "execution_authority_created",
        "bind_authorization_created",
        "bind_invoked",
        "bind_receipt_created",
        "credential_material_accessed",
        "network_used",
        "external_effect_occurred",
        "ready_for_real_bind",
    ):
        assert getattr(verified, field) is False


@pytest.mark.parametrize(
    "rules",
    [
        {"required": False, "minimum_approvals": 0},
        {"required": True, "minimum_approvals": 2},
        {"required": True, "minimum_approvals": 1, "approver_role": "attacker"},
    ],
)
def test_fully_rebuilt_same_id_version_policy_substitution_fails(native, rules):
    source, trusted, linkage, now = native
    forged_contract = replace(trusted, human_approval_rules=rules)
    assert (forged_contract.id, forged_contract.version) == (
        trusted.id,
        trusted.version,
    )
    forged_resolution = resolve(source, forged_contract, now)
    forged = satisfy(
        source,
        forged_resolution,
        forged_contract,
        linkage if forged_resolution.required_human_approval else None,
        now,
    )
    with pytest.raises(ValueError):
        verify(forged, expected_source=source, expected_contract=trusted)
    with pytest.raises(ValueError):
        verify_resolution(forged_resolution, source, trusted)


def test_fully_rebuilt_source_substitution_fails(native):
    original, contract, _, now = native
    bundle = original.authority_evidence_reference_bundle.model_dump(mode="json")
    bundle["bundle_declared_by"] = "attacker"
    forged_source = authority(
        original.source_bind_pre_dispatch_review_packet, bundle, sources.RECORDED_AT
    )
    forged = satisfy(
        forged_source,
        resolve(forged_source, contract, now),
        contract,
        _link(forged_source, now),
        now,
    )
    with pytest.raises(ValueError):
        verify(forged, expected_source=original, expected_contract=contract)


def test_valid_linkage_for_another_source_cannot_satisfy_requirement(native):
    source, contract, _, now = native
    bundle = source.authority_evidence_reference_bundle.model_dump(mode="json")
    bundle["bundle_declared_by"] = "different-reviewer"
    other = authority(
        source.source_bind_pre_dispatch_review_packet, bundle, sources.RECORDED_AT
    )
    with pytest.raises(ValueError, match="PHARS_LINKAGE_SOURCE_MISMATCH"):
        satisfy(
            source, resolve(source, contract, now), contract, _link(other, now), now
        )


@pytest.mark.parametrize("change", ["format", "nested_hash"])
def test_native_source_cannot_be_relabeled_or_tampered(native, change):
    source, contract, _, now = native
    raw = source.model_dump(mode="json")
    if change == "format":
        raw["format_version"] = (
            "canonical-live-adapter-dry-run-authority-evidence-linkage-review/v1"
        )
    else:
        raw["source_bind_pre_dispatch_review_packet"]["execution_intent_hash"] = (
            "0" * 64
        )
    with pytest.raises(ValueError):
        resolve(raw, contract, now)


def test_high_irreversibility_policy_rule_remains_required(native):
    source, contract, _, now = native
    contract = replace(
        contract,
        irreversibility={"level": "high"},
        human_approval_rules={"required": False, "minimum_approvals": 1},
    )
    assert resolve(source, contract, now).required_human_approval is True


def test_satisfaction_cannot_predate_required_linkage(native):
    source, contract, linkage, _ = native
    earlier = sources.RECORDED_AT + timedelta(seconds=1)
    with pytest.raises(ValueError, match="PHARS_TIMESTAMP_ORDER"):
        satisfy(source, resolve(source, contract, earlier), contract, linkage, earlier)


@pytest.mark.parametrize(
    "field",
    [
        "required_human_approval",
        "requirement_state",
        "requirement_reason",
        "action_contract_digest",
        "source_execution_intent_hash",
    ],
)
def test_rehashed_resolution_fields_are_reconstructed(native, field):
    source, contract, linkage, now = native
    raw = resolve(source, contract, now).model_dump(mode="json")
    raw[field] = (
        False
        if field == "required_human_approval"
        else "NOT_REQUIRED_BY_ACTION_CONTRACT"
        if field == "requirement_state"
        else "0" * 64
    )
    payload = {
        k: v
        for k, v in raw.items()
        if k
        not in {
            "human_approval_requirement_resolution_id",
            "human_approval_requirement_resolution_hash",
        }
    }
    digest = resolution_digest(payload)
    raw.update(
        human_approval_requirement_resolution_hash=digest,
        human_approval_requirement_resolution_id=f"harr:v1:sha256:{digest}",
    )
    with pytest.raises(ValueError):
        satisfy(source, raw, contract, linkage, now)


@pytest.mark.parametrize(
    "field",
    [
        "execution_intent_id",
        "execution_intent_hash",
        "action_contract_digest",
        "source_authority_evidence_linkage_review_hash",
        "satisfaction_state",
        "required_human_approval",
    ],
)
def test_rehashed_downstream_copies_do_not_override_rebuilt_resolution(native, field):
    source, contract, linkage, now = native
    raw = satisfy(
        source, resolve(source, contract, now), contract, linkage, now
    ).model_dump(mode="json")
    raw[field] = (
        False
        if field == "required_human_approval"
        else "SATISFIED_AS_NOT_REQUIRED_BY_ACTION_CONTRACT"
        if field == "satisfaction_state"
        else "0" * 64
    )
    digest = _packet_hash(raw)
    raw.update(packet_hash=digest, packet_id=f"phars:v1:sha256:{digest}")
    with pytest.raises(ValueError):
        verify(raw, expected_source=source, expected_contract=contract)


@pytest.mark.parametrize("anchor", ["source", "contract", "missing_keywords"])
def test_independent_anchors_are_mandatory(native, anchor):
    source, contract, linkage, now = native
    packet = satisfy(source, resolve(source, contract, now), contract, linkage, now)
    kwargs = dict(expected_source=source, expected_contract=contract)
    if anchor == "missing_keywords":
        kwargs = {}
    else:
        kwargs["expected_" + anchor] = None
    with pytest.raises((TypeError, ValueError)):
        verify(packet, **kwargs)


@pytest.mark.parametrize("required", [False, True])
def test_missing_or_unexpected_linkage_is_rejected(native, required):
    source, _, linkage, now = native
    contract = _contract(required=required)
    with pytest.raises(ValueError):
        satisfy(
            source,
            resolve(source, contract, now),
            contract,
            None if required else linkage,
            now,
        )


@pytest.mark.parametrize("stage", ["resolution", "satisfaction", "naive"])
def test_invalid_timestamp_order_fails(native, stage):
    source, contract, linkage, now = native
    with pytest.raises(ValueError):
        if stage == "resolution":
            resolve(source, contract, sources.RECORDED_AT - timedelta(seconds=1))
        else:
            satisfy(
                source,
                resolve(source, contract, now),
                contract,
                linkage,
                now.replace(tzinfo=None)
                if stage == "naive"
                else now - timedelta(seconds=1),
            )


@pytest.fixture(scope="module", params=[False, True])
def api_source(request, tmp_path_factory):
    output = tmp_path_factory.mktemp("native-api") / "capture.json"
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
    verification = verify_canonical_decision_artifact(
        captured["canonical_decision_artifact"]
    )
    assert verification.is_valid and verification.artifact is not None
    cda = verification.artifact
    now = datetime.fromisoformat(captured["observed_at"])
    promotion = build_canonical_verified_decision_promotion_packet(
        cda, captured["candidate"], promoted_at=now
    )
    source = build_native_authority_source(promotion, now)
    assert source.execution_intent == promotion.exact_execution_intent
    assert source.execution_intent["decision_id"] == cda.decision_id
    assert source.execution_intent["decision_hash"] == cda.decision_hash
    return source, now, request.param


def test_real_api_native_source_reaches_requirement_satisfaction(api_source):
    source, now, required = api_source
    contract = _contract(action="post_synthetic_review", required=required)
    resolution = resolve(source, contract, now)
    packet = satisfy(
        source, resolution, contract, _link(source, now) if required else None, now
    )
    before = deepcopy(packet.model_dump(mode="json"))
    verified = verify(packet, expected_source=source, expected_contract=contract)
    assert verified.required_human_approval is required
    assert verified.execution_intent == source.execution_intent
    assert packet.model_dump(mode="json") == before
    assert verified.human_approval_proven is False
    assert verified.ready_for_real_bind is False
