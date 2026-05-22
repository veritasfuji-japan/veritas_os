from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from veritas_os.governance.local_viki_mock_receiver import (
    UPSTREAM_MIDDLEWARE_OFFLINE,
    UPSTREAM_MOCK_PAYLOAD_INVALID,
    build_local_viki_mock_unreachable_decision,
    ingest_local_viki_mock_payload,
)


@pytest.fixture(autouse=True)
def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERITAS_LOCAL_VIKI_MOCK_RECEIVER_ENABLE", "1")


def _base_payload(status: str, timestamp: str) -> dict[str, str]:
    return {
        "rsa_status": status,
        "trigger_source": "SRC_Incomplete_Context",
        "timestamp": timestamp,
    }


@pytest.mark.parametrize(
    ("fixture_id", "status", "decision", "reason", "commit_state"),
    [
        (
            "VIKI_POS_001",
            "SAFE_PROCEED",
            "CONTINUE_TO_BIND_BOUNDARY",
            "UPSTREAM_SAFE_PROCEED_SIGNAL",
            "SUSPENDED_NOT_COMMITTED",
        ),
        (
            "VIKI_POS_002",
            "DENSITY_THROTTLED",
            "CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED",
            "UPSTREAM_INTERVENTION_DENSITY_THROTTLE",
            "SUSPENDED_NOT_COMMITTED",
        ),
        (
            "VIKI_POS_003",
            "ALGORITHMIC_HUMILITY_ENGAGED",
            "PAUSE_FOR_HUMAN_REVIEW",
            "UPSTREAM_INCOMPLETE_KYC_CONTEXT",
            "SUSPENDED_NOT_COMMITTED",
        ),
        (
            "VIKI_POS_004",
            "DEFERRAL_ENGAGED",
            "BLOCK_FINAL_COMMIT",
            "UPSTREAM_CRITICAL_DEFERRAL_SIGNAL",
            "BLOCKED_NOT_COMMITTED",
        ),
    ],
)
def test_positive_fixtures(
    fixture_id: str,
    status: str,
    decision: str,
    reason: str,
    commit_state: str,
) -> None:
    receiver_now = datetime(2026, 5, 20, 23, 1, 35, 876000, tzinfo=UTC)
    payload = _base_payload(status, "2026-05-20T23:01:35.876Z")

    result = ingest_local_viki_mock_payload(payload, receiver_now=receiver_now)

    assert fixture_id.startswith("VIKI_POS_")
    assert result["veritas_decision"]["continuation_decision"] == decision
    assert result["veritas_decision"]["reason_code"] == reason
    assert result["veritas_decision"]["sandbox_commit_state"] == commit_state
    assert result["audit_entry"]["original_llm_intent"] == "[REDACTED]"
    assert result["audit_entry"]["rsa_action_taken"] == "[REDACTED]"


