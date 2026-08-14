"""Reviewer-boundary tests for the Decision Pipeline PoC runner."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "scripts/run_decide_pipeline_poc.py"


def _run(tmp_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the proof in a fresh interpreter so import-time paths are isolated."""
    report = tmp_path / "report.json"
    environment = dict(os.environ)
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "OPENROUTER_API_KEY",
    ):
        environment.pop(name, None)
    return subprocess.run(
        [sys.executable, str(RUNNER), "--report", str(report), *arguments],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
        timeout=120,
    )


@pytest.mark.integration
def test_real_decide_route_generates_strict_evidence(tmp_path: Path) -> None:
    """The authenticated real route must produce linked encrypted evidence."""
    result = _run(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["route"] == "POST /v1/decide"
    assert report["authenticated_http_route_exercised"]
    assert report["permission_decide_exercised"]
    assert report["request_validation_exercised"]
    assert report["controlled_provider_calls"] > 0
    assert report["outbound_provider_network_calls"] == 0
    assert report["trustlog_append_verified"]
    assert report["trustlog_chain_verified"]
    assert report["replay_artifact_verified"]
    assert report["execution_intent_created"] is False
    assert report["bind_invoked"] is False
    assert report["webhook_bind_adapter_invoked"] is False
    assert report["external_effect_occurred"] is False
    assert report["human_approval_fabricated"] is False
    assert report["authority_evidence_fabricated"] is False


@pytest.mark.integration
def test_proof_fails_after_http_200_when_ledger_verification_fails(
    tmp_path: Path,
) -> None:
    """TrustLog verification is stricter than ordinary route success."""
    result = _run(tmp_path, "--force-verify-failure")

    assert result.returncode != 0
    assert "HTTP_ROUTE               PASS" in result.stdout
    assert "TRUSTLOG                 FAIL" in result.stdout
    assert "RESULT                   FAIL" in result.stdout
    assert not (tmp_path / "report.json").exists()


@pytest.mark.integration
def test_proof_fails_without_encryption_material(tmp_path: Path) -> None:
    """Missing encryption material must never yield reviewer PASS evidence."""
    result = _run(tmp_path, "--omit-encryption-key")

    assert result.returncode != 0
    assert "TRUSTLOG                 FAIL" in result.stdout
    assert not (tmp_path / "report.json").exists()


def test_runner_controls_only_central_llm_seam_and_keeps_bind_separate() -> None:
    """Static boundary guard prevents broad runtime mocks and bind imports."""
    source = RUNNER.read_text(encoding="utf-8")

    assert 'patch.object(llm_client, "chat", controlled_chat)' in source
    assert "decision_pipeline, \"core_decide\", observed_kernel_decide" in source
    assert "original_kernel_decide(*args, **kwargs)" in source
    assert "patch.object(server, \"get_decision_pipeline\"" not in source
    assert "WebhookBindAdapter" not in source
    assert "ExecutionIntent" not in source
    assert "external_bind_poc" not in source


def test_normalized_projection_is_stable_and_contains_no_fixture_secret() -> None:
    """Stable inputs hash identically and no credential is committed."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("decide_poc_runner", RUNNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fixture = module._request_fixture()
    transcript = json.loads(module.FIXTURE_PATH.read_text(encoding="utf-8"))

    assert module._digest(fixture) == module._digest(module._request_fixture())
    assert module._digest(transcript) == module._digest(transcript)
    serialized = RUNNER.read_text(encoding="utf-8") + json.dumps(transcript)
    assert "OPENAI_API_KEY=" not in serialized
    assert "VERITAS_ENCRYPTION_KEY=" not in serialized
