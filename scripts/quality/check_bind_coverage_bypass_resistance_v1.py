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
import tempfile

from veritas_os.policy.bind_coverage_registry import (
    load_bind_coverage_registry,
    validate_bind_coverage_registry,
)
from veritas_os.policy.bind_execution_capability import PROOF_SCOPE


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "artifacts" / "bind-coverage-bypass-resistance-v1"
POLICY_ROOT = ROOT / "veritas_os" / "policy"
DECLARED_EFFECT_SINKS = {
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
    (
        "veritas_os/policy/trusted_https_reconciliation.py",
        "httpx.AsyncClient.get",
    ): "auxiliary_read_only_network",
}

# An import is evidence that the module can acquire the capability.  It is not
# a claim that every use is Bind-governed or that importing it performs I/O.
DECLARED_EFFECT_CAPABILITIES = {
    (
        "veritas_os/policy/bind_effect_reconciliation.py",
        "asyncio",
    ): "outside_v1_but_declared",
    (
        "veritas_os/policy/bind_execution_capability.py",
        "asyncio",
    ): "outside_v1_but_declared",
    (
        "veritas_os/policy/debate_safety_policy_runtime_shadow.py",
        "os",
    ): "process_launch_capable_but_not_used",
    (
        "veritas_os/policy/live_adapter_bind_authorization_consumption_store.py",
        "asyncio",
    ): "outside_v1_but_declared",
    (
        "veritas_os/policy/runtime_adapter.py",
        "os",
    ): "process_launch_capable_but_not_used",
    (
        "veritas_os/policy/sandbox_bind_execution.py",
        "asyncio",
    ): "outside_v1_but_declared",
    (
        "veritas_os/policy/sandbox_credential_resolution.py",
        "asyncio",
    ): "outside_v1_but_declared",
    (
        "veritas_os/policy/sandbox_https_transport.py",
        "asyncio",
    ): "governed_v1_effect_transport",
    (
        "veritas_os/policy/sandbox_receipt_outcome.py",
        "asyncio",
    ): "outside_v1_but_declared",
    (
        "veritas_os/policy/sandbox_reconciliation.py",
        "asyncio",
    ): "auxiliary_read_only_network",
    ("veritas_os/policy/sandbox_recovery.py", "asyncio"): "outside_v1_but_declared",
    (
        "veritas_os/policy/trusted_https_reconciliation.py",
        "httpx",
    ): "auxiliary_read_only_network",
    ("veritas_os/policy/webhook_bind_adapter.py", "socket"): "auxiliary_dns_resolution",
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "urllib.request.HTTPRedirectHandler",
    ): "governed_v1_effect_transport",
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "urllib.request.Request",
    ): "governed_v1_effect_transport",
    (
        "veritas_os/policy/webhook_bind_adapter.py",
        "urllib.request.build_opener",
    ): "governed_v1_effect_transport",
}

# Compatibility name for callers of the historical one-inventory interface.
DECLARED_EFFECT_CANDIDATES = DECLARED_EFFECT_SINKS

