# veritas_os/core/continuation_runtime/lawpack.py
# -*- coding: utf-8 -*-
"""
ContinuationLawPack — versioned, immutable rule set for revalidation.

Law packs define the conditions under which continuation standing is
maintained, narrowed, or lost.  They are NOT policies in the FUJI sense
(content safety); they govern the structural validity of continuation.

Each law pack is versioned and immutable once published.  Snapshots
record which law_version was applied so that replay can deterministically
reproduce the revalidation.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List


class EvaluationMode(str, Enum):
    """How the law pack's rules are combined during revalidation."""

    SHADOW = "shadow"
    ADVISORY = "advisory"
    ENFORCE = "enforce"

    def __str__(self) -> str:
        return self.value


@dataclass
class ContinuationLawPack:
    """Versioned rule set governing continuation revalidation.

    Immutable once published.  ``law_version_id`` is the primary
    reference used by snapshots and receipts.
    """

    law_version_id: str = ""
    policy_family: str = ""
    invariant_family: str = ""
    corridor_family: str = ""
    rule_refs: List[str] = field(default_factory=list)
    evaluation_mode: EvaluationMode = EvaluationMode.SHADOW

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict representation."""
        d = asdict(self)
        d["evaluation_mode"] = self.evaluation_mode.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContinuationLawPack":
        """Reconstruct from a dict (e.g. deserialized JSON)."""
        data = dict(data)  # shallow copy
        if "evaluation_mode" in data and isinstance(data["evaluation_mode"], str):
            data["evaluation_mode"] = EvaluationMode(data["evaluation_mode"])
        return cls(**data)
