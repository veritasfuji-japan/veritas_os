"""Canonical Policy IR types used for deterministic audit and hashing."""

from __future__ import annotations

from typing import Any, Dict, List, TypedDict


class CanonicalExpression(TypedDict):
    """Normalized expression tuple serialized as a stable mapping."""

    field: str
    operator: str
    value: Any


class CanonicalPolicyIR(TypedDict):
    """Canonical and deterministic policy representation."""

    schema_version: str
    policy_id: str
    version: str
    title: str
    description: str
    effective_date: str | None
    scope: Dict[str, List[str]]
    conditions: List[CanonicalExpression]
    requirements: Dict[str, Any]
    constraints: List[CanonicalExpression]
    outcome: Dict[str, str]
    obligations: List[str]
    test_vectors: List[Dict[str, Any]]
    source_refs: List[str]
    metadata: Dict[str, Any]
