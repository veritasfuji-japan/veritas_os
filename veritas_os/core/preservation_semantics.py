"""Pre-bind preservation vocabulary and normalization helpers.

This module defines additive vocabulary for the preservation layer, which is
adjacent to (and distinct from) pre-bind detection:

- detection: did structural threshold crossing occur?
- preservation: does meaningful intervention remain realistically possible?
"""

from __future__ import annotations

from typing import Any, Mapping

from veritas_os.core.participation_semantics import (
    normalize_participation_signal_payload,
)

PRESERVATION_FAMILY = "pre_bind_preservation"
PRESERVATION_VERSION = "v1"

PRESERVATION_STATE_VALUES: tuple[str, ...] = ("open", "degrading", "collapsed")
INTERVENTION_VIABILITY_VALUES: tuple[str, ...] = ("high", "partial", "minimal", "none")
OPENNESS_FLOOR_STATUS_VALUES: tuple[str, ...] = ("met", "at_risk", "breached")


def normalize_preservation_input(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize preservation input by reusing participation structural vocabulary."""
    return normalize_participation_signal_payload(payload)
