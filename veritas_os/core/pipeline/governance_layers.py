"""Governance layer evaluation/assembly helpers for decide response payloads.

This module keeps pre-bind governance concerns separated by responsibility:
- evaluation: participation detection + preservation evaluation
- assembly: stable public response field mapping

It preserves the existing public DecideResponse contract shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from veritas_os.core.participation_detection import (
    evaluate_pre_bind_structural_detection,
)
from veritas_os.core.preservation_evaluator import evaluate_pre_bind_preservation


@dataclass(frozen=True)
class GovernanceEvaluationSnapshot:
    """Typed snapshot bridging evaluators and response assembly."""

    participation_signal: Dict[str, Any] | None
    pre_bind_detection: Dict[str, Any]
    pre_bind_preservation: Dict[str, Any]


def evaluate_governance_layers(
    *,
    participation_signal: Any,
) -> GovernanceEvaluationSnapshot:
    """Run pre-bind governance evaluators and return a typed snapshot."""
    normalized_signal = participation_signal if isinstance(participation_signal, dict) else None
    if normalized_signal is None:
        return GovernanceEvaluationSnapshot(
            participation_signal=None,
            pre_bind_detection={},
            pre_bind_preservation={},
        )

    detection = evaluate_pre_bind_structural_detection(normalized_signal)
    preservation = evaluate_pre_bind_preservation(
        normalized_signal,
        pre_bind_detection_summary=detection.get("pre_bind_detection_summary"),
    )
    return GovernanceEvaluationSnapshot(
        participation_signal=normalized_signal,
        pre_bind_detection=detection,
        pre_bind_preservation=preservation,
    )


def assemble_governance_public_fields(
    snapshot: GovernanceEvaluationSnapshot,
) -> Dict[str, Any]:
    """Assemble additive public governance fields from evaluator snapshot."""
    return {
        "participation_signal": snapshot.participation_signal,
        "pre_bind_detection_summary": snapshot.pre_bind_detection.get(
            "pre_bind_detection_summary"
        ),
        "pre_bind_detection_detail": snapshot.pre_bind_detection.get(
            "pre_bind_detection_detail"
        ),
        "pre_bind_preservation_summary": snapshot.pre_bind_preservation.get(
            "pre_bind_preservation_summary"
        ),
        "pre_bind_preservation_detail": snapshot.pre_bind_preservation.get(
            "pre_bind_preservation_detail"
        ),
    }
