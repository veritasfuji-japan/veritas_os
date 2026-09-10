"""Regression guards for TASK-011 Benchmark Rebaseline Phase A."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs" / "benchmarks" / "benchmark-rebaseline-contract-v1.json"
PHASE_A_DOC = ROOT / "docs" / "en" / "benchmarks" / "benchmark-rebaseline-phase-a.md"
CURRENT_LOCAL = (
    ROOT / "docs" / "en" / "benchmarks" / "local-performance-metrics.latest.json"
)


def _contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_phase_a_contract_is_pinned_to_post_consolidation_head() -> None:
    data = _contract()
    assert data["format_version"] == "benchmark-rebaseline-contract/v1"
    assert data["status"] == "PHASE_A_CONTRACT_FROZEN"
    assert data["source_commit"] == "53e8e2974123024348b92ddfb7155cd645371620"
    assert (
        data["frozen_controlled_e2e_anchor"]
        == "ada46f2fe324dd3cbcff6be59d56c4f75c4a6bdc"
    )
    assert data["task"] == "TASK-011"
    assert data["phase"] == "A"


def test_phase_a_does_not_publish_new_benchmark_numbers() -> None:
    data = _contract()
    gate = data["publication_gate"]
    assert gate["new_benchmark_numbers_permitted"] is False
    assert data["phase_a_exit"]["benchmark_values_updated"] is False
    assert (
        data["phase_a_exit"]["next_phase"]
        == "PHASE_B_CURRENT_HEAD_DETERMINISTIC_MEASUREMENTS"
    )


def test_canonical_benchmark_surfaces_exist_and_are_distinct() -> None:
    data = _contract()
    surfaces = {row["id"]: row for row in data["canonical_surfaces"]}
    assert set(surfaces) == {"local_deterministic_smoke", "evidence_axes_fixture"}

    local = surfaces["local_deterministic_smoke"]
    assert local["role"] == "CANONICAL_PERFORMANCE_HARNESS"
    assert local["schema_version"] == "performance_metrics.v1"
    assert local["external_network_required"] is False
    assert local["external_llm_or_api_allowed"] is False
    assert (ROOT / local["harness"]).exists()

    evidence = surfaces["evidence_axes_fixture"]
    assert evidence["role"] == "CANONICAL_EVIDENCE_HARNESS"
    assert evidence["external_network_required"] is False
    assert evidence["external_llm_or_api_allowed"] is False
    for key in ("harness", "metrics_definition", "output_schema", "fixture"):
        assert (ROOT / evidence[key]).exists()


def test_evidence_fixture_identity_is_explicitly_synthetic() -> None:
    data = _contract()
    evidence = next(
        row for row in data["canonical_surfaces"] if row["id"] == "evidence_axes_fixture"
    )
    identity = evidence["input_identity"]
    assert identity["synthetic_comparison"] is True
    assert identity["systems"] == ["veritas", "generic"]

    fixture_path = ROOT / evidence["fixture"]
    cases = [
        json.loads(line)
        for line in fixture_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(cases) == identity["fixture_case_count"] == 2
    assert all(set(case["systems"]) == {"veritas", "generic"} for case in cases)


def test_existing_local_artifact_is_marked_stale_pre_rebaseline() -> None:
    data = _contract()
    published = {
        row["path"]: row for row in data["existing_published_artifacts"]
    }
    row = published["docs/en/benchmarks/local-performance-metrics.latest.json"]
    assert row["classification"] == "STALE_PRE_REBASELINE_REFERENCE"
    assert row["source_commit_recorded"] is False
    assert row["current_head_claim_permitted"] is False

    current = json.loads(CURRENT_LOCAL.read_text(encoding="utf-8"))
    assert current["generated_at"] == row["generated_at"]
    assert current["schema_version"] == "performance_metrics.v1"


def test_supporting_runners_are_not_misclassified_as_canonical() -> None:
    data = _contract()
    supporting = {row["id"]: row for row in data["supporting_noncanonical_surfaces"]}
    assert supporting["one_day_poc_http"]["classification"] == (
        "POC_SUPPORTING_NOT_PHASE_A_CANONICAL"
    )
    assert supporting["enhanced_yaml_decide_runner"]["classification"] == (
        "LEGACY_MAINTENANCE_NOT_REBASELINE_CANONICAL"
    )
    assert all((ROOT / row["path"]).exists() for row in supporting.values())


def test_contract_keeps_claim_boundary_conservative() -> None:
    data = _contract()
    non_claims = set(data["non_claims"])
    required = {
        "production latency",
        "customer-environment performance",
        "third-party certification",
        "production SLA",
        "superiority over named vendors",
        "third-party competitive validation from synthetic generic fixtures",
    }
    assert required.issubset(non_claims)

    doc = PHASE_A_DOC.read_text(encoding="utf-8")
    assert "STALE_PRE_REBASELINE_REFERENCE" in doc
    assert "synthetic fixture scoring" in doc
    assert "No benchmark value is changed in this phase." in doc
