"""Tests for pre-bind governance evaluation/assembly composition."""

from __future__ import annotations

from veritas_os.core.pipeline.governance_layers import (
    assemble_governance_public_fields,
    evaluate_governance_layers,
)


def test_evaluate_governance_layers_returns_empty_snapshot_without_signal() -> None:
    snapshot = evaluate_governance_layers(participation_signal=None)

    assert snapshot.participation_signal is None
    assert snapshot.pre_bind_detection == {}
    assert snapshot.pre_bind_preservation == {}


def test_assemble_governance_public_fields_preserves_contract_shape() -> None:
    signal = {
        "participation_signal_id": "ps-1",
        "participation_admissibility": "admissible",
        "structural_signal": "open_participation",
        "source": "unit-test",
    }

    snapshot = evaluate_governance_layers(participation_signal=signal)
    payload = assemble_governance_public_fields(snapshot)

    assert payload["participation_signal"]["participation_signal_id"] == "ps-1"
    assert payload["pre_bind_detection_summary"]["detection_family"] == (
        "pre_bind_structural_detection"
    )
    assert payload["pre_bind_preservation_summary"]["preservation_family"] == (
        "pre_bind_preservation"
    )
    assert "pre_bind_detection_detail" in payload
    assert "pre_bind_preservation_detail" in payload
