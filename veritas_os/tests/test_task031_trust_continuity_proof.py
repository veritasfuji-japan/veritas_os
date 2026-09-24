"""Deterministic proof-harness checks for TASK-031."""

from pathlib import Path

from scripts.run_task031_trust_continuity_proof import build_proof

FREEZE = Path(
    "docs/architecture/post-compromise-trust-state-continuity-freeze-v1.json"
)


def test_task031_proof_matches_exact_frozen_ten_case_corpus():
    proof = build_proof(FREEZE)
    assert proof["scenario_count"] == 10
    assert [item["case_id"] for item in proof["scenarios"]] == [
        f"T31-{index:02d}" for index in range(1, 11)
    ]
    assert proof["all_scenarios_matched"] is True
    assert proof["runtime_received_expected_labels"] is False
    assert proof["offline_oracle_applied_after_runtime"] is True


def test_task031_proof_never_reuses_historical_authority_or_creates_retry():
    proof = build_proof(FREEZE)
    assert all(
        item["authorization_identity_and_consumption_state"][
            "historical_authorization_reusable"
        ]
        is False
        for item in proof["scenarios"]
    )
    assert all(
        item["external_effect_retry_permitted"] is False
        for item in proof["scenarios"]
    )
    replay = next(item for item in proof["scenarios"] if item["case_id"] == "T31-09")
    assert replay["matched"] is True
    assert replay["new_authorization_eligible"] is False
    assert replay["allow_block_reason_code"] == (
        "PTC_HISTORICAL_AUTHORIZATION_REUSE_REJECTED"
    )


def test_task031_proof_is_deterministic():
    assert build_proof(FREEZE) == build_proof(FREEZE)
