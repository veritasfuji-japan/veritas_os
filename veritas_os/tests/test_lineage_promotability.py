"""Tests for lineage promotability invariant evaluation and assembly."""

from __future__ import annotations

from veritas_os.core.lineage_promotability import evaluate_lineage_promotability


def test_lineage_promotability_non_promotable_canonical_case() -> None:
    result = evaluate_lineage_promotability(
        pre_bind_detection_summary={"participation_state": "decision_shaping"},
        pre_bind_preservation_summary={"preservation_state": "collapsed"},
    )
    assert result["promotability_status"] == "non_promotable"
    assert result["reason_code"] == "NON_PROMOTABLE_LINEAGE"
    assert result["transformation_stable"] is True
    assert (
        result["invariant_id"]
        == "BIND_ELIGIBLE_ARTIFACT_CANNOT_EMERGE_FROM_NON_PROMOTABLE_LINEAGE"
    )


def test_lineage_promotability_informative_open_remains_promotable() -> None:
    result = evaluate_lineage_promotability(
        pre_bind_detection_summary={"participation_state": "informative"},
        pre_bind_preservation_summary={"preservation_state": "open"},
    )
    assert result["promotability_status"] == "promotable"
    assert result["reason_code"] is None


def test_lineage_promotability_missing_summaries_remains_promotable() -> None:
    result = evaluate_lineage_promotability(
        pre_bind_detection_summary=None,
        pre_bind_preservation_summary=None,
    )
    assert result["promotability_status"] == "promotable"
    assert result["reason_code"] is None
