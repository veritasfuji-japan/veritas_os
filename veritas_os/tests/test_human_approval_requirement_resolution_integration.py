"""Independent-source verification using the real nested linkage chain.

These are metadata-linkage fixtures, not authenticated authority evidence.
No source verifier is replaced with a mock.
"""

from copy import deepcopy
from dataclasses import replace

import pytest

from veritas_os.policy import human_approval_requirement_resolution as resolution
from veritas_os.tests.test_gate_bound_human_approval_issuance import _contract
from veritas_os.tests.test_live_adapter_dry_run_authority_evidence_linkage import (
    RECORDED_AT,
    _packet,
)

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def chain():
    source = _packet()
    contract = _contract(source)
    packet = resolution.build_human_approval_requirement_resolution_packet(
        source, contract, RECORDED_AT
    )
    return source, contract, packet


def _rehash(raw):
    body = dict(raw)
    body.pop("human_approval_requirement_resolution_hash")
    body.pop("human_approval_requirement_resolution_id")
    digest = resolution._digest(body)
    raw["human_approval_requirement_resolution_hash"] = digest
    raw["human_approval_requirement_resolution_id"] = f"harr:v1:sha256:{digest}"


def test_real_chain_roundtrip(chain):
    source, contract, packet = chain
    verified = resolution.verify_human_approval_requirement_resolution_packet(
        packet.model_dump(mode="json"), source.model_dump(mode="json"), contract
    )
    assert verified == packet
    assert verified.required_human_approval
    assert not verified.execution_authority_created


@pytest.mark.parametrize(
    "change",
    [
        {"execution_authority_created": True},
        {"unexpected_field": True},
        {"required_human_approval": False},
    ],
)
def test_invalid_schema_or_inconsistent_state(chain, change):
    source, contract, packet = chain
    raw = packet.model_dump(mode="json")
    raw.update(change)
    with pytest.raises(resolution.HumanApprovalRequirementResolutionError):
        resolution.verify_human_approval_requirement_resolution_packet(
            raw, source, contract
        )


def test_downgrade_with_recomputed_hash_is_rejected(chain):
    source, contract, packet = chain
    raw = packet.model_dump(mode="json")
    raw.update(
        required_human_approval=False,
        requirement_state="NOT_REQUIRED_BY_ACTION_CONTRACT",
        requirement_reason="action_contract_does_not_require_human_approval",
    )
    _rehash(raw)
    with pytest.raises(
        resolution.HumanApprovalRequirementResolutionError, match="RECONSTRUCTION"
    ):
        resolution.verify_human_approval_requirement_resolution_packet(
            raw, source, contract
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_execution_intent_hash", "a" * 64),
        ("source_authority_evidence_linkage_review_hash", "a" * 64),
        ("action_contract_digest", "a" * 64),
        ("requirement_reason", "invented"),
        ("scope_limitations", []),
        ("resolved_at", "not-a-time"),
        ("required_human_approval", 1),
    ],
)
def test_rehashed_substitution_rejected(chain, field, value):
    source, contract, packet = chain
    raw = packet.model_dump(mode="json")
    raw[field] = value
    _rehash(raw)
    with pytest.raises(resolution.HumanApprovalRequirementResolutionError):
        resolution.verify_human_approval_requirement_resolution_packet(
            raw, source, contract
        )


def test_changed_contract_same_id_rejected(chain):
    source, contract, packet = chain
    changed = replace(
        contract,
        human_approval_rules={"required": False},
        irreversibility={"level": "low"},
    )
    with pytest.raises(
        resolution.HumanApprovalRequirementResolutionError, match="RECONSTRUCTION"
    ):
        resolution.verify_human_approval_requirement_resolution_packet(
            packet, source, changed
        )


@pytest.mark.parametrize("source_value", [None, {}])
def test_missing_source_rejected(chain, source_value):
    _, contract, packet = chain
    with pytest.raises(
        resolution.HumanApprovalRequirementResolutionError, match="SOURCE_INVALID"
    ):
        resolution.verify_human_approval_requirement_resolution_packet(
            packet, source_value, contract
        )


def test_nested_source_tamper_rejected(chain):
    source, contract, packet = chain
    raw = deepcopy(source.model_dump(mode="json"))
    raw["execution_intent"]["intended_action"] = "another-action"
    with pytest.raises(
        resolution.HumanApprovalRequirementResolutionError, match="SOURCE_INVALID"
    ):
        resolution.verify_human_approval_requirement_resolution_packet(
            packet, raw, contract
        )


def test_not_required_still_supported(chain):
    source, contract, _ = chain
    contract = replace(
        contract,
        human_approval_rules={"required": False},
        irreversibility={"level": "low"},
    )
    packet = resolution.build_human_approval_requirement_resolution_packet(
        source, contract, RECORDED_AT
    )
    verified = resolution.verify_human_approval_requirement_resolution_packet(
        packet, source, contract
    )
    assert not verified.required_human_approval
    assert not verified.human_approval_created
