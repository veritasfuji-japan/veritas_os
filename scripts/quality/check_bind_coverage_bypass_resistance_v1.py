#!/usr/bin/env python3
"""Export and check the frozen V1 executable effect-boundary inventory."""

from __future__ import annotations

import ast
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from veritas_os.policy.bind_coverage_registry import (
    load_bind_coverage_registry,
    validate_bind_coverage_registry,
)
from veritas_os.policy.bind_execution_capability import PROOF_SCOPE


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "artifacts" / "bind-coverage-bypass-resistance-v1"
POLICY_ROOT = ROOT / "veritas_os" / "policy"
DECLARED_EFFECT_CANDIDATES = {
    ("veritas_os/policy/bundle.py", "archive_path.open"): "local_file_io",
    ("veritas_os/policy/bundle.py", "open"): "local_file_io",
    ("veritas_os/policy/bundle.py", "tarfile.open"): "local_file_io",
    (
        "veritas_os/policy/sandbox_event_service.py",
        "app.post",
    ): "route_registration_not_dispatch",
    (
        "veritas_os/policy/sandbox_reconciliation.py",
        "asyncio.open_connection",
    ): "auxiliary_reconciliation_read_outside_v1",
    (
        "veritas_os/policy/sandbox_reconciliation.py",
        "writer.write",
    ): "auxiliary_reconciliation_read_outside_v1",
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "asyncio.open_connection",
    ): "native_v2_sandbox_action",
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "writer.write",
    ): "native_v2_sandbox_action",
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "opener.open",
    ): "registered_webhook_action_or_compensation",
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "transport.request",
    ): "registered_webhook_dispatch_to_exact_sink",
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "self._delegate.request",
    ): "controlled_test_delegate_below_exact_sink",
}
_EFFECT_CALL_NAMES = {
    "open",
    "open_connection",
    "post",
    "request",
    "send",
    "sendall",
    "urlopen",
    "write",
}
MATRIX_CASES = (
    "direct adapter invocation", "direct helper invocation",
    "direct transport invocation", "fake Permit", "reconstructed Permit",
    "serialized Permit", "Permit replay", "concurrent Permit use",
    "leaked consumed Permit", "wrong operation", "wrong resource",
    "changed credential identity", "stale/expired authorization",
    "consumed authorization", "alternate adapter", "unregistered subclass",
    "wrapper/proxy", "alternate factory implementation", "duplicate coverage",
    "ambiguous coverage", "registry/runtime mismatch", "undeclared effect sink",
    "ACTION Permit used for COMPENSATION", "direct COMPENSATION Permit mint",
    "fake CompensationEligibilityGrant", "reconstructed Grant", "Grant replay",
    "concurrent Grant consumption", "cross-ACTION Grant reuse",
    "compensation endpoint mutation", "compensation payload mutation",
    "recovery ACTION remint attempt", "recovery Grant fabrication",
    "valid P2/H(P2) against Permit(P1)", "post-validation P1-to-P2 TOCTOU attempt",
    "exact outbound representation equality", "legitimate ACTION",
    "legitimate COMPENSATION",
)

