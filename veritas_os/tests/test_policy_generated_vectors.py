from __future__ import annotations

from pathlib import Path

import pytest

from veritas_os.policy.compiler import compile_policy_to_bundle
from veritas_os.policy.evaluator import evaluate_runtime_policies
from veritas_os.policy.generated_tests import build_generated_test_cases
from veritas_os.policy.runtime_adapter import load_runtime_bundle


@pytest.mark.parametrize(
    "case",
    build_generated_test_cases(),
    ids=lambda case: f"{case.policy_id}:{case.vector_name}",
)
def test_generated_policy_vectors_match_expected_outcome(
    tmp_path: Path,
    case,
) -> None:
    result = compile_policy_to_bundle(
        case.policy_file,
        tmp_path,
        compiled_at="2026-03-28T00:00:00Z",
    )
    runtime_bundle = load_runtime_bundle(result.bundle_dir)
    decision = evaluate_runtime_policies(runtime_bundle, case.context).to_dict()

    assert decision["final_outcome"] == case.expected_outcome


def test_generated_policy_vectors_are_deterministic() -> None:
    first = build_generated_test_cases()
    second = build_generated_test_cases()

    assert first == second
