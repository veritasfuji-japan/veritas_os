"""
Pydantic schema for the Debate safety policy YAML format.

This module is the single source of truth for the debate_safety_policy YAML
structure. It is Phase 1 schema-definition only and is NOT wired into any
runtime enforcement path. Production loading (Phase 3+) must use
DebateSafetyPolicy.model_validate() before any enforcement switch.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

import pydantic


class PolicyMode(str, Enum):
    example_only = "example_only"
    shadow = "shadow"
    enforced = "enforced"


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class PolicyAction(str, Enum):
    review = "review"
    escalate_or_block = "escalate_or_block"
    block = "block"


class PatternCategory(pydantic.BaseModel):
    severity: Severity
    action: PolicyAction
    patterns: Annotated[
        list[Annotated[str, pydantic.StringConstraints(min_length=1)]],
        pydantic.Field(min_length=1),
    ]


class DebateSafetyPolicy(pydantic.BaseModel):
    schema_version: int
    policy_id: str
    mode: PolicyMode
    notes: list[str] = pydantic.Field(default_factory=list)
    categories: Annotated[
        dict[str, PatternCategory],
        pydantic.Field(min_length=1),
    ]

    model_config = pydantic.ConfigDict(extra="forbid")
