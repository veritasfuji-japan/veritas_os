"""Tests for EU AI Act remaining-gap improvements.

GAP-04: Art. 50(2) — Machine-readable AI content watermark
GAP-05: Art. 10  — Data lineage tracking in memory system
GAP-14: Art. 14  — Human review timeout / SLA expiry enforcement
GAP-16: Art. 15  — Degraded mode for LLM unavailability
"""
from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta

import pytest

from veritas_os.core.eu_ai_act_compliance_module import (
    HumanReviewQueue,
    build_ai_content_watermark,
    build_degraded_response,
    classify_annex_iii_risk,
    eu_compliance_pipeline,
    AI_DISCLOSURE_TEXT,
    AI_REGULATION_NOTICE,
    EUComplianceConfig,
)


# =====================================================================
# GAP-04: Art. 50(2) — Machine-readable AI content watermark
# =====================================================================
class TestAIContentWatermark:
    """GAP-04 — C2PA-compatible watermark metadata."""

    def test_watermark_contains_required_fields(self) -> None:
        wm = build_ai_content_watermark(decision_id="test-001")
        assert wm["ai_generated"] is True
        assert wm["standard"] == "C2PA-compatible"
        assert wm["producer"] == "VERITAS OS"
        assert wm["decision_id"] == "test-001"
        assert wm["regulation"] == "EU AI Act (EU) 2024/1689"
        assert "content_credentials" in wm
        assert wm["content_credentials"]["assertion"] == "c2pa.ai_generated"

    def test_watermark_has_timestamp(self) -> None:
        wm = build_ai_content_watermark(decision_id="ts-test")
        assert "timestamp" in wm
        # Should parse as ISO format
        datetime.fromisoformat(wm["timestamp"])

    def test_watermark_has_signature(self) -> None:
        wm = build_ai_content_watermark(decision_id="sig-test")
        sig = wm["content_credentials"]["signature"]
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA-256 hex

    def test_watermark_custom_model(self) -> None:
        wm = build_ai_content_watermark(decision_id="m1", model="custom-model")
        assert wm["model"] == "custom-model"

    def test_watermark_integrated_in_pipeline(self) -> None:
        @eu_compliance_pipeline(config=EUComplianceConfig())
        def dummy_decide(**kwargs):
            return {"output": "hello", "trust_score": 0.95}

        result = dummy_decide(prompt="simple question")
        assert "ai_content_watermark" in result
        assert result["ai_content_watermark"]["ai_generated"] is True
        assert result["ai_content_watermark"]["standard"] == "C2PA-compatible"


# =====================================================================
# GAP-14: Art. 14 — Human review timeout / SLA expiry enforcement
# =====================================================================
class TestHumanReviewTimeout:
    """GAP-14 — SLA expiry enforcement for pending human reviews."""

    def setup_method(self) -> None:
        HumanReviewQueue.clear_for_testing()

    def test_check_expired_entries_empty_queue(self) -> None:
        expired = HumanReviewQueue.check_expired_entries()
        assert expired == []

    def test_non_expired_entry_stays_pending(self) -> None:
        entry = HumanReviewQueue.enqueue(
            decision_payload={"request_id": "fresh"},
            reason="test",
        )
        expired = HumanReviewQueue.check_expired_entries()
        assert expired == []
        # Verify still pending
        e = HumanReviewQueue.get_entry(entry["entry_id"])
        assert e is not None
        assert e["status"] == "pending"

    def test_expired_entry_is_marked(self) -> None:
        entry = HumanReviewQueue.enqueue(
            decision_payload={"request_id": "old"},
            reason="test",
        )
        # Manually set deadline in the past
        with HumanReviewQueue._lock:
            for e in HumanReviewQueue._queue:
                if e["entry_id"] == entry["entry_id"]:
                    e["sla_deadline"] = (
                        datetime.now(timezone.utc) - timedelta(seconds=10)
                    ).isoformat()

        expired = HumanReviewQueue.check_expired_entries()
        assert len(expired) == 1
        assert expired[0]["entry_id"] == entry["entry_id"]
        assert expired[0]["status"] == "expired"
        assert "expired_at" in expired[0]

    def test_already_reviewed_entry_not_expired(self) -> None:
        entry = HumanReviewQueue.enqueue(
            decision_payload={"request_id": "reviewed"},
            reason="test",
        )
        HumanReviewQueue.review(
            entry["entry_id"], approved=True, reviewer="human"
        )
        # Set past deadline
        with HumanReviewQueue._lock:
            for e in HumanReviewQueue._queue:
                if e["entry_id"] == entry["entry_id"]:
                    e["sla_deadline"] = (
                        datetime.now(timezone.utc) - timedelta(seconds=10)
                    ).isoformat()

        expired = HumanReviewQueue.check_expired_entries()
        assert expired == []

    def test_expired_entry_cannot_be_reviewed(self) -> None:
        entry = HumanReviewQueue.enqueue(
            decision_payload={"request_id": "late"},
            reason="test",
        )
        # Expire the entry
        with HumanReviewQueue._lock:
            for e in HumanReviewQueue._queue:
                if e["entry_id"] == entry["entry_id"]:
                    e["sla_deadline"] = (
                        datetime.now(timezone.utc) - timedelta(seconds=10)
                    ).isoformat()
        HumanReviewQueue.check_expired_entries()

        # Try to review — should fail (status is "expired", not "pending")
        result = HumanReviewQueue.review(
            entry["entry_id"], approved=True, reviewer="human"
        )
        assert result is None


