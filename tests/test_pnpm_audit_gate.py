"""Tests for the pnpm audit CI wrapper."""

from __future__ import annotations

import subprocess
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "ci" / "pnpm_audit_gate.py"
    spec = spec_from_file_location("pnpm_audit_gate", module_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pnpm_audit_gate = _load_module()


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    """Build a ``CompletedProcess`` for subprocess mocks."""
    return subprocess.CompletedProcess(
        args=["pnpm", "audit"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_should_tolerate_endpoint_retirement_true() -> None:
    """Known endpoint-retirement signatures should be tolerated."""
    output = "ERR_PNPM_AUDIT_BAD_RESPONSE responded with 410 endpoint is being retired"
    assert pnpm_audit_gate.should_tolerate_endpoint_retirement(output)


def test_should_tolerate_endpoint_retirement_false() -> None:
    """Non-retirement errors should not be tolerated."""
    output = "high severity vulnerabilities found"
    assert not pnpm_audit_gate.should_tolerate_endpoint_retirement(output)


def test_run_pnpm_audit_success(monkeypatch) -> None:
    """Successful pnpm audit exits with zero."""

    def _fake_run(*_args, **_kwargs):
        return _completed(returncode=0, stdout="ok")

    monkeypatch.setattr(pnpm_audit_gate.subprocess, "run", _fake_run)
    assert pnpm_audit_gate.run_pnpm_audit(["--audit-level=high", "--prod"]) == 0


def test_run_pnpm_audit_tolerates_known_410(monkeypatch) -> None:
    """Known endpoint-retirement errors should exit zero with warnings."""

    def _fake_run(*_args, **_kwargs):
        return _completed(
            returncode=1,
            stderr="ERR_PNPM_AUDIT_BAD_RESPONSE: endpoint is being retired; responded with 410",
        )

    monkeypatch.setattr(pnpm_audit_gate.subprocess, "run", _fake_run)
    assert pnpm_audit_gate.run_pnpm_audit(["--audit-level=high", "--prod"]) == 0


def test_run_pnpm_audit_preserves_other_failures(monkeypatch) -> None:
    """Unexpected pnpm audit failures must remain blocking."""

    def _fake_run(*_args, **_kwargs):
        return _completed(returncode=42, stderr="network timeout")

    monkeypatch.setattr(pnpm_audit_gate.subprocess, "run", _fake_run)
    assert pnpm_audit_gate.run_pnpm_audit(["--audit-level=high", "--prod"]) == 42