_CAPABILITY_MODULES = {
    "aiohttp",
    "asyncio",
    "http.client",
    "httpx",
    "os",
    "requests",
    "socket",
    "subprocess",
    "urllib.request",
}
_NETWORK_METHODS = {
    "connect",
    "connect_ex",
    "create_connection",
    "create_server",
    "delete",
    "get",
    "open",
    "open_connection",
    "patch",
    "post",
    "put",
    "request",
    "send",
    "sendall",
    "sendto",
    "start_server",
    "stream",
    "urlopen",
}
_PROCESS_METHODS = {
    "Popen",
    "call",
    "check_call",
    "check_output",
    "popen",
    "run",
    "system",
}
_PRESERVED_SINKS = {
    "app.post",
    "archive_path.open",
    "open",
    "opener.open",
    "self._delegate.request",
    "tarfile.open",
    "transport.request",
    "writer.write",
}
MATRIX_CASES = (
    "direct adapter invocation",
    "direct helper invocation",
    "direct transport invocation",
    "fake Permit",
    "reconstructed Permit",
    "serialized Permit",
    "Permit replay",
    "concurrent Permit use",
    "leaked consumed Permit",
    "wrong operation",
    "wrong resource",
    "changed credential identity",
    "stale/expired authorization",
    "consumed authorization",
    "alternate adapter",
    "unregistered subclass",
    "wrapper/proxy",
    "alternate factory implementation",
    "duplicate coverage",
    "ambiguous coverage",
    "registry/runtime mismatch",
    "undeclared effect sink",
    "ACTION Permit used for COMPENSATION",
    "direct COMPENSATION Permit mint",
    "fake CompensationEligibilityGrant",
    "reconstructed Grant",
    "Grant replay",
    "concurrent Grant consumption",
    "cross-ACTION Grant reuse",
    "compensation endpoint mutation",
    "compensation payload mutation",
    "recovery ACTION remint attempt",
    "recovery Grant fabrication",
    "valid P2/H(P2) against Permit(P1)",
    "post-validation P1-to-P2 TOCTOU attempt",
    "exact outbound representation equality",
    "legitimate ACTION",
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


def _expression_name(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        return _expression_name(node.func)
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _canonical_name(name: str, aliases: dict[str, str]) -> str:
    head, separator, tail = name.partition(".")
    canonical = aliases.get(head, head)
    return canonical + (separator + tail if separator else "")


def _is_capability_import(name: str) -> bool:
    return any(
        name == family or name.startswith(f"{family}.")
        for family in _CAPABILITY_MODULES
    )


def _is_effect_sink(name: str) -> bool:
    if name in _PRESERVED_SINKS:
        return True
    head, _, tail = name.partition(".")
    terminal = name.rsplit(".", 1)[-1]
    if head == "socket":
        return terminal in _NETWORK_METHODS or name == "socket.socket"
    if head in {"aiohttp", "httpx", "requests", "urllib"}:
        return terminal in _NETWORK_METHODS
    if name.startswith("http.client.") or name.startswith("asyncio."):
        return terminal in _NETWORK_METHODS
    if head == "subprocess":
        return terminal in _PROCESS_METHODS
    if head == "os":
        return terminal in _PROCESS_METHODS or terminal.startswith(("exec", "spawn"))
    return False


class _EffectVisitor(ast.NodeVisitor):
    """Resolve effect-family imports, aliases, and simple client instances."""

    def __init__(self, relative: str) -> None:
        self.relative = relative
        self.aliases: dict[str, str] = {}
        self.instances: dict[str, str] = {}
        self.capabilities: list[dict[str, object]] = []
        self.sinks: list[dict[str, object]] = []

    def _add_capability(self, identity: str, line: int) -> None:
        self.capabilities.append(
            {
                "path": self.relative,
                "capability": identity,
                "line": line,
            }
        )

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for imported in node.names:
            local = imported.asname or imported.name.split(".", 1)[0]
            self.aliases[local] = (
                imported.name if imported.asname else imported.name.split(".", 1)[0]
            )
            if _is_capability_import(imported.name):
                self._add_capability(imported.name, node.lineno)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if node.module is None:
            return
        for imported in node.names:
            identity = f"{node.module}.{imported.name}"
            self.aliases[imported.asname or imported.name] = identity
            if _is_capability_import(identity):
                self._add_capability(identity, node.lineno)

    def _record_instance(self, target: ast.AST, value: ast.AST) -> None:
        if not isinstance(target, ast.Name):
            return
        expression = value.func if isinstance(value, ast.Call) else value
        canonical = _canonical_name(_expression_name(expression), self.aliases)
        if canonical.endswith((".get_event_loop", ".get_running_loop")):
            self.instances[target.id] = "asyncio.loop"
        elif canonical == "socket.socket" or canonical.endswith(
            (
                ".Client",
                ".AsyncClient",
                ".ClientSession",
                ".HTTPConnection",
                ".HTTPSConnection",
                ".Session",
            )
        ):
            self.instances[target.id] = canonical

    def _record_dynamic_import(self, target: ast.AST, value: ast.AST) -> None:
        if not isinstance(target, ast.Name) or not isinstance(value, ast.Call):
            return
        canonical = _canonical_name(_expression_name(value.func), self.aliases)
        if canonical not in {"__import__", "importlib.import_module"} or not value.args:
            return
        argument = value.args[0]
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            if _is_capability_import(argument.value):
                self.aliases[target.id] = argument.value

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        for target in node.targets:
            self._record_instance(target, node.value)
            self._record_dynamic_import(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        if node.value is not None:
            self._record_instance(node.target, node.value)
            self._record_dynamic_import(node.target, node.value)
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:  # noqa: N802
        for item in node.items:
            if item.optional_vars is not None:
                self._record_instance(item.optional_vars, item.context_expr)
        self.generic_visit(node)

    visit_AsyncWith = visit_With

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        raw = _expression_name(node.func)
        canonical = _canonical_name(raw, self.aliases)
        head, separator, tail = canonical.partition(".")
        if head in self.instances:
            canonical = self.instances[head] + (separator + tail if separator else "")
        if canonical in {"__import__", "importlib.import_module"} and node.args:
            argument = node.args[0]
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                if _is_capability_import(argument.value):
                    self._add_capability(argument.value, node.lineno)
        if _is_effect_sink(canonical) or raw in _PRESERVED_SINKS:
            self.sinks.append(
                {
                    "path": self.relative,
                    "primitive": canonical,
                    "line": node.lineno,
                }
            )
        self.generic_visit(node)


def discover_inventories(
    root: Path = POLICY_ROOT,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Discover canonical capability imports and effect sinks package-wide.

    This deliberately bounded static analysis resolves direct import aliases and
    simple assigned client/socket objects.  It is not whole-program Python
    soundness and does not resolve reflective or data-dependent dispatch.
    """
    capabilities: list[dict[str, object]] = []
    sinks: list[dict[str, object]] = []
    for source in sorted(root.rglob("*.py")):
        try:
            relative = str(source.relative_to(ROOT))
        except ValueError:
            relative = str(source.relative_to(root.parent))
        tree = ast.parse(source.read_text(encoding="utf-8"))
        visitor = _EffectVisitor(relative)
        visitor.visit(tree)
        capabilities.extend(visitor.capabilities)
        sinks.extend(visitor.sinks)

    def key(item: dict[str, object]) -> tuple[str, int]:
        return str(item["path"]), int(item["line"])

    return sorted(capabilities, key=key), sorted(sinks, key=key)


def discover(root: Path = POLICY_ROOT) -> list[dict[str, object]]:
    """Return the sink inventory through the historical scanner interface."""
    return discover_inventories(root)[1]


def _write(name: str, value: object) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / name).write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def run_static_inventory_regressions() -> tuple[bool, list[dict[str, object]]]:
    """Prove representative undeclared capabilities fail both inventories."""
    fixtures = {
        "raw_socket_create_connection": (
            "raw_socket.py",
            "import socket\nsocket.create_connection(('example.com', 443))\n",
        ),
        "imported_alias": (
            "imported_alias.py",
            "from socket import create_connection as connect_external\n"
            "connect_external(('example.com', 443))\n",
        ),
        "module_alias": (
            "module_alias.py",
            "import socket as sock\nsock.create_connection(('example.com', 443))\n",
        ),
        "automatic_new_module": (
            "unlisted_transport.py",
            "import socket\nsocket.create_connection(('example.com', 443))\n",
        ),
    }
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory() as directory:
        policy_root = Path(directory) / "veritas_os" / "policy"
        policy_root.mkdir(parents=True)
        for name, (filename, source) in fixtures.items():
            for old_source in policy_root.glob("*.py"):
                old_source.unlink()
            (policy_root / filename).write_text(source, encoding="utf-8")
            capabilities, sinks = discover_inventories(policy_root)
            capability_set = {
                (str(row["path"]), str(row["capability"])) for row in capabilities
            }
            sink_set = {(str(row["path"]), str(row["primitive"])) for row in sinks}
            canonical_sink_found = any(
                primitive == "socket.create_connection" for _, primitive in sink_set
            )
            rejected = capability_set != set(
                DECLARED_EFFECT_CAPABILITIES
            ) and sink_set != set(DECLARED_EFFECT_SINKS)
            passed = canonical_sink_found and rejected
            results.append(
                {
                    "name": name,
                    "passed": passed,
                    "capabilities": capabilities,
                    "sinks": sinks,
                    "inventory_equality": False if rejected else True,
                    "automatic_package_scan": name == "automatic_new_module",
                }
            )
    return all(bool(row["passed"]) for row in results), results


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
        entry
        for entry in load_bind_coverage_registry()
        if entry.proof_scope == PROOF_SCOPE
    ]
    validation = validate_bind_coverage_registry(load_bind_coverage_registry())
    discovered_capabilities, discovered_sinks = discover_inventories()
    discovered_capability_set = {
        (str(row["path"]), str(row["capability"])) for row in discovered_capabilities
    }
    discovered_sink_set = {
        (str(row["path"]), str(row["primitive"])) for row in discovered_sinks
    }
    declared_capability_set = set(DECLARED_EFFECT_CAPABILITIES)
    declared_sink_set = set(DECLARED_EFFECT_SINKS)
    regressions_passed, regression_results = run_static_inventory_regressions()
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
        and discovered_capability_set == declared_capability_set
        and discovered_sink_set == declared_sink_set
        and regressions_passed
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
    effect_sink_inventory = [
        {
            **row,
            "classification": DECLARED_EFFECT_SINKS.get(
                (str(row["path"]), str(row["primitive"])), "UNDECLARED"
            ),
        }
        for row in discovered_sinks
    ]
    effect_capability_inventory = [
        {
            **row,
            "classification": DECLARED_EFFECT_CAPABILITIES.get(
                (str(row["path"]), str(row["capability"])), "UNDECLARED"
            ),
        }
        for row in discovered_capabilities
    ]
    # Retain the historical artifact name while making the separate sink
    # inventory explicit for this closure.
    _write("execution-boundary-inventory.json", effect_sink_inventory)
    _write("effect-capability-inventory.json", effect_capability_inventory)
    _write("effect-sink-inventory.json", effect_sink_inventory)
    _write(
        "static-inventory-regressions.json",
        {
            "passed": regressions_passed,
            "cases": regression_results,
            "limitation": (
                "bounded AST analysis; reflective and data-dependent dispatch are "
                "outside the reviewed static threat model"
            ),
        },
    )
    _write("bind-coverage-registry.json", registry_payload)
    if set(MATRIX_CASE_TO_PYTEST_NODE) != set(MATRIX_CASES):
        raise RuntimeError("mandatory matrix mapping is incomplete")
    if len(set(MATRIX_CASE_TO_PYTEST_NODE.values())) != len(MATRIX_CASES):
        raise RuntimeError("mandatory matrix nodes must be unique")
    _write(
        "adversarial-matrix.json",
        {
            "cases": [
                {
                    "name": name,
                    "required": True,
                    "pytest_node": MATRIX_CASE_TO_PYTEST_NODE[name],
                }
                for name in MATRIX_CASES
            ],
            "result_source": "each pytest node performs the named behavior",
        },
    )
    _write(
        "near-miss.json",
        {
            "undeclared_capabilities": sorted(
                discovered_capability_set - declared_capability_set
            ),
            "missing_declared_capabilities": sorted(
                declared_capability_set - discovered_capability_set
            ),
            "undeclared_sinks": sorted(discovered_sink_set - declared_sink_set),
            "missing_declared_sinks": sorted(declared_sink_set - discovered_sink_set),
        },
    )
    _write(
        "immutable-dispatch-evidence.json",
        {"representation": "ImmutableFinalDispatch", "proof_status": "NOT_PROVEN"},
    )
    _write(
        "compensation-authority-evidence.json",
        {"authority": "CompensationEligibilityGrant", "proof_status": "NOT_PROVEN"},
    )
    _write("provenance.json", provenance)
    _write(
        "proof-report.json",
        {
            **provenance,
            "inventory_set_equality": discovered_sink_set == declared_sink_set,
            "effect_capability_set_equality": (
                discovered_capability_set == declared_capability_set
            ),
            "effect_sink_set_equality": discovered_sink_set == declared_sink_set,
            "static_inventory_regressions_passed": regressions_passed,
            "registry_set_equality": registered_boundaries == expected_boundaries,
            "result": "PASS" if passed else "FAIL",
            "explicit_non_claims": [
                "all VERITAS external I/O is Bind-governed",
                "arbitrary equivalent-privilege in-process compromise resistance",
                "TLS/provider identity proof",
                "universal exactly-once external delivery",
                "production readiness",
            ],
        },
    )
    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-matrix", action="store_true")
    arguments = parser.parse_args()
    raise SystemExit(run_mandatory_matrix() if arguments.run_matrix else main())
