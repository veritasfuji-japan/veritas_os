from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from veritas_os.governance.local_viki_mock_receiver import ingest_local_viki_mock_payload

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "local_viki_mock_receiver"


def _fixture_text(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def _assert_decision(
    result: dict[str, object],
    expected_decision: str,
    expected_reason: str,
    expected_commit_state: str,
) -> None:
    veritas_decision = result["veritas_decision"]
    assert isinstance(veritas_decision, dict)
    assert veritas_decision["continuation_decision"] == expected_decision
    assert veritas_decision["reason_code"] == expected_reason
    assert veritas_decision["sandbox_commit_state"] == expected_commit_state


@pytest.mark.parametrize(
    ("fixture_name", "decision", "reason", "commit_state"),
    [
        (
            "viki_pos_001_safe_proceed.json",
            "CONTINUE_TO_BIND_BOUNDARY",
            "UPSTREAM_SAFE_PROCEED_SIGNAL",
            "SUSPENDED_NOT_COMMITTED",
        ),
        (
            "viki_pos_002_density_throttled.json",
            "CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED",
            "UPSTREAM_INTERVENTION_DENSITY_THROTTLE",
            "SUSPENDED_NOT_COMMITTED",
        ),
        (
            "viki_pos_003_algorithmic_humility_engaged.json",
            "PAUSE_FOR_HUMAN_REVIEW",
            "UPSTREAM_INCOMPLETE_KYC_CONTEXT",
            "SUSPENDED_NOT_COMMITTED",
        ),
        (
            "viki_pos_004_deferral_engaged.json",
            "BLOCK_FINAL_COMMIT",
            "UPSTREAM_CRITICAL_DEFERRAL_SIGNAL",
            "BLOCKED_NOT_COMMITTED",
        ),
    ],
)
def test_local_fixture_e2e_positive(
    monkeypatch: pytest.MonkeyPatch,
    fixture_name: str,
    decision: str,
    reason: str,
    commit_state: str,
) -> None:
    monkeypatch.setenv("VERITAS_LOCAL_VIKI_MOCK_RECEIVER_ENABLE", "1")
    receiver_now = datetime(2026, 5, 20, 23, 1, 35, 876000, tzinfo=UTC)

    result = ingest_local_viki_mock_payload(_fixture_text(fixture_name), receiver_now=receiver_now)

    _assert_decision(result, decision, reason, commit_state)
    audit_entry = result["audit_entry"]
    assert isinstance(audit_entry, dict)
    assert audit_entry["upstream_signal_source"] == "RSA"
    assert audit_entry["original_llm_intent"] == "[REDACTED]"
    assert audit_entry["rsa_action_taken"] == "[REDACTED]"
    assert audit_entry["veritas_continuation_decision"] == decision
    assert audit_entry["veritas_sandbox_commit_state"] == commit_state


@pytest.mark.parametrize(
    "fixture_name",
    [
        "viki_neg_001_invalid_json.json",
        "viki_neg_002_missing_rsa_status.json",
        "viki_neg_003_unknown_rsa_status.json",
        "viki_neg_004_invalid_timestamp.json",
        "viki_neg_005_payload_shape_array.json",
        "viki_neg_006_missing_trigger_source.json",
        "viki_neg_007_null_required_field.json",
    ],
)
def test_local_fixture_e2e_negative(monkeypatch: pytest.MonkeyPatch, fixture_name: str) -> None:
    monkeypatch.setenv("VERITAS_LOCAL_VIKI_MOCK_RECEIVER_ENABLE", "1")
    receiver_now = datetime(2026, 5, 20, 23, 1, 35, 876000, tzinfo=UTC)

    result = ingest_local_viki_mock_payload(_fixture_text(fixture_name), receiver_now=receiver_now)

    _assert_decision(
        result,
        "PAUSE_FOR_HUMAN_REVIEW",
        "UPSTREAM_MOCK_PAYLOAD_INVALID",
        "SUSPENDED_NOT_COMMITTED",
    )
    veritas_decision = result["veritas_decision"]
    assert isinstance(veritas_decision, dict)
    assert veritas_decision["required_next_action"] == "REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW"

    audit_entry = result["audit_entry"]
    assert isinstance(audit_entry, dict)
    assert audit_entry["rsa_status"] == "INVALID_OR_UNAVAILABLE"
    assert audit_entry["trigger_source"] == "LOCAL_VIKI_MOCK_RECEIVER"
    assert audit_entry["original_llm_intent"] == "[REDACTED]"
    assert audit_entry["rsa_action_taken"] == "[REDACTED]"


def test_local_fixture_guard_blocks_before_payload_processing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VERITAS_LOCAL_VIKI_MOCK_RECEIVER_ENABLE", raising=False)
    receiver_now = datetime(2026, 5, 20, 23, 1, 35, 876000, tzinfo=UTC)

    with pytest.raises(RuntimeError, match="VERITAS_LOCAL_VIKI_MOCK_RECEIVER_ENABLE=1"):
        ingest_local_viki_mock_payload(
            _fixture_text("viki_pos_001_safe_proceed.json"),
            receiver_now=receiver_now,
        )
