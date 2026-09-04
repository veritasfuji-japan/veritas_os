"""Tests for the pnpm audit CI wrapper."""

from __future__ import annotations

import subprocess
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import yaml


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


def test_transient_transport_failure_signatures_are_narrow() -> None:
    """Known registry transport errors should be retryable, not tolerated."""
    assert pnpm_audit_gate.is_transient_transport_failure("ERR_SOCKET_TIMEOUT")
    assert pnpm_audit_gate.is_transient_transport_failure("503 Service Unavailable")
    assert not pnpm_audit_gate.is_transient_transport_failure(
        "high severity vulnerabilities found"
    )


def test_run_pnpm_audit_success(monkeypatch) -> None:
    """Successful pnpm audit exits with zero."""

    def _fake_run(*_args, **kwargs):
        assert kwargs["timeout"] == pnpm_audit_gate._ATTEMPT_TIMEOUT_SECONDS
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
    """Vulnerability and unexpected failures remain immediately blocking."""

    calls = 0

    def _fake_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return _completed(returncode=42, stderr="high severity vulnerabilities found")

    monkeypatch.setattr(pnpm_audit_gate.subprocess, "run", _fake_run)
    assert pnpm_audit_gate.run_pnpm_audit(["--audit-level=high", "--prod"]) == 42
    assert calls == 1


def test_run_pnpm_audit_retries_transient_failure_then_succeeds(monkeypatch) -> None:
    """A transient registry failure should receive a bounded retry."""

    results = iter(
        [
            _completed(returncode=1, stderr="ERR_SOCKET_TIMEOUT"),
            _completed(returncode=0, stdout="No known vulnerabilities found"),
        ]
    )
    sleeps: list[int] = []

    monkeypatch.setattr(pnpm_audit_gate.subprocess, "run", lambda *_a, **_k: next(results))
    monkeypatch.setattr(pnpm_audit_gate.time, "sleep", sleeps.append)

    assert pnpm_audit_gate.run_pnpm_audit(["--audit-level=high", "--prod"]) == 0
    assert sleeps == [5]


def test_run_pnpm_audit_fails_closed_after_transient_retries(monkeypatch) -> None:
    """Repeated transport failures must never become a passing audit."""

    calls = 0
    sleeps: list[int] = []

    def _fake_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return _completed(returncode=37, stderr="request failed: ECONNRESET")

    monkeypatch.setattr(pnpm_audit_gate.subprocess, "run", _fake_run)
    monkeypatch.setattr(pnpm_audit_gate.time, "sleep", sleeps.append)

    assert pnpm_audit_gate.run_pnpm_audit(["--audit-level=high", "--prod"]) == 37
    assert calls == 3
    assert sleeps == [5, 15]


def test_run_pnpm_audit_bounds_hung_subprocess(monkeypatch) -> None:
    """A hung pnpm process should be retried and end as temporary failure."""

    calls = 0

    def _fake_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise subprocess.TimeoutExpired(cmd="pnpm audit", timeout=75)

    monkeypatch.setattr(pnpm_audit_gate.subprocess, "run", _fake_run)
    monkeypatch.setattr(pnpm_audit_gate.time, "sleep", lambda _seconds: None)

    assert (
        pnpm_audit_gate.run_pnpm_audit(["--audit-level=high", "--prod"])
        == pnpm_audit_gate._TEMPORARY_FAILURE_EXIT_CODE
    )
    assert calls == 3


def test_main_test_lanes_do_not_wait_for_dependency_audit() -> None:
    """Registry outages must not suppress independent test evidence."""
    workflow_path = Path(__file__).resolve().parents[1] / ".github/workflows/main.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))

    jobs = workflow["jobs"]
    assert "continue-on-error" not in jobs["dependency-audit"]
    for job_name in ("test", "test-postgresql", "test-slow", "frontend-quality-gate"):
        assert "dependency-audit" not in jobs[job_name]["needs"]


def test_parse_args_accepts_pnpm_options_without_separator() -> None:
    """CLI passthrough should accept unknown pnpm options as audit args."""
    parsed = pnpm_audit_gate.parse_args(["--audit-level=high", "--prod"])
    assert parsed.audit_args == ["--audit-level=high", "--prod"]