# =====================================================================
# GAP-16: Art. 15 — Degraded mode for LLM unavailability
# =====================================================================
class TestDegradedMode:
    """GAP-16 — Safe fallback when LLM is unavailable."""

    def test_degraded_response_structure(self) -> None:
        resp = build_degraded_response(reason="LLM timeout")
        assert resp["degraded_mode"] is True
        assert resp["decision_status"] == "abstain"
        assert resp["status"] == "DEGRADED"
        assert resp["degraded_reason"] == "LLM timeout"
        assert resp["ai_disclosure"] == AI_DISCLOSURE_TEXT
        assert resp["regulation_notice"] == AI_REGULATION_NOTICE
        assert "recommendation" in resp

    def test_degraded_response_includes_risk_assessment(self) -> None:
        resp = build_degraded_response(
            reason="connection error",
            prompt="hiring decision for candidate",
        )
        assert "eu_risk_assessment" in resp
        # "hiring" keyword triggers risk assessment
        assert resp["eu_risk_assessment"]["risk_level"] in ("HIGH", "MEDIUM")

    def test_degraded_response_with_custom_risk(self) -> None:
        custom_risk = {"risk_level": "HIGH", "risk_score": 0.95}
        resp = build_degraded_response(
            reason="API error",
            risk_assessment=custom_risk,
        )
        assert resp["eu_risk_assessment"] == custom_risk

    def test_degraded_response_output_is_empty(self) -> None:
        resp = build_degraded_response(reason="test")
        assert resp["output"] == ""


# =====================================================================
# GAP-05: Art. 10 — Data lineage in memory system
# =====================================================================
class TestDataLineage:
    """GAP-05 — Data lineage tracking in VectorMemory.add()."""

    def test_lineage_auto_generated(self) -> None:
        """When no lineage is provided, a default is generated."""
        from unittest.mock import MagicMock, patch
        import numpy as np

        mock_model = MagicMock()
        mock_model.encode.return_value = [np.zeros(384)]

        # Patch the transitive import that requires httpx
        import sys
        httpx_stub = MagicMock()
        with patch.dict(sys.modules, {"httpx": httpx_stub}):
            from veritas_os.core.memory import VectorMemory

            mem = VectorMemory.__new__(VectorMemory)
            mem.model = mock_model
            mem.documents = []
            mem.embeddings = None
            mem._id_counter = 0
            mem._lock = __import__("threading").RLock()
            mem.index_path = None

            result = mem.add("semantic", "test text")
            assert result is True
            assert len(mem.documents) == 1
            doc = mem.documents[0]
            assert "lineage" in doc
            assert doc["lineage"]["source"] == "semantic"
            assert "ingested_at" in doc["lineage"]

    def test_lineage_from_meta(self) -> None:
        """When meta["lineage"] is provided, it is used."""
        from unittest.mock import MagicMock, patch
        import numpy as np

        mock_model = MagicMock()
        mock_model.encode.return_value = [np.zeros(384)]

        import sys
        httpx_stub = MagicMock()
        with patch.dict(sys.modules, {"httpx": httpx_stub}):
            from veritas_os.core.memory import VectorMemory

            mem = VectorMemory.__new__(VectorMemory)
            mem.model = mock_model
            mem.documents = []
            mem.embeddings = None
            mem._id_counter = 0
            mem._lock = __import__("threading").RLock()
            mem.index_path = None

            custom_lineage = {
                "source": "user_upload",
                "original_format": "csv",
                "transformations": ["anonymised", "tokenised"],
            }
            result = mem.add("episodic", "data", meta={"lineage": custom_lineage})
            assert result is True
            doc = mem.documents[0]
            assert doc["lineage"] == custom_lineage
