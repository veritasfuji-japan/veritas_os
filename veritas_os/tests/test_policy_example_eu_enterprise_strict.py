from __future__ import annotations

from pathlib import Path

from veritas_os.policy.compiler import compile_policy_to_bundle
from veritas_os.policy.evaluator import evaluate_runtime_policies
from veritas_os.policy.generated_tests import build_generated_test_cases
from veritas_os.policy.runtime_adapter import load_runtime_bundle
from veritas_os.policy.schema import load_and_validate_policy


EXAMPLE_PATH = Path("policies/examples/eu_ai_act_enterprise_strict.yaml")


def test_eu_strict_policy_example_loads_and_validates() -> None:
    policy = load_and_validate_policy(EXAMPLE_PATH)
    assert policy.policy_id == "policy.eu_ai_act.enterprise_strict"


def test_eu_strict_policy_example_compiles_and_runs(tmp_path: Path) -> None:
    compiled = compile_policy_to_bundle(
        EXAMPLE_PATH,
        tmp_path,
        compiled_at="2026-04-06T00:00:00Z",
    )
    runtime_bundle = load_runtime_bundle(compiled.bundle_dir)

    context = {
        "domain": "governance",
        "route": "/v1/decide",
        "actor": "fuji",
        "risk": {"level": "critical"},
        "request": {"sensitive_domain": "medical"},
        "runtime": {"auto_execute": False},
        "evidence": {
            "available": [
                "risk_assessment",
                "impact_assessment",
                "human_oversight_plan",
            ]
        },
        "approvals": {"approved_by": ["governance_officer", "legal_reviewer"]},
    }
    decision = evaluate_runtime_policies(runtime_bundle, context).to_dict()

    assert decision["final_outcome"] == "require_human_review"


def test_generated_test_cases_include_eu_strict_example() -> None:
    cases = build_generated_test_cases()
    assert any(case.policy_id == "policy.eu_ai_act.enterprise_strict" for case in cases)
