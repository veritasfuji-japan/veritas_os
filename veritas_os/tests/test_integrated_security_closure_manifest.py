"""Drift guards for the integrated F-01 through F-08 security closure gate."""

from __future__ import annotations

from pathlib import Path

from scripts.security.run_integrated_security_closure import (
    EXPECTED_FINDINGS,
    MANIFEST_PATH,
    load_manifest,
    regression_targets,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_manifest_covers_each_security_finding_without_gaps() -> None:
    manifest = load_manifest()

    assert set(manifest["findings"]) == EXPECTED_FINDINGS
    assert all(manifest["findings"][finding] for finding in EXPECTED_FINDINGS)


def test_manifest_preserves_execution_boundary_regressions() -> None:
    manifest = load_manifest()

    assert set(manifest["preserved_boundary_targets"]) == {
        "veritas_os/tests/test_native_bind_authorization_consumption.py",
        "veritas_os/tests/test_sandbox_bind_execution.py",
        "veritas_os/tests/test_controlled_execution_proof_architecture_freeze.py",
    }
    assert {
        "native_v2_authorization_is_single_use",
        "effect_unknown_prohibits_blind_redispatch",
        "controlled_execution_proof_scope_remains_frozen",
    }.issubset(set(manifest["preserved_invariants"]))


def test_manifest_keeps_security_closure_non_claims_explicit() -> None:
    manifest = load_manifest()

    assert set(manifest["explicit_non_claims"]) == {
        "production_readiness",
        "production_security_certification",
        "dependency_advisories_resolved",
        "real_customer_credentials_or_endpoints",
        "independent_production_infrastructure",
        "production_decision_to_effect_e2e_proven",
    }


def test_security_gates_workflow_runs_manifest_backed_closure_runner() -> None:
    workflow = (
        REPO_ROOT / ".github" / "workflows" / "security-gates.yml"
    ).read_text(encoding="utf-8")

    assert "Integrated Security Closure (F-01-F-08)" in workflow
    assert "python scripts/security/run_integrated_security_closure.py" in workflow
    assert MANIFEST_PATH.is_file()
    assert len(regression_targets(load_manifest())) == 11
