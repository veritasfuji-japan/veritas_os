# tests for veritas_os/core/eu_ai_act_oversight.py
"""Tests for Article 14 human oversight helpers."""
from __future__ import annotations

from unittest import mock

import pytest

from veritas_os.core.eu_ai_act_oversight import (
    HumanReviewQueue,
    SystemHaltController,
    apply_human_oversight_hook,
    DEFAULT_HUMAN_REVIEW_SLA_SECONDS,
)


@pytest.fixture(autouse=True)
def _clear_state():
    """Reset shared state before and after each test."""
    HumanReviewQueue.clear_for_testing()
    SystemHaltController.clear_for_testing()
    yield
    HumanReviewQueue.clear_for_testing()
    SystemHaltController.clear_for_testing()


class TestHumanReviewQueue:
    def test_enqueue_returns_entry(self):
        entry = HumanReviewQueue.enqueue(
            decision_payload={"request_id": "r1"},
            reason="test",
        )
        assert entry["status"] == "pending"
        assert entry["entry_id"]
        assert entry["sla_deadline"]
        assert entry["reason"] == "test"

    def test_pending_entries(self):
        HumanReviewQueue.enqueue(decision_payload={"id": "1"}, reason="a")
        HumanReviewQueue.enqueue(decision_payload={"id": "2"}, reason="b")
        pending = HumanReviewQueue.pending_entries()
        assert len(pending) == 2

    def test_review_approve(self):
        entry = HumanReviewQueue.enqueue(decision_payload={"id": "1"})
        result = HumanReviewQueue.review(
            entry["entry_id"], approved=True, reviewer="admin"
        )
        assert result["status"] == "approved"
        assert result["reviewer"] == "admin"
        # No longer pending
        assert len(HumanReviewQueue.pending_entries()) == 0

    def test_review_reject(self):
        entry = HumanReviewQueue.enqueue(decision_payload={"id": "1"})
        result = HumanReviewQueue.review(
            entry["entry_id"], approved=False, reviewer="admin", comment="bad"
        )
        assert result["status"] == "rejected"

    def test_review_nonexistent_returns_none(self):
        assert HumanReviewQueue.review("fake", approved=True, reviewer="x") is None

    def test_get_entry(self):
        entry = HumanReviewQueue.enqueue(decision_payload={"id": "1"})
        found = HumanReviewQueue.get_entry(entry["entry_id"])
        assert found is not None
        assert found["entry_id"] == entry["entry_id"]

    def test_get_entry_nonexistent(self):
        assert HumanReviewQueue.get_entry("nonexistent") is None

    def test_check_expired_entries(self):
        # Enqueue with very short SLA
        original_sla = HumanReviewQueue._sla_seconds
        try:
            HumanReviewQueue._sla_seconds = -1  # Already expired
            entry = HumanReviewQueue.enqueue(decision_payload={"id": "exp"})
            expired = HumanReviewQueue.check_expired_entries()
            assert len(expired) >= 1
            assert expired[0]["status"] == "expired"
        finally:
            HumanReviewQueue._sla_seconds = original_sla

    def test_webhook_not_called_when_no_url(self):
        original = HumanReviewQueue._webhook_url
        try:
            HumanReviewQueue._webhook_url = None
            # Should not raise
            HumanReviewQueue.enqueue(decision_payload={"id": "1"})
        finally:
            HumanReviewQueue._webhook_url = original

    def test_webhook_bad_scheme_skipped(self):
        original = HumanReviewQueue._webhook_url
        try:
            HumanReviewQueue._webhook_url = "ftp://bad.example.com"
            HumanReviewQueue.enqueue(decision_payload={"id": "1"})
        finally:
            HumanReviewQueue._webhook_url = original


class TestSystemHaltController:
    def test_halt_and_resume(self):
        assert SystemHaltController.is_halted() is False
        halt_result = SystemHaltController.halt(reason="emergency", operator="admin")
        assert halt_result["halted"] is True
        assert SystemHaltController.is_halted() is True

        resume_result = SystemHaltController.resume(operator="admin", comment="resolved")
        assert resume_result["resumed"] is True
        assert resume_result["was_halted"] is True
        assert SystemHaltController.is_halted() is False

    def test_status(self):
        status = SystemHaltController.status()
        assert status["halted"] is False

        SystemHaltController.halt(reason="test", operator="op")
        status = SystemHaltController.status()
        assert status["halted"] is True
        assert status["halted_by"] == "op"
        assert status["reason"] == "test"

    def test_resume_when_not_halted(self):
        result = SystemHaltController.resume(operator="op")
        assert result["was_halted"] is False


class TestApplyHumanOversightHook:
    def test_pauses_on_low_trust(self):
        payload: dict = {"request_id": "r1"}
        result = apply_human_oversight_hook(
            trust_score=0.5,
            risk_level="MEDIUM",
            response_payload=payload,
            threshold=0.8,
        )
        assert result["status"] == "PENDING_HUMAN_REVIEW"
        assert "human_review_entry_id" in result

    def test_pauses_on_high_risk(self):
        payload: dict = {"request_id": "r2"}
        result = apply_human_oversight_hook(
            trust_score=0.9,
            risk_level="HIGH",
            response_payload=payload,
        )
        assert result["status"] == "PENDING_HUMAN_REVIEW"

    def test_no_pause_when_trust_ok(self):
        payload: dict = {"request_id": "r3", "status": "ok"}
        result = apply_human_oversight_hook(
            trust_score=0.95,
            risk_level="LOW",
            response_payload=payload,
        )
        assert result["status"] == "ok"

    def test_fail_close_sets_hold(self):
        payload: dict = {"request_id": "r4"}
        result = apply_human_oversight_hook(
            trust_score=0.3,
            risk_level="HIGH",
            response_payload=payload,
        )
        assert result.get("decision_blocked") is True
        assert result.get("decision_status") == "hold"
