"""Deterministic pytest test-case generation from policy test vectors."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .normalize import to_canonical_ir
from .schema import load_and_validate_policy


@dataclass(frozen=True)
class GeneratedPolicyTestCase:
    """Generated runtime test case derived from one policy test vector."""

    policy_file: str
    policy_id: str
    vector_name: str
    context: Dict[str, Any]
    expected_outcome: str


DEFAULT_POLICY_EXAMPLES_DIR = Path("policies/examples")


def _deep_merge(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(base)
    for key, value in updates.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _base_context_for_policy(canonical_ir: Dict[str, Any]) -> Dict[str, Any]:
    scope = canonical_ir["scope"]
    return {
        "domain": scope["domains"][0] if scope["domains"] else None,
        "route": scope["routes"][0] if scope["routes"] else None,
        "actor": scope["actors"][0] if scope["actors"] else None,
        "evidence": {
            "available": list(canonical_ir["requirements"].get("required_evidence", []))
        },
        "approvals": {
            "approved_by": list(
                canonical_ir["requirements"].get("required_reviewers", [])
            )
        },
        "runtime": {"auto_execute": False},
    }


def build_generated_test_cases(
    policy_files: Iterable[Path] | None = None,
) -> List[GeneratedPolicyTestCase]:
    """Build deterministic test cases from policy test_vectors."""
    files = sorted(
        policy_files if policy_files is not None else DEFAULT_POLICY_EXAMPLES_DIR.glob("*.yaml")
    )
    cases: List[GeneratedPolicyTestCase] = []
    for path in files:
        source_policy = load_and_validate_policy(path)
        canonical_ir = to_canonical_ir(source_policy)
        base_context = _base_context_for_policy(canonical_ir)

        for vector in canonical_ir["test_vectors"]:
            merged_context = _deep_merge(base_context, dict(vector["input"]))
            expected_outcome = vector["expected_outcome"]
            cases.append(
                GeneratedPolicyTestCase(
                    policy_file=path.as_posix(),
                    policy_id=canonical_ir["policy_id"],
                    vector_name=vector["name"],
                    context=merged_context,
                    expected_outcome=str(expected_outcome),
                )
            )

    cases.sort(key=lambda item: (item.policy_id, item.vector_name, item.policy_file))
    return cases
