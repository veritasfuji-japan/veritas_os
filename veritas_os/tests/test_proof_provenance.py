"""Regression checks for checkout-bound E2E evidence and workflow coverage."""

import subprocess

import pytest
import yaml

from veritas_os.tests.helpers.proof_provenance import (
    REPO_ROOT,
    capture_proof_provenance,
    verify_proof_provenance,
)


@pytest.fixture
def checkout(tmp_path):
    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=tmp_path, check=True,
            capture_output=True, text=True,
        ).stdout.strip()

    git("init")
    git("-c", "user.name=Proof Test", "-c", "user.email=proof@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "fixture")
    return {
        "source_sha": "a" * 40,
        "base_sha": "b" * 40,
        "expected_tested_sha": git("rev-parse", "HEAD"),
        "repo_root": tmp_path,
    }


@pytest.mark.parametrize("event", ["pull_request", "push", "workflow_dispatch"])
def test_records_actual_checkout_separately_from_pr_metadata(checkout, event):
    if event != "pull_request":
        checkout["source_sha"] = checkout["expected_tested_sha"]
        checkout["base_sha"] = checkout["expected_tested_sha"]
    provenance = capture_proof_provenance(**checkout)
    assert provenance == {
        "source_sha": checkout["source_sha"],
        "base_sha": checkout["base_sha"],
        "tested_sha": checkout["expected_tested_sha"],
    }
    verify_proof_provenance(provenance, dict(provenance), **checkout)


@pytest.mark.parametrize("field", ["source_sha", "base_sha", "expected_tested_sha"])
@pytest.mark.parametrize("value", ["", "abc123", "g" * 40, "a" * 40 + "\n", None])
def test_missing_or_malformed_identity_fails_closed(checkout, field, value):
    checkout[field] = value
    with pytest.raises(ValueError, match=f"invalid proof provenance: {field}"):
        capture_proof_provenance(**checkout)


def test_checkout_must_match_ci_event_sha(checkout):
    checkout["expected_tested_sha"] = "c" * 40
    with pytest.raises(ValueError, match="checkout identity mismatch"):
        capture_proof_provenance(**checkout)


def test_checkout_is_rechecked_when_verifying_artifacts(checkout):
    provenance = capture_proof_provenance(**checkout)
    subprocess.run(
        ["git", "-c", "user.name=Proof Test", "-c",
         "user.email=proof@example.invalid", "-c", "commit.gpgsign=false",
         "commit", "--allow-empty", "-m", "changed checkout"],
        cwd=checkout["repo_root"], check=True, capture_output=True,
    )
    with pytest.raises(ValueError, match="checkout identity mismatch"):
        verify_proof_provenance(provenance, dict(provenance), **checkout)


@pytest.mark.parametrize("error", [FileNotFoundError(), subprocess.TimeoutExpired("git", 10)])
def test_unavailable_git_fails_closed(checkout, monkeypatch, error):
    def unavailable(*args, **kwargs):
        raise error

    monkeypatch.setattr(subprocess, "run", unavailable)
    with pytest.raises(ValueError, match="checkout identity unavailable"):
        capture_proof_provenance(**checkout)


@pytest.mark.parametrize("field", ["source_sha", "base_sha", "tested_sha"])
@pytest.mark.parametrize("target", ["report", "evidence", "both"])
@pytest.mark.parametrize("missing", [False, True])
def test_wrong_or_missing_artifact_identities_fail_even_if_both_agree(
    checkout, field, target, missing,
):
    provenance = capture_proof_provenance(**checkout)
    artifacts = {"report": dict(provenance), "evidence": dict(provenance)}
    for name, artifact in artifacts.items():
        if target in (name, "both"):
            if missing:
                del artifact[field]
            else:
                artifact[field] = "d" * 40
    with pytest.raises(ValueError, match="proof provenance mismatch"):
        verify_proof_provenance(**artifacts, **checkout)


@pytest.mark.parametrize("workflow,prefix", [
    ("reproducible-decision-to-effect-e2e.yml", "VERITAS_E2E"),
    ("reproducible-reconciliation-capable-execution-profile.yml", "VERITAS_PROFILE"),
])
def test_dedicated_proofs_cover_all_prs_main_pushes_and_manual_runs(workflow, prefix):
    # BaseLoader preserves the YAML 1.2 Actions key `on` as a string.
    config = yaml.load(
        (REPO_ROOT / ".github" / "workflows" / workflow).read_text(),
        Loader=yaml.BaseLoader,
    )
    assert set(config["on"]) == {"pull_request", "push", "workflow_dispatch"}
    assert not config["on"]["pull_request"]  # No transitive-dependency path gaps.
    assert config["on"]["push"] == {"branches": ["main"]}
    job, = config["jobs"].values()
    assert job["env"][f"{prefix}_TESTED_SHA"] == "${{ github.sha }}"
    assert job["env"][f"{prefix}_SOURCE_SHA"] == (
        "${{ github.event.pull_request.head.sha || github.sha }}"
    )
    assert job["env"][f"{prefix}_BASE_SHA"] == (
        "${{ github.event.pull_request.base.sha || github.sha }}"
    )
    checkout, = [step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@")]
    assert not checkout.get("with", {}).get("ref")  # Keep the event's merge/main SHA.
