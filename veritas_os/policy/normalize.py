"""Normalization routines that convert source policies into Canonical IR."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

from .ir import CanonicalExpression, CanonicalPolicyIR
from .models import SourcePolicy


def _dedupe_sorted(values: Iterable[str]) -> List[str]:
    return sorted({value.strip() for value in values if value and value.strip()})


def _normalize_expression(expr: Dict[str, Any]) -> CanonicalExpression:
    normalized_value = expr["value"]
    if isinstance(normalized_value, dict):
        normalized_value = {
            key: normalized_value[key]
            for key in sorted(normalized_value.keys())
        }
    return {
        "field": expr["field"].strip(),
        "operator": expr["operator"],
        "value": normalized_value,
    }


def _normalize_expression_list(values: List[Dict[str, Any]]) -> List[CanonicalExpression]:
    expressions = [_normalize_expression(value) for value in values]
    expressions.sort(
        key=lambda item: (
            item["field"],
            item["operator"],
            json.dumps(item["value"], sort_keys=True, separators=(",", ":")),
        )
    )
    return expressions


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _normalize_json_value(value[key])
            for key in sorted(value.keys())
        }
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    return value


def to_canonical_ir(policy: SourcePolicy) -> CanonicalPolicyIR:
    """Normalize a validated `SourcePolicy` into deterministic canonical IR."""
    policy_dict = policy.model_dump(mode="python")
    requirements = policy_dict["requirements"]

    test_vectors = sorted(
        policy_dict["test_vectors"],
        key=lambda item: (
            item["name"],
            json.dumps(item["input"], sort_keys=True, separators=(",", ":")),
            item["expected_outcome"],
        ),
    )

    return {
        "schema_version": policy_dict["schema_version"],
        "policy_id": policy_dict["policy_id"],
        "version": policy_dict["version"],
        "title": policy_dict["title"],
        "description": policy_dict["description"],
        "effective_date": policy_dict["effective_date"],
        "scope": {
            "domains": _dedupe_sorted(policy_dict["scope"]["domains"]),
            "routes": _dedupe_sorted(policy_dict["scope"]["routes"]),
            "actors": _dedupe_sorted(policy_dict["scope"]["actors"]),
        },
        "conditions": _normalize_expression_list(policy_dict["conditions"]),
        "requirements": {
            "required_evidence": _dedupe_sorted(requirements["required_evidence"]),
            "required_reviewers": _dedupe_sorted(requirements["required_reviewers"]),
            "minimum_approval_count": requirements["minimum_approval_count"],
        },
        "constraints": _normalize_expression_list(policy_dict["constraints"]),
        "outcome": {
            "decision": policy_dict["outcome"]["decision"],
            "reason": policy_dict["outcome"]["reason"],
        },
        "obligations": _dedupe_sorted(policy_dict["obligations"]),
        "test_vectors": test_vectors,
        "source_refs": _dedupe_sorted(policy_dict["source_refs"]),
        "metadata": _normalize_json_value(policy_dict["metadata"]),
    }
