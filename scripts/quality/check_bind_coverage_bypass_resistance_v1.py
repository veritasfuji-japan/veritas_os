#!/usr/bin/env python3
"""Export and check the frozen V1 executable effect-boundary inventory."""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from veritas_os.policy.bind_coverage_registry import (
    load_bind_coverage_registry,
    validate_bind_coverage_registry,
)
from veritas_os.policy.bind_execution_capability import PROOF_SCOPE


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "artifacts" / "bind-coverage-bypass-resistance-v1"
EXPECTED_SINKS = {
    ("veritas_os/policy/bundle.py", "archive_path.open"),
    ("veritas_os/policy/bundle.py", "open"),
    ("veritas_os/policy/bundle.py", "tarfile.open"),
    ("veritas_os/policy/sandbox_event_service.py", "app.post"),
    ("veritas_os/policy/sandbox_https_transport.py", "asyncio.open_connection"),
    ("veritas_os/policy/sandbox_https_transport.py", "writer.write"),
    ("veritas_os/policy/sandbox_reconciliation.py", "asyncio.open_connection"),
    ("veritas_os/policy/sandbox_reconciliation.py", "writer.write"),
    ("veritas_os/policy/webhook_bind_adapter.py", "opener.open"),
    ("veritas_os/policy/webhook_bind_adapter.py", "transport.request"),
}
FROZEN_EFFECT_SINKS = {
    ("veritas_os/policy/sandbox_https_transport.py", "asyncio.open_connection"),
    ("veritas_os/policy/sandbox_https_transport.py", "writer.write"),
    ("veritas_os/policy/webhook_bind_adapter.py", "opener.open"),
    ("veritas_os/policy/webhook_bind_adapter.py", "transport.request"),
}
EFFECT_CALL_NAMES = {
    "open_connection", "open", "request", "urlopen", "write", "send",
    "sendall", "post", "put", "patch", "delete",
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


def _call_name(node: ast.Call) -> str:
    parts: list[str] = []
    current = node.func
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _reviewed_sources(root: Path) -> list[Path]:
    policy = root / "veritas_os" / "policy"
    return sorted(policy.glob("*.py"))


def discover(root: Path = ROOT) -> list[dict[str, object]]:
    """Return every candidate effect call in the reviewed production scope."""
    found: list[dict[str, object]] = []
    for path in _reviewed_sources(root):
        relative = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name.rsplit(".", 1)[-1] in EFFECT_CALL_NAMES:
                found.append({
                    "path": relative,
                    "primitive": name,
                    "line": node.lineno,
                    "classification": (
                        "FROZEN_V1_EFFECT_SINK"
                        if (relative, name) in FROZEN_EFFECT_SINKS
                        else "DECLARED_OUT_OF_SCOPE_CANDIDATE"
                    ),
                })
    return sorted(found, key=lambda item: (str(item["path"]), int(item["line"])))


def _write(name: str, value: object) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / name).write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _matrix_evidence(path: Path) -> tuple[list[dict[str, object]], bool]:
    if not path.is_file():
        return [], False
    root = ET.parse(path).getroot()
    evidence: list[dict[str, object]] = []
    for testcase in root.iter("testcase"):
        properties = {
            item.attrib.get("name", ""): item.attrib.get("value", "")
            for item in testcase.findall("./properties/property")
        }
        case_name = properties.get("bind_case_name")
        if not case_name:
            continue
        passed = testcase.find("failure") is None and testcase.find("error") is None
        evidence.append({
            "case_name": case_name,
            "pytest_node_id": (
                f"{testcase.attrib.get('classname', '')}::"
                f"{testcase.attrib.get('name', '')}"
            ),
            "expected_outcome": properties.get("expected_outcome"),
            "actual_outcome": properties.get("actual_outcome"),
            "zero_effect_observation": properties.get(
                "zero_effect_observation"
            ) == "true",
            "result": "PASS" if passed else "FAIL",
        })
    by_name = {str(item["case_name"]): item for item in evidence}
    complete = set(by_name) == set(MATRIX_CASES) and len(evidence) == len(MATRIX_CASES)
    valid = complete and all(
        item["result"] == "PASS"
        and item["actual_outcome"] == "PASS"
        and (
            item["case_name"] in {"legitimate ACTION", "legitimate COMPENSATION"}
            or item["zero_effect_observation"] is True
        )
        for item in evidence
    )
    return sorted(evidence, key=lambda item: str(item["case_name"])), valid


def main() -> int:
    entries = [
        entry for entry in load_bind_coverage_registry()
        if entry.proof_scope == PROOF_SCOPE
    ]
    validation = validate_bind_coverage_registry(load_bind_coverage_registry())
    matrix, matrix_valid = _matrix_evidence(
        OUTPUT / "pytest.xml"
    )
    discovered = discover()
    discovered_set = {(str(row["path"]), str(row["primitive"])) for row in discovered}
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
        and discovered_set == EXPECTED_SINKS
        and registered_boundaries == expected_boundaries
        and len(entries) == 3
        and matrix_valid
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
    _write("execution-boundary-inventory.json", discovered)
    _write("bind-coverage-registry.json", registry_payload)
    _write("adversarial-matrix.json", {
        "required_case_count": len(MATRIX_CASES),
        "executed_case_count": len(matrix),
        "complete": matrix_valid,
        "cases": matrix,
    })
    _write("near-miss.json", {"undeclared_sink_count": len(discovered_set ^ EXPECTED_SINKS)})
    _write("immutable-dispatch-evidence.json", {
        "representation": "ImmutableFinalDispatch", "proof_status": "NOT_PROVEN"
    })
    _write("compensation-authority-evidence.json", {
        "authority": "CompensationEligibilityGrant", "proof_status": "NOT_PROVEN"
    })
    _write("provenance.json", provenance)
    _write("proof-report.json", {
        **provenance,
        "inventory_set_equality": discovered_set == EXPECTED_SINKS,
        "registry_set_equality": registered_boundaries == expected_boundaries,
        "adversarial_matrix_complete": matrix_valid,
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
    raise SystemExit(main())
