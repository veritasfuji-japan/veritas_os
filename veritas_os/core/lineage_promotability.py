"""Pre-bind formation-space lineage promotability invariant evaluator."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping

PromotabilityStatus = Literal["promotable", "restricted", "non_promotable"]

LINEAGE_PROMOTABILITY_FAMILY = "lineage_promotability"
LINEAGE_PROMOTABILITY_VERSION = "v1"
NON_PROMOTABLE_INVARIANT_ID = (
    "BIND_ELIGIBLE_ARTIFACT_CANNOT_EMERGE_FROM_NON_PROMOTABLE_LINEAGE"
)


@dataclass(frozen=True)
class LineagePromotability:
    """Typed summary for lineage promotability invariant evaluation."""

    promotability_family: str
    promotability_version: str
    promotability_status: PromotabilityStatus
    reason_code: str | None
    invariant_id: str
    source_participation_state: str | None
    source_preservation_state: str | None
    transformation_stable: bool
    concise_rationale: str


def evaluate_lineage_promotability(
    *,
    pre_bind_detection_summary: Mapping[str, Any] | None,
    pre_bind_preservation_summary: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Evaluate whether current pre-bind formation lineage can be bind-eligible."""
    participation_state = None
    preservation_state = None
    if isinstance(pre_bind_detection_summary, Mapping):
        participation_state = pre_bind_detection_summary.get("participation_state")
    if isinstance(pre_bind_preservation_summary, Mapping):
        preservation_state = pre_bind_preservation_summary.get("preservation_state")

    if (
        participation_state == "decision_shaping"
        and preservation_state == "collapsed"
    ):
        return asdict(
            LineagePromotability(
                promotability_family=LINEAGE_PROMOTABILITY_FAMILY,
                promotability_version=LINEAGE_PROMOTABILITY_VERSION,
                promotability_status="non_promotable",
                reason_code="NON_PROMOTABLE_LINEAGE",
                invariant_id=NON_PROMOTABLE_INVARIANT_ID,
                source_participation_state="decision_shaping",
                source_preservation_state="collapsed",
                transformation_stable=True,
                concise_rationale=(
                    "A bind-eligible artifact cannot be constructed from a "
                    "non-promotable pre-bind formation lineage."
                ),
            )
        )

    return asdict(
        LineagePromotability(
            promotability_family=LINEAGE_PROMOTABILITY_FAMILY,
            promotability_version=LINEAGE_PROMOTABILITY_VERSION,
            promotability_status="promotable",
            reason_code=None,
            invariant_id=NON_PROMOTABLE_INVARIANT_ID,
            source_participation_state=None,
            source_preservation_state=None,
            transformation_stable=True,
            concise_rationale=(
                "No non-promotable formation lineage was detected in the "
                "current v1 invariant set."
            ),
        )
    )