MATRIX_CASE_TO_PYTEST_NODE = {
    "direct adapter invocation": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_direct_webhook_adapter_invocation_has_zero_external_post",
    "direct helper invocation": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_direct_webhook_helper_invocation_has_zero_external_post",
    "direct transport invocation": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_direct_webhook_transport_invocation_has_zero_external_post",
    "fake Permit": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_fake_permit_is_rejected",
    "reconstructed Permit": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_reconstructed_permit_is_rejected",
    "serialized Permit": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_serialized_permit_is_rejected",
    "Permit replay": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_permit_replay_is_rejected",
    "concurrent Permit use": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_permit_atomic_consumption_has_exactly_one_winner",
    "leaked consumed Permit": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_leaked_consumed_permit_reference_is_rejected",
    "wrong operation": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_exact_binding_mutation_is_rejected[wrong-operation]",
    "wrong resource": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_exact_binding_mutation_is_rejected[wrong-resource]",
    "changed credential identity": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_exact_binding_mutation_is_rejected[changed-credential-identity]",
    "stale/expired authorization": "veritas_os/tests/test_live_adapter_bind_authorization_consumption.py::test_expired_authorization_fails_before_consumption",
    "consumed authorization": "veritas_os/tests/test_live_adapter_bind_authorization_consumption.py::test_failure_after_consumption_never_releases_authorization",
    "alternate adapter": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_alternate_adapter_is_rejected",
    "unregistered subclass": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_unregistered_subclass_is_rejected",
    "wrapper/proxy": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_wrapper_proxy_is_rejected",
    "alternate factory implementation": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_alternate_factory_implementation_is_rejected",
    "duplicate coverage": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_duplicate_coverage_is_rejected",
    "ambiguous coverage": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_ambiguous_coverage_is_rejected",
    "registry/runtime mismatch": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_registry_runtime_mismatch_is_rejected",
    "undeclared effect sink": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_undeclared_effect_sink_breaks_exact_inventory_equality",
    "ACTION Permit used for COMPENSATION": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_action_permit_cannot_authorize_compensation",
    "direct COMPENSATION Permit mint": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_direct_compensation_permit_mint_is_rejected",
    "fake CompensationEligibilityGrant": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_fake_compensation_grant_is_rejected",
    "reconstructed Grant": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_reconstructed_compensation_grant_is_rejected",
    "Grant replay": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_grant_replay_is_rejected",
    "concurrent Grant consumption": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_concurrent_grant_consumption_has_exactly_one_winner",
    "cross-ACTION Grant reuse": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_cross_action_grant_reuse_is_rejected",
    "compensation endpoint mutation": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_compensation_endpoint_mutation_is_rejected",
    "compensation payload mutation": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_compensation_payload_mutation_is_rejected",
    "recovery ACTION remint attempt": "veritas_os/tests/test_sandbox_recovery.py::test_pre_dispatch_crash_closes_no_effect_without_reader_or_resend",
    "recovery Grant fabrication": "veritas_os/tests/test_sandbox_recovery.py::test_lookup_absence_remains_unknown_and_never_posts",
    "valid P2/H(P2) against Permit(P1)": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_valid_p2_cannot_replace_frozen_p1",
    "post-validation P1-to-P2 TOCTOU attempt": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_post_validation_toctou_dispatches_frozen_p1",
    "exact outbound representation equality": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_legitimate_webhook_action_sends_exact_frozen_bytes",
    "legitimate ACTION": "veritas_os/tests/test_sandbox_https_transport.py::test_single_exact_post_and_observations[201-HTTP_201_MATCHING_ACK]",
    "legitimate COMPENSATION": "tests/policy/test_bind_coverage_bypass_resistance_v1.py::test_bind_core_transition_mints_exactly_one_compensation",
}


def _call_name(node: ast.Call) -> str:
    parts: list[str] = []
    current = node.func
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def discover(root: Path = POLICY_ROOT) -> list[dict[str, object]]:
    """Discover effect-shaped calls across the complete policy package."""
    found: list[dict[str, object]] = []
    for source in sorted(root.rglob("*.py")):
        try:
            relative = str(source.relative_to(ROOT))
        except ValueError:
            relative = str(source.relative_to(root.parent))
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name.rsplit(".", 1)[-1] in _EFFECT_CALL_NAMES:
                found.append({"path": relative, "primitive": name, "line": node.lineno})
    return sorted(found, key=lambda item: (str(item["path"]), int(item["line"])))


def _write(name: str, value: object) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / name).write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def run_mandatory_matrix() -> int:
    """Execute every mapped node and retain per-case execution results."""
    results: list[dict[str, object]] = []
    passed = True
    positive_cases = {
        "exact outbound representation equality",
        "legitimate ACTION",
        "legitimate COMPENSATION",
    }
    for case_name in MATRIX_CASES:
        node = MATRIX_CASE_TO_PYTEST_NODE[case_name]
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", node],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        status = "PASS" if completed.returncode == 0 else "FAIL"
        passed = passed and completed.returncode == 0
        if completed.returncode != 0:
            sys.stderr.write(completed.stdout)
            sys.stderr.write(completed.stderr)
        negative = case_name not in positive_cases
        results.append(
            {
                "case_name": case_name,
                "pytest_node": node,
                "executed": True,
                "status": status,
                "expected_outcome": (
                    "LEGITIMATE_EFFECT" if not negative else "REJECTED_FAIL_CLOSED"
                ),
                "zero_effect_evidence": (
                    "asserted_by_behavioral_test" if negative else "not_applicable"
                ),
            }
        )
    matrix_payload = {
            "proof_scope": PROOF_SCOPE,
            "executed_case_count": len(results),
            "passed_case_count": sum(row["status"] == "PASS" for row in results),
            "all_mapped_cases_executed": len(results) == len(MATRIX_CASES),
            "cases": results,
        }
    _write("adversarial-matrix.json", matrix_payload)
    report_path = OUTPUT / "proof-report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        matrix_bytes = json.dumps(
            matrix_payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        report.update(
            adversarial_matrix_digest=hashlib.sha256(matrix_bytes).hexdigest(),
            adversarial_matrix_executed=len(results) == len(MATRIX_CASES),
            adversarial_matrix_passed=passed,
        )
        _write("proof-report.json", report)
    return 0 if passed and len(results) == len(MATRIX_CASES) else 1


