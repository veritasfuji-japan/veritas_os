"""Strict source policy schema for Policy-as-Code authoring."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SCHEMA_VERSION = "1.0"


class PolicyValidationError(ValueError):
    """Raised when a source policy fails strict validation."""


class PolicyCompilationError(RuntimeError):
    """Raised when a compilation I/O or artifact error occurs."""


class OutcomeAction(str, Enum):
    """Allowed policy outcomes for governance decisions."""

    ALLOW = "allow"
    DENY = "deny"
    HALT = "halt"
    ESCALATE = "escalate"
    REQUIRE_HUMAN_REVIEW = "require_human_review"


class Expression(BaseModel):
    """A simple condition or constraint expression."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str = Field(min_length=1, max_length=120)
    operator: Literal[
        "eq",
        "neq",
        "in",
        "not_in",
        "gt",
        "gte",
        "lt",
        "lte",
        "contains",
        "regex",
    ]
    value: Any

    @field_validator("field")
    @classmethod
    def _normalize_field(cls, value: str) -> str:
        return value.strip()


class PolicyScope(BaseModel):
    """Scope selectors describing where this policy applies."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    domains: List[str] = Field(min_length=1)
    routes: List[str] = Field(min_length=1)
    actors: List[str] = Field(min_length=1)

    @field_validator("domains", "routes", "actors", mode="before")
    @classmethod
    def _ensure_list(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("domains", "routes", "actors")
    @classmethod
    def _strip_and_validate_items(cls, values: List[str]) -> List[str]:
        cleaned = [item.strip() for item in values if item and item.strip()]
        if not cleaned:
            raise ValueError("scope list must include at least one value")
        return cleaned


class PolicyRequirements(BaseModel):
    """Evidence and approval requirements enforced by a policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    required_evidence: List[str] = Field(default_factory=list)
    required_reviewers: List[str] = Field(default_factory=list)
    minimum_approval_count: int = Field(default=0, ge=0, le=20)

    @field_validator("required_evidence", "required_reviewers", mode="before")
    @classmethod
    def _ensure_list(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("required_evidence", "required_reviewers")
    @classmethod
    def _normalize_items(cls, values: List[str]) -> List[str]:
        return [item.strip() for item in values if item and item.strip()]

    @model_validator(mode="after")
    def _approval_consistency(self) -> "PolicyRequirements":
        if self.minimum_approval_count > len(set(self.required_reviewers)):
            raise ValueError(
                "minimum_approval_count cannot exceed number of "
                "required_reviewers"
            )
        return self


class PolicyOutcome(BaseModel):
    """Policy decision outcome with optional rationale metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: OutcomeAction
    reason: str = Field(default="", max_length=2000)

    @field_validator("reason")
    @classmethod
    def _normalize_reason(cls, value: str) -> str:
        return value.strip()


class PolicyExample(BaseModel):
    """Test vector that documents expected policy behavior."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=200)
    input: Dict[str, Any] = Field(default_factory=dict)
    expected_outcome: OutcomeAction

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        return value.strip()


class SourcePolicy(BaseModel):
    """Human-authored source policy schema."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(default=SCHEMA_VERSION)
    policy_id: str = Field(min_length=3, max_length=120)
    version: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    effective_date: str | None = Field(default=None)
    scope: PolicyScope
    conditions: List[Expression] = Field(default_factory=list)
    requirements: PolicyRequirements = Field(default_factory=PolicyRequirements)
    constraints: List[Expression] = Field(default_factory=list)
    outcome: PolicyOutcome
    obligations: List[str] = Field(default_factory=list)
    test_vectors: List[PolicyExample] = Field(default_factory=list)
    source_refs: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("policy_id", "version", "title", "description")
    @classmethod
    def _normalize_string_fields(cls, value: str) -> str:
        return value.strip()

    @field_validator("obligations", mode="before")
    @classmethod
    def _ensure_obligations_list(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("source_refs", mode="before")
    @classmethod
    def _ensure_source_refs_list(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("source_refs")
    @classmethod
    def _normalize_source_refs(cls, values: List[str]) -> List[str]:
        return [item.strip() for item in values if item and item.strip()]

    @field_validator("effective_date")
    @classmethod
    def _validate_effective_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        date.fromisoformat(normalized)
        return normalized

    @field_validator("metadata")
    @classmethod
    def _ensure_metadata_mapping(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("metadata must be an object")
        return value

    @field_validator("obligations")
    @classmethod
    def _normalize_obligations(cls, values: List[str]) -> List[str]:
        return [item.strip() for item in values if item and item.strip()]

    @model_validator(mode="after")
    def _validate_schema_version(self) -> "SourcePolicy":
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported schema_version={self.schema_version}; "
                f"expected {SCHEMA_VERSION}"
            )
        return self
