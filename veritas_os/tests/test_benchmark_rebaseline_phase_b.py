"""Regression guards for TASK-011 Benchmark Rebaseline Phase B."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "scripts/benchmarks/run_performance_metrics.py"
PHASE_A_CONTRACT = ROOT / "docs/benchmarks/benchmark-rebaseline-contract-v1.json"
PHASE_B_RECORD = ROOT / "docs/benchmarks/benchmark-rebaseline-phase-b-v1.json"
WORKFLOW = ROOT / ".github/workflows/benchmark-rebaseline-phase-b.yml"
STALE_LATEST = ROOT / "docs/en/benchmarks/local-performance-metrics.latest.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase_b_record_is_pinned_to_phase_a_merge() -> None:
    data = _load(PHASE_B_RECORD)

    assert data["format_version"] == "benchmark-rebaseline-phase-b/v1"
    assert data["status"] == "MEASUREMENT_PROTOCOL_DEFINED"
    assert data["task"] == "TASK-011"
    assert data["phase"] == "B"
    assert (
        data["baseline_source_commit"]
        == "ad92ec663b962183327b1b96192378fd562da794"
    )
    assert (
        data["frozen_controlled_e2e_anchor"]
        == "ada46f2fe324dd3cbcff6be59d56c4f75c4a6bdc"
    )
    assert data["runtime_integrity"]["runtime_semantics_changed"] is False
    assert len(data["phase_b_exit"]["completion_conditions"]) >= 6


def test_phase_b_cli_emits_required_source_bound_provenance(tmp_path: Path) -> None:
    source_sha = "a" * 40
    output = tmp_path / "phase-b.json"

    subprocess.run(
        [
            sys.executable,
            str(HARNESS),
            "--iterations",
            "3",
            "--warmup",
            "1",
            "--output",
            str(output),
            "--source-commit",
            source_sha,
        ],
        cwd=ROOT,
        check=True,
    )

    data = _load(output)
    contract = _load(PHASE_A_CONTRACT)

    assert set(contract["required_artifact_fields"]).issubset(data)
    assert data["source_commit_sha"] == source_sha
    assert data["run_timestamp"] == data["generated_at"]
    assert data["iterations_or_run_count"] == data["iterations"] == 3
    assert data["warmup_when_relevant"] == data["warmup"] == 1
    assert data["failure_count"] == data["counters"]["failure"] == 0
    assert data["raw_machine_readable_result"]["metrics"] == data["metrics"]
    assert data["raw_machine_readable_result"]["counters"] == data["counters"]

    harness_identity = data["harness_identity"]
    assert harness_identity["path"] == "scripts/benchmarks/run_performance_metrics.py"
    assert harness_identity["sha256"] == hashlib.sha256(HARNESS.read_bytes()).hexdigest()

    input_identity = data["input_identity"]
    assert input_identity["type"] == "embedded_deterministic_fixture"
    assert input_identity["scenario"] == "local_deterministic_smoke"

    assert data["reproducibility_instructions"]["checkout"] == (
        f"git checkout {source_sha}"
    )
    assert "--source-commit" in data["exact_command"]
    assert source_sha in data["exact_command"]


def test_phase_b_claim_boundary_remains_non_production() -> None:
    data = _load(PHASE_B_RECORD)
    non_claims = set(data["non_claims"])

    assert {
        "production latency",
        "production SLA",
        "customer-environment performance",
        "real customer endpoint performance",
        "external provider latency",
        "third-party certification",
        "regulatory approval",
        "superiority over named vendors",
    }.issubset(non_claims)

    assert data["canonical_measurement"]["external_network_required"] is False
    assert data["canonical_measurement"]["external_llm_or_api_allowed"] is False


def test_phase_b_workflow_measures_checked_out_source_and_uploads_evidence() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    record = _load(PHASE_B_RECORD)
    exact_command = record["canonical_measurement"]["exact_command"]

    assert "pull_request:" in text
    assert "push:" in text
    assert "branches: [main]" in text
    assert "ref: ${{ github.event.pull_request.head.sha || github.sha }}" in text
    assert 'SOURCE_SHA="$(git rev-parse HEAD)"' in text
    assert exact_command in text
    assert "benchmark source SHA mismatch" in text
    assert "actions/upload-artifact@v4" in text
    assert "retention-days: 90" in text
    assert "OPENAI_API_KEY" not in text
    assert "VERITAS_API_KEY" not in text


def test_committed_may_artifact_remains_explicitly_pre_rebaseline() -> None:
    old = _load(STALE_LATEST)
    phase_a = _load(PHASE_A_CONTRACT)
    phase_b = _load(PHASE_B_RECORD)

    old_row = next(
        row
        for row in phase_a["existing_published_artifacts"]
        if row["path"] == "docs/en/benchmarks/local-performance-metrics.latest.json"
    )

    assert old["generated_at"] == "2026-05-09T02:05:00.659731+00:00"
    assert "source_commit_sha" not in old
    assert old_row["classification"] == "STALE_PRE_REBASELINE_REFERENCE"
    assert phase_b["artifact_policy"][
        "committed_pre_rebaseline_latest_classification"
    ] == "STALE_PRE_REBASELINE_REFERENCE"
    assert "GitHub Actions artifact" in phase_b["artifact_policy"][
        "authoritative_phase_b_current_head_location"
    ]