def main() -> int:
    entries = [
        entry for entry in load_bind_coverage_registry()
        if entry.proof_scope == PROOF_SCOPE
    ]
    validation = validate_bind_coverage_registry(load_bind_coverage_registry())
    discovered = discover()
    discovered_set = {(str(row["path"]), str(row["primitive"])) for row in discovered}
    declared_set = set(DECLARED_EFFECT_CANDIDATES)
    registered_boundaries = {
        (entry.effect_boundary_id, entry.dispatch_kind) for entry in entries
    }
    expected_boundaries = {
        ("registered-webhook-action", "ACTION"),
        ("registered-webhook-compensation", "COMPENSATION"),
        ("native-v2-sandbox-action", "ACTION"),
    }
    passed = (
        validation.valid
        and discovered_set == declared_set
        and registered_boundaries == expected_boundaries
        and len(entries) == 3
    )
    registry_payload = [entry.__dict__ for entry in entries]
    registry_bytes = json.dumps(
        registry_payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    tested_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    provenance = {
        "proof_scope": PROOF_SCOPE,
        "tested_sha": tested_sha,
        "source_sha": os.environ.get("GITHUB_SHA", tested_sha),
        "registry_digest": hashlib.sha256(registry_bytes).hexdigest(),
        "architecture_status": "FROZEN",
        "implementation_status": "IMPLEMENTED",
        "proof_status": "NOT_PROVEN",
    }
    _write("execution-boundary-inventory.json", [
        {
            **row,
            "classification": DECLARED_EFFECT_CANDIDATES.get(
                (str(row["path"]), str(row["primitive"])), "UNDECLARED"
            ),
        }
        for row in discovered
    ])
    _write("bind-coverage-registry.json", registry_payload)
    if set(MATRIX_CASE_TO_PYTEST_NODE) != set(MATRIX_CASES):
        raise RuntimeError("mandatory matrix mapping is incomplete")
    if len(set(MATRIX_CASE_TO_PYTEST_NODE.values())) != len(MATRIX_CASES):
        raise RuntimeError("mandatory matrix nodes must be unique")
    _write("adversarial-matrix.json", {
        "cases": [
            {
                "name": name,
                "required": True,
                "pytest_node": MATRIX_CASE_TO_PYTEST_NODE[name],
            }
            for name in MATRIX_CASES
        ],
        "result_source": "each pytest node performs the named behavior",
    })
    _write("near-miss.json", {
        "undeclared_candidates": sorted(discovered_set - declared_set),
        "missing_declared_candidates": sorted(declared_set - discovered_set),
    })
    _write("immutable-dispatch-evidence.json", {
        "representation": "ImmutableFinalDispatch", "proof_status": "NOT_PROVEN"
    })
    _write("compensation-authority-evidence.json", {
        "authority": "CompensationEligibilityGrant", "proof_status": "NOT_PROVEN"
    })
    _write("provenance.json", provenance)
    _write("proof-report.json", {
        **provenance,
        "inventory_set_equality": discovered_set == declared_set,
        "registry_set_equality": registered_boundaries == expected_boundaries,
        "result": "PASS" if passed else "FAIL",
        "explicit_non_claims": [
            "all VERITAS external I/O is Bind-governed",
            "arbitrary equivalent-privilege in-process compromise resistance",
            "TLS/provider identity proof",
            "universal exactly-once external delivery",
            "production readiness",
        ],
    })
    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-matrix", action="store_true")
    arguments = parser.parse_args()
    raise SystemExit(run_mandatory_matrix() if arguments.run_matrix else main())