@pytest.mark.parametrize(
    "raw_payload",
    [
        "{",
        {"trigger_source": "SRC_Incomplete_Context", "timestamp": "2026-05-20T23:01:35.876Z"},
        {"rsa_status": "SAFE_PROCEED", "timestamp": "2026-05-20T23:01:35.876Z"},
        {"rsa_status": "SAFE_PROCEED", "trigger_source": "SRC_Incomplete_Context"},
        {
            "rsa_status": None,
            "trigger_source": "SRC_Incomplete_Context",
            "timestamp": "2026-05-20T23:01:35.876Z",
        },
        {
            "rsa_status": "SAFE_PROCEED",
            "trigger_source": "",
            "timestamp": "2026-05-20T23:01:35.876Z",
        },
        {
            "rsa_status": "UNKNOWN",
            "trigger_source": "SRC_Incomplete_Context",
            "timestamp": "2026-05-20T23:01:35.876Z",
        },
        {
            "rsa_status": "SAFE_PROCEED",
            "trigger_source": "SRC_Incomplete_Context",
            "timestamp": "invalid",
        },
        ["not", "a", "mapping"],
        {
            "rsa_status": "SAFE_PROCEED",
            "trigger_source": "SRC_Incomplete_Context",
            "timestamp": "2026-05-20T23:01:35.876Z",
            "original_llm_intent": None,
        },
        {
            "rsa_status": "SAFE_PROCEED",
            "trigger_source": "SRC_Incomplete_Context",
            "timestamp": "2026-05-20T23:01:35.876Z",
            "original_llm_intent": 1,
        },
        {
            "rsa_status": "SAFE_PROCEED",
            "trigger_source": "SRC_Incomplete_Context",
            "timestamp": "2026-05-20T23:01:35.876Z",
            "original_llm_intent": "",
        },
        {
            "rsa_status": "SAFE_PROCEED",
            "trigger_source": "SRC_Incomplete_Context",
            "timestamp": "2026-05-20T23:01:35.876Z",
            "rsa_action_taken": None,
        },
        {
            "rsa_status": "SAFE_PROCEED",
            "trigger_source": "SRC_Incomplete_Context",
            "timestamp": "2026-05-20T23:01:35.876Z",
            "rsa_action_taken": 1,
        },
        {
            "rsa_status": "SAFE_PROCEED",
            "trigger_source": "SRC_Incomplete_Context",
            "timestamp": "2026-05-20T23:01:35.876Z",
            "rsa_action_taken": "",
        },
    ],
)
def test_invalid_payloads_fail_closed(raw_payload: object) -> None:
    receiver_now = datetime(2026, 5, 20, 23, 1, 35, 876000, tzinfo=UTC)

    result = ingest_local_viki_mock_payload(raw_payload, receiver_now=receiver_now)

    assert result["veritas_decision"]["continuation_decision"] == "PAUSE_FOR_HUMAN_REVIEW"
    assert result["veritas_decision"]["reason_code"] == UPSTREAM_MOCK_PAYLOAD_INVALID
    assert result["audit_entry"]["rsa_status"] == "INVALID_OR_UNAVAILABLE"


@pytest.mark.parametrize(
    ("offset_seconds", "expected_reason"),
    [
        (299, "UPSTREAM_SAFE_PROCEED_SIGNAL"),
        (300, "UPSTREAM_SAFE_PROCEED_SIGNAL"),
        (301, UPSTREAM_MOCK_PAYLOAD_INVALID),
        (-301, UPSTREAM_MOCK_PAYLOAD_INVALID),
    ],
)
def test_clock_skew_threshold(offset_seconds: int, expected_reason: str) -> None:
    receiver_now = datetime(2026, 5, 20, 23, 1, 35, 876000, tzinfo=UTC)
    payload_time = receiver_now - timedelta(seconds=offset_seconds)
    payload = _base_payload(status="SAFE_PROCEED", timestamp=payload_time.isoformat().replace("+00:00", "Z"))

    result = ingest_local_viki_mock_payload(payload, receiver_now=receiver_now)

    assert result["veritas_decision"]["reason_code"] == expected_reason


def test_unreachable_decision_contract() -> None:
    receiver_now = datetime(2026, 5, 20, 23, 1, 35, 876000, tzinfo=UTC)

    result = build_local_viki_mock_unreachable_decision(receiver_now=receiver_now)

    assert result["veritas_decision"]["continuation_decision"] == "PAUSE_FOR_HUMAN_REVIEW"
    assert result["veritas_decision"]["reason_code"] == UPSTREAM_MIDDLEWARE_OFFLINE
    assert result["veritas_decision"]["sandbox_commit_state"] == "SUSPENDED_NOT_COMMITTED"
    assert (
        result["veritas_decision"]["required_next_action"]
        == "REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE"
    )


def test_guard_blocks_receiver_before_payload_processing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VERITAS_LOCAL_VIKI_MOCK_RECEIVER_ENABLE", raising=False)

    with pytest.raises(
        RuntimeError,
        match="VERITAS_LOCAL_VIKI_MOCK_RECEIVER_ENABLE=1",
    ):
        ingest_local_viki_mock_payload("{", receiver_now=datetime.now(UTC))
