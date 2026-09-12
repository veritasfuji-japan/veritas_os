"""Tests for the VERITAS / CAGE Provider03 Phase 3 deterministic proof."""

from __future__ import annotations

import copy
import json

import pytest

from veritas_os.governance.cage_provider03_phase3 import (
    PROVIDER03_FIELD_MAP,
    build_negative_test_report,
    build_phase3_proof_bundle,
    build_replay_report,
    cage_ingested_bind_receipt_digest,
    jcs_canonicalize_phase3,
    normalize_provider03_payload,
    phase3_evidence_seal_hash,
    project_provider03_validation_result,
    write_phase3_artifacts,
)


def _by_name(bundle: dict[str, object]) -> dict[str, dict[str, object]]:
    scenarios = bundle["scenarios"]
    assert isinstance(scenarios, list)
    return {item["scenario_name"]: item for item in scenarios}


def test_phase3_preserves_existing_seven_scenario_outcomes() -> None:
    bundle = build_phase3_proof_bundle()
    scenarios = _by_name(bundle)

    assert {
        name: item["actual_outcome"] for name, item in scenarios.items()
    } == {
        "scenario_a_allowed_internal_escalation": "commit",
        "scenario_b_prohibited_account_freeze": "block",
        "scenario_c_prohibited_customer_notification": "block",
        "scenario_d_stale_sanctions_screening": "escalate",
        "scenario_e_missing_authority": "block",
        "scenario_f_high_irreversibility_without_human_approval": "block",
        "scenario_g_policy_uncertainty": "block",
    }


def test_phase3_verdict_counts_are_1_1_5() -> None:
    manifest = build_phase3_proof_bundle()["manifest"]
    assert manifest["observed_primary_results"] == {
        "APPROVED": 1,
        "ESCALATE": 1,
        "REJECTED": 5,
    }


def test_escalate_maps_to_defer_semantics() -> None:
    scenario = _by_name(build_phase3_proof_bundle())[
        "scenario_d_stale_sanctions_screening"
    ]
    assert scenario["provider03_response"]["verdict"] == "ESCALATE"
    projection = scenario["validation_projection"]
    assert projection["admitted"] is False
    assert any(
        finding.get("code") == "provider_03.escalate"
        and finding.get("needs_human_review") is True
        for finding in projection["findings"]
    )


@pytest.mark.parametrize(
    "scenario_name",
    [
        "scenario_e_missing_authority",
        "scenario_f_high_irreversibility_without_human_approval",
        "scenario_g_policy_uncertainty",
    ],
)
def test_fail_closed_scenarios_never_admit(scenario_name: str) -> None:
    scenario = _by_name(build_phase3_proof_bundle())[scenario_name]
    assert scenario["provider03_response"]["verdict"] == "REJECTED"
    assert scenario["validation_projection"]["admitted"] is False


def test_unknown_and_missing_verdicts_fail_closed() -> None:
    assert project_provider03_validation_result({"verdict": "MAYBE"})["admitted"] is False
    assert project_provider03_validation_result({})["admitted"] is False


def test_provider03_field_mapping_is_non_mutating() -> None:
    payload = {
        "action_context": {
            "amount": 100000,
            "symbol": "AAPL",
            "currency": "USD",
        }
    }
    original = copy.deepcopy(payload)

    normalized = normalize_provider03_payload(
        payload,
        field_map=PROVIDER03_FIELD_MAP,
    )

    assert payload == original
    assert normalized == {
        "action_context": {
            "magnitude": 100000,
            "context": "AAPL",
            "currency": "USD",
        }
    }


def test_phase3_jcs_is_key_order_independent() -> None:
    left = {"b": 2, "a": {"y": True, "x": "value"}}
    right = {"a": {"x": "value", "y": True}, "b": 2}
    assert jcs_canonicalize_phase3(left) == jcs_canonicalize_phase3(right)


def test_phase3_jcs_rejects_float_drift() -> None:
    with pytest.raises(TypeError, match="rejects floats"):
        jcs_canonicalize_phase3({"amount": 1.25})


def test_cage_ingest_digest_is_deterministic_and_mutation_sensitive() -> None:
    scenario = _by_name(build_phase3_proof_bundle())[
        "scenario_a_allowed_internal_escalation"
    ]
    receipt = scenario["bind_receipt"]
    first = cage_ingested_bind_receipt_digest(receipt)
    second = cage_ingested_bind_receipt_digest(dict(reversed(list(receipt.items()))))
    assert first == second

    mutated = dict(receipt)
    mutated["commit_boundary_result"] = "block"
    assert cage_ingested_bind_receipt_digest(mutated) != first


def test_hash_domains_remain_explicitly_separate() -> None:
    scenario = _by_name(build_phase3_proof_bundle())[
        "scenario_a_allowed_internal_escalation"
    ]
    domains = scenario["hash_domains"]

    assert (
        domains["veritas_bind_receipt_hash"]["input"]
        == "bind receipt body before bind_receipt_hash is added"
    )
    assert (
        domains["cage_ingested_bind_receipt_digest"]["input"]
        == "complete bind receipt including bind_receipt_hash"
    )
    assert len(domains["veritas_bind_receipt_hash"]["value"]) == 64
    assert len(domains["cage_ingested_bind_receipt_digest"]["value"]) == 64


def test_trustlog_is_lineage_only_without_fabricated_witness() -> None:
    scenario = _by_name(build_phase3_proof_bundle())[
        "scenario_a_allowed_internal_escalation"
    ]
    assert scenario["trustlog"]["proof_status"] == "lineage_only"
    assert scenario["trustlog"]["lineage_ref"].startswith("trustlog://bind/")
    assert scenario["trustlog"]["witness_hash"] is None


def test_evidence_seal_is_deterministic_and_mutation_sensitive() -> None:
    scenario = _by_name(build_phase3_proof_bundle())[
        "scenario_a_allowed_internal_escalation"
    ]
    evidence = scenario["evidence_artifact"]
    first = phase3_evidence_seal_hash(evidence)
    second = phase3_evidence_seal_hash(json.loads(json.dumps(evidence)))
    assert first == second

    mutated = dict(evidence)
    mutated["provider03_verdict"] = "REJECTED"
    assert phase3_evidence_seal_hash(mutated) != first


def test_two_independent_phase3_runs_replay_identically() -> None:
    first = build_phase3_proof_bundle()
    second = build_phase3_proof_bundle()
    report = build_replay_report(first, second)
    assert report["scenario_count"] == 7
    assert report["overall_replay_match"] is True
    assert all(item["overall_replay_match"] for item in report["scenarios"])


def test_negative_test_report_passes() -> None:
    report = build_negative_test_report(build_phase3_proof_bundle())
    assert report["passed"] is True
    assert len(report["checks"]) >= 8
    assert all(item["passed"] for item in report["checks"])


def test_artifact_writer_produces_reviewer_pack(tmp_path) -> None:
    summary = write_phase3_artifacts(tmp_path)
    assert summary["scenario_count"] == 7
    assert summary["overall_replay_match"] is True
    assert summary["negative_tests_passed"] is True
    assert summary["live_external_effects"] is False
    assert summary["production_claim"] is False

    assert (tmp_path / "manifest.json").is_file()
    assert (tmp_path / "replay_report.json").is_file()
    assert (tmp_path / "negative_test_report.json").is_file()
    assert (tmp_path / "summary.json").is_file()
    scenario_files = list((tmp_path / "scenarios").glob("*.json"))
    assert len(scenario_files) == 7
