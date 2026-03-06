"""EU AI Act dynamic compliance orchestration for API pipeline.

This module is API-layer middleware logic and does not alter Planner/Kernel/FUJI/
MemoryOS core responsibilities.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import threading
from typing import Any, Dict, List, MutableMapping


class ComplianceStopException(RuntimeError):
    """Raised when compliance policy requires a human review stop."""

    def __init__(self, payload: Dict[str, Any]) -> None:
        super().__init__("Compliance stop required: pending human review")
        self.payload = payload


@dataclass
class ComplianceRuntimeConfig:
    """Mutable runtime config for EU AI Act toggle.

    - Art. 9: enables fundamental-rights impact step for high-risk contexts.
    - Art. 14: enables human-in-the-loop stop decisions.
    """

    eu_ai_act_mode: bool = False
    safety_threshold: float = 0.8


_RUNTIME_CONFIG = ComplianceRuntimeConfig()
_RUNTIME_LOCK = threading.RLock()


def get_runtime_config() -> Dict[str, Any]:
    """Return a thread-safe snapshot of runtime compliance config."""
    with _RUNTIME_LOCK:
        return asdict(_RUNTIME_CONFIG)


def update_runtime_config(*, eu_ai_act_mode: bool, safety_threshold: float) -> Dict[str, Any]:
    """Update runtime compliance config safely.

    Raises:
        ValueError: if the threshold is outside [0.0, 1.0].
    """
    threshold = float(safety_threshold)
    if threshold < 0.0 or threshold > 1.0:
        raise ValueError("safety_threshold must be between 0.0 and 1.0")

    with _RUNTIME_LOCK:
        _RUNTIME_CONFIG.eu_ai_act_mode = bool(eu_ai_act_mode)
        _RUNTIME_CONFIG.safety_threshold = threshold
        return asdict(_RUNTIME_CONFIG)


def resolve_dynamic_steps(payload: MutableMapping[str, Any]) -> List[str]:
    """Resolve pipeline steps dynamically based on EU mode.

    When EU mode is on, API orchestrator appends compliance steps:
    - Art. 9 Fundamental Rights Impact Assessment
    - Art. 14 Human-in-the-loop oversight check
    """
    steps = ["evidence", "debate", "critique", "safety"]
    config = get_runtime_config()
    if config["eu_ai_act_mode"]:
        steps.extend([
            "fundamental_rights_impact_assessment",  # Art. 9
            "human_in_the_loop",  # Art. 14
        ])
    payload["pipeline_steps"] = steps
    return steps


def enforce_compliance_stop(payload: MutableMapping[str, Any]) -> Dict[str, Any]:
    """Raise compliance stop if score is below configured threshold.

    - Art. 14 Human Oversight: low trust score must be routed to human review.
    """
    config = get_runtime_config()
    if not config["eu_ai_act_mode"]:
        return dict(payload)

    trust_score = float(payload.get("trust_score", 1.0))
    if trust_score < float(config["safety_threshold"]):
        pending_payload = dict(payload)
        pending_payload["status"] = "PENDING_REVIEW"
        pending_payload["compliance_reason"] = "art_14_human_review_required"
        raise ComplianceStopException(pending_payload)
    return dict(payload)
