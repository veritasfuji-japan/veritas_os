"""Whole-chain rehash attacks cannot replace independent policy/source inputs."""

from dataclasses import replace

import pytest

from veritas_os.policy.human_approval_requirement_resolution import (
    build_human_approval_requirement_resolution_packet,
)
from veritas_os.policy.live_adapter_dry_run_human_approval_requirement_satisfaction import (
    build_live_adapter_dry_run_human_approval_requirement_satisfaction_packet as build,
    verify_live_adapter_dry_run_human_approval_requirement_satisfaction_packet as verify,
)
from veritas_os.policy.live_adapter_dry_run_final_bind_authorization_readiness import (
    verify_live_adapter_dry_run_final_bind_authorization_readiness_packet as verify_final,
)
from veritas_os.policy.live_adapter_dry_run_bind_authorization_gate_review import (
    verify_live_adapter_dry_run_bind_authorization_gate_review_packet as verify_gate,
)
from veritas_os.tests.test_live_adapter_dry_run_human_approval_requirement_satisfaction import (
    _build_satisfaction,
    _build_gate,
    HUMAN_RECORDED_AT,
    SATISFACTION_RECORDED_AT,
)
from veritas_os.tests.test_live_adapter_dry_run_authority_evidence_linkage import (
    _packet,
    _bundle,
)

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def attack():
    source, trusted, _, _, original = _build_satisfaction(required=True)
    substituted = replace(
        trusted, human_approval_rules={"required": False, "minimum_approvals": 0}
    )
    assert substituted.id == trusted.id and substituted.version == trusted.version
    resolution = build_human_approval_requirement_resolution_packet(
        source, substituted, HUMAN_RECORDED_AT
    )
    forged = build(source, resolution, substituted, None, SATISFACTION_RECORDED_AT)
    final, gate = _build_gate(forged, source, substituted)
    assert original.required_human_approval and not forged.required_human_approval
    return source, trusted, substituted, (forged, final, gate)


@pytest.mark.parametrize("stage", range(3))
def test_full_rehash_same_id_version_contract_downgrade_rejected(attack, stage):
    source, trusted, substituted, packets = attack
    verifier = (verify, verify_final, verify_gate)[stage]
    # Positive control: these are internally valid, fully rehashed packets.
    verifier(packets[stage], expected_source=source, expected_contract=substituted)
    with pytest.raises(ValueError):
        verifier(packets[stage], expected_source=source, expected_contract=trusted)


@pytest.mark.parametrize("stage", range(3))
@pytest.mark.parametrize("missing", ["source", "contract", "both"])
def test_no_embedded_fallback(attack, stage, missing):
    source, _, contract, packets = attack
    with pytest.raises(ValueError):
        (verify, verify_final, verify_gate)[stage](
            packets[stage],
            expected_source=None if missing in ("source", "both") else source,
            expected_contract=None if missing in ("contract", "both") else contract,
        )


def test_fully_rebuilt_source_substitution_rejected(attack):
    original_source, _, contract, _ = attack
    substituted = _packet(
        bundle=_bundle(bundle_declared_by="different-source-declarer")
    )
    resolution = build_human_approval_requirement_resolution_packet(
        substituted, contract, HUMAN_RECORDED_AT
    )
    forged = build(substituted, resolution, contract, None, SATISFACTION_RECORDED_AT)
    final, gate = _build_gate(forged, substituted, contract)
    for packet, verifier in zip(
        (forged, final, gate), (verify, verify_final, verify_gate), strict=True
    ):
        with pytest.raises(ValueError):
            verifier(
                packet, expected_source=original_source, expected_contract=contract
            )
