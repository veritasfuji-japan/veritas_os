"""Regression guards for TASK-011 Benchmark Rebaseline Phase C."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE_C_RECORD = ROOT / "docs/benchmarks/benchmark-rebaseline-phase-c-v1.json"
HARNESS = ROOT / "veritas_os/scripts/evidence_benchmark.py"
METRICS = ROOT / "veritas_os/benchmarks/evidence/metrics_definition.yaml"
SCHEMA = ROOT / "veritas_os/benchmarks/evidence/output_schema.json"
FIXTURE = ROOT / "veritas_os/benchmarks/evidence/fixtures/sample_cases.jsonl"
WORKFLOW = ROOT / ".github/workflows/benchmark-rebaseline-phase-c.yml"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase_c_record_is_pinned_to_current_post_phase_b_main() -> None:
    data = _load(PHASE_C_RECORD)

    assert data["format_version"] == "benchmark-rebaseline-phase-c/v1"
    assert data["status"] == "EVIDENCE_MEASUREMENT_PROTOCOL_DEFINED"
    assert data["task"] == "TASK-011"
    assert data["phase"] == "C"
    assert data["baseline_source_commit"] == (
        "cb8bde7dc9d191e872d5bfcefe17e1597e70ddcd"
    )
    assert data["phase_b_measured_main_commit"] == (
        "bbf6fdd69f4c2cc5d77903f60f42163528818a03"
    )
    assert data["frozen_controlled_e2e_anchor"] == (
        "ada46f2fe324dd3cbcff6be59d56c4f75c4a6bdc"
    )
    assert data["runtime_integrity"]["runtime_semantics_changed"] is False
    assert data["runtime_integrity"]["benchmark_fixture_changed_for_score"] is False
    assert data["runtime_integrity"]["metric_definition_changed_for_score"] is False


def test_phase_c_uses_frozen_canonical_evidence_inputs() -> None:
    data = _load(PHASE_C_RECORD)
    canonical = data["canonical_measurement"]

    assert canonical["harness"] == "veritas_os/scripts/evidence_benchmark.py"
    assert canonical["metrics_definition"] == (
        "veritas_os/benchmarks/evidence/metrics_definition.yaml"
    )
    assert canonical["output_schema"] == (
        "veritas_os/benchmarks/evidence/output_schema.json"
    )
    assert canonical["fixture"] == (
        "veritas_os/benchmarks/evidence/fixtures/sample_cases.jsonl"
    )
    assert canonical["fixture_case_count"] == 2
    assert set(canonical["systems"]) == {"veritas", "generic"}
    assert set(canonical["axes"]) == {
        "auditability",
        "fail_closed_safety",
        "governance_change_control",
        "replay_divergence_visibility",
        "trust_log_integrity",
    }
    assert canonical["synthetic_comparison"] is True
    assert canonical["external_llm_or_api_allowed"] is False
    assert canonical["benchmark_workload_external_network_required"] is False

    for path in (HARNESS, METRICS, SCHEMA, FIXTURE):
        assert path.is_file()
        assert len(hashlib.sha256(path.read_bytes()).hexdigest()) == 64


def test_phase_c_harness_scores_the_frozen_fixture_deterministically(
    tmp_path: Path,
) -> None:
    output = tmp_path / "evidence.json"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "veritas_os.scripts.evidence_benchmark",
            "--fixtures",
            str(FIXTURE.relative_to(ROOT)),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
    )

    report = _load(output)
    record = _load(PHASE_C_RECORD)
    canonical = record["canonical_measurement"]

    assert report["meta"]["harness_version"] == "0.1.0"
    assert len(report["cases"]) == canonical["fixture_case_count"]
    assert set(report["aggregate"]) == set(canonical["systems"])

    for system in canonical["systems"]:
        assert set(report["aggregate"][system]) == set(canonical["axes"])
        for axis in canonical["axes"]:
            row = report["aggregate"][system][axis]
            assert row["total"] == canonical["fixture_case_count"]
            assert 0 <= row["pass"] <= row["total"]
            assert 0.0 <= row["rate"] <= 1.0


def test_phase_c_claim_boundary_forbids_competitive_overstatement() -> None:
    data = _load(PHASE_C_RECORD)
    boundary = data["claim_boundary"]
    non_claims = set(data["non_claims"])

    assert boundary["comparison_classification"] == (
        "REPOSITORY_CONTROLLED_SYNTHETIC_FIXTURE_SCORING"
    )
    assert boundary["independent_competitive_validation"] is False
    assert boundary["named_vendor_superiority_claim_permitted"] is False
    assert boundary["production_performance_claim_permitted"] is False
    assert boundary["production_readiness_claim_permitted"] is False
    assert boundary["third_party_certification_claim_permitted"] is False
    assert boundary["external_llm_or_api_allowed"] is False

    assert {
        "production latency",
        "production SLA",
        "customer-environment performance",
        "production readiness",
        "third-party certification",
        "superiority over named vendors",
        "third-party competitive validation from synthetic generic fixtures",
    }.issubset(non_claims)


def test_phase_c_workflow_binds_raw_report_and_inputs_to_source_sha() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    record = _load(PHASE_C_RECORD)
    exact_command = record["canonical_measurement"]["exact_command"]

    assert "pull_request:" in text
    assert "push:" in text
    assert "branches: [main]" in text
    assert "ref: ${{ github.event.pull_request.head.sha || github.sha }}" in text
    assert 'SOURCE_SHA="$(git rev-parse HEAD)"' in text
    assert exact_command in text
    assert "validate(instance=report, schema=schema)" in text
    assert "hashlib.sha256(path.read_bytes()).hexdigest()" in text
    assert '"source_commit_sha": source_sha' in text
    assert '"failure_count": 0' in text
    assert "actions/upload-artifact@v4" in text
    assert "retention-days: 90" in text
    assert "OPENAI_API_KEY" not in text
    assert "ANTHROPIC_API_KEY" not in text
    assert "VERITAS_API_KEY" not in text
