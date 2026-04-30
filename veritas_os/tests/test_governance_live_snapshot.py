"""Tests for governance live snapshot endpoint and builder behavior."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

import veritas_os.api.server as server
from veritas_os.api.governance_live_snapshot import (
    _normalize_bind_outcome,
    _normalize_state,
    build_governance_live_snapshot,
)
from veritas_os.policy.bind_artifacts import BindReceipt, FinalOutcome

_TEST_KEY = "gov-live-snapshot-test-key"
os.environ["VERITAS_API_KEY"] = _TEST_KEY
_AUTH = {"X-API-Key": _TEST_KEY, "X-Role": "admin"}

client = TestClient(server.app)


@pytest.fixture(autouse=True)
def _reset_auth(monkeypatch):
    monkeypatch.setenv("VERITAS_API_KEY", _TEST_KEY)
    monkeypatch.setenv("VERITAS_API_KEYS", "[{\"key\":\"gov-live-snapshot-test-key\",\"role\":\"auditor\"}]")


def test_governance_live_snapshot_returns_200(monkeypatch):
    receipt = BindReceipt(final_outcome=FinalOutcome.COMMITTED, bind_ts="2026-04-30T00:00:00Z")
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [receipt],
    )

    response = client.get("/v1/governance/live-snapshot", headers=_AUTH)
    assert response.status_code == 200
    payload = response.json()
    assert "governance_layer_snapshot" in payload


def test_governance_live_snapshot_has_required_fields(monkeypatch):
    receipt = BindReceipt(final_outcome=FinalOutcome.ESCALATED, bind_ts="2026-04-30T00:00:00Z")
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [receipt],
    )

    snapshot = client.get("/v1/governance/live-snapshot", headers=_AUTH).json()["governance_layer_snapshot"]
    for key in (
        "participation_state",
        "preservation_state",
        "intervention_viability",
        "bind_outcome",
        "source",
        "updated_at",
    ):
        assert key in snapshot


def test_governance_live_snapshot_uses_latest_receipt(monkeypatch):
    old = BindReceipt(final_outcome=FinalOutcome.BLOCKED, bind_ts="2026-04-29T00:00:00Z")
    latest = BindReceipt(final_outcome=FinalOutcome.COMMITTED, bind_ts="2026-04-30T00:00:00Z")
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [old, latest],
    )

    snapshot = client.get("/v1/governance/live-snapshot", headers=_AUTH).json()["governance_layer_snapshot"]
    assert snapshot["source"] == "backend_live_snapshot"
    assert snapshot["bind_outcome"] == "COMMITTED"
    assert snapshot["updated_at"] == "2026-04-30T00:00:00Z"




def test_governance_live_snapshot_includes_bind_metadata(monkeypatch):
    receipt = BindReceipt(
        bind_receipt_id="br_1",
        execution_intent_id="ei_1",
        decision_id="dec_1",
        final_outcome=FinalOutcome.ESCALATED,
        bind_ts="2026-04-30T00:00:00Z",
        bind_reason_code="AUTHORITY_MISSING",
        bind_failure_reason="Authority evidence missing",
        target_path="/v1/governance/policy",
        target_type="governance_policy",
        target_path_type="governance_policy_update",
        target_label="Governance policy",
        operator_surface="governance",
        relevant_ui_href="/governance",
        authority_check_result={"status": "fail"},
        constraint_check_result={"status": "pass"},
        drift_check_result={"status": "pass"},
        risk_check_result={"status": "escalate"},
        failure_category="authority",
        rollback_status="not_started",
        retry_safety="manual_review_required",
    )
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [receipt],
    )

    snapshot = client.get("/v1/governance/live-snapshot", headers=_AUTH).json()["governance_layer_snapshot"]

    assert snapshot["source"] == "backend_live_snapshot"
    assert snapshot["bind_outcome"] == "ESCALATED"
    assert snapshot["bind_receipt_id"] == "br_1"
    assert snapshot["execution_intent_id"] == "ei_1"
    assert snapshot["decision_id"] == "dec_1"
    assert snapshot["target_path"] == "/v1/governance/policy"
    assert snapshot["target_type"] == "governance_policy"
    assert isinstance(snapshot["target_label"], str)
    assert snapshot["target_label"]
    assert snapshot["operator_surface"] == "governance"
    assert snapshot["relevant_ui_href"] == "/governance"
    assert snapshot["bind_reason_code"] == "AUTHORITY_MISSING"
    assert snapshot["bind_failure_reason"] == "Authority evidence missing"
    assert snapshot["failure_category"] == "authority"
    assert snapshot["rollback_status"] == "not_started"
    assert snapshot["retry_safety"] == "manual_review_required"
    assert snapshot["authority_check_result"] == {"status": "fail"}
    assert snapshot["constraint_check_result"] == {"status": "pass"}
    assert snapshot["drift_check_result"] == {"status": "pass"}
    assert snapshot["risk_check_result"] == {"status": "escalate"}
    assert snapshot["bind_summary"]["bind_outcome"] == "ESCALATED"


def test_governance_live_snapshot_optional_metadata_defaults_to_none(monkeypatch):
    receipt = BindReceipt(
        final_outcome=FinalOutcome.BLOCKED,
        bind_ts="2026-04-30T00:00:00Z",
    )
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [receipt],
    )

    snapshot = client.get("/v1/governance/live-snapshot", headers=_AUTH).json()["governance_layer_snapshot"]

    assert snapshot["source"] == "backend_live_snapshot"
    assert snapshot["bind_outcome"] == "BLOCKED"
    assert isinstance(snapshot["bind_receipt_id"], str)
    assert snapshot["execution_intent_id"] in (None, "")
    assert snapshot["decision_id"] in (None, "")
    assert snapshot["bind_failure_reason"] is None
    assert snapshot["failure_category"] is None

def test_governance_live_snapshot_degraded_when_no_receipts(monkeypatch):
    monkeypatch.setattr("veritas_os.api.governance_live_snapshot.find_bind_receipts", lambda: [])

    snapshot = client.get("/v1/governance/live-snapshot", headers=_AUTH).json()["governance_layer_snapshot"]
    assert snapshot["source"] == "degraded_no_recent_governance_artifact"
    assert snapshot["bind_outcome"] == "UNKNOWN"
    assert snapshot["pre_bind_source"] == "none"
    assert snapshot["pre_bind_detection_summary"] is None
    assert snapshot["pre_bind_preservation_summary"] is None


def test_governance_live_snapshot_degraded_when_artifact_unavailable(monkeypatch):
    def _raise():
        raise RuntimeError("no storage")

    monkeypatch.setattr("veritas_os.api.governance_live_snapshot.find_bind_receipts", _raise)
    response = client.get("/v1/governance/live-snapshot", headers=_AUTH)
    assert response.status_code == 200
    snapshot = response.json()["governance_layer_snapshot"]
    assert snapshot["source"] == "degraded_artifact_retrieval_failed"
    assert snapshot["bind_outcome"] == "UNKNOWN"
    assert snapshot["pre_bind_source"] == "none"
    assert snapshot["pre_bind_detection_summary"] is None
    assert snapshot["pre_bind_preservation_summary"] is None


def test_governance_live_snapshot_vocabulary(monkeypatch):
    class _FakeReceipt:
        def to_dict(self):
            return {
                "participation_state": "INVALID",
                "preservation_state": "",
                "intervention_viability": "NOT_A_STATE",
                "final_outcome": "not_real",
                "bind_ts": "2026-04-30T00:00:00Z",
            }

    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [_FakeReceipt()],
    )
    snapshot = client.get("/v1/governance/live-snapshot", headers=_AUTH).json()["governance_layer_snapshot"]
    assert snapshot["participation_state"] == "unknown"
    assert snapshot["preservation_state"] == "unknown"
    assert snapshot["intervention_viability"] == "unknown"
    assert snapshot["bind_outcome"] == "UNKNOWN"
    assert snapshot["pre_bind_source"] == "none"
    assert snapshot["pre_bind_detection_summary"] is None
    assert snapshot["pre_bind_preservation_summary"] is None


def test_builder_uses_latest_receipt(monkeypatch):
    old = BindReceipt(final_outcome=FinalOutcome.BLOCKED, bind_ts="2026-04-29T00:00:00Z")
    latest = BindReceipt(final_outcome=FinalOutcome.ESCALATED, bind_ts="2026-04-30T00:00:00Z")
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [old, latest],
    )

    snapshot = build_governance_live_snapshot()["governance_layer_snapshot"]
    assert snapshot["source"] == "backend_live_snapshot"
    assert snapshot["bind_outcome"] == "ESCALATED"
    assert snapshot["updated_at"] == "2026-04-30T00:00:00Z"


def test_builder_degraded_on_exception(monkeypatch):
    def _raise():
        raise RuntimeError("boom")

    monkeypatch.setattr("veritas_os.api.governance_live_snapshot.find_bind_receipts", _raise)
    snapshot = build_governance_live_snapshot()["governance_layer_snapshot"]
    assert snapshot["source"] == "degraded_artifact_retrieval_failed"
    assert snapshot["bind_outcome"] == "UNKNOWN"
    assert snapshot["pre_bind_source"] == "none"
    assert snapshot["pre_bind_detection_summary"] is None
    assert snapshot["pre_bind_preservation_summary"] is None


def test_normalizers_invalid_values():
    assert _normalize_state("invalid", allowed={"known", "unknown"}) == "unknown"
    assert _normalize_state(None, allowed={"known", "unknown"}) == "unknown"
    assert _normalize_bind_outcome("not_real") == "UNKNOWN"
    assert _normalize_bind_outcome(None) == "UNKNOWN"


def test_governance_live_snapshot_defaults_pre_bind_to_unknown_when_missing(monkeypatch):
    receipt = BindReceipt(final_outcome=FinalOutcome.COMMITTED, bind_ts="2026-04-30T00:00:00Z")
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [receipt],
    )

    snapshot = client.get("/v1/governance/live-snapshot", headers=_AUTH).json()["governance_layer_snapshot"]
    assert snapshot["participation_state"] == "unknown"
    assert snapshot["preservation_state"] == "unknown"
    assert snapshot["intervention_viability"] == "unknown"
    assert snapshot["pre_bind_source"] == "none"
    assert snapshot["pre_bind_detection_summary"] is None
    assert snapshot["pre_bind_preservation_summary"] is None
    assert snapshot["pre_bind_detection_detail"] is None
    assert snapshot["pre_bind_preservation_detail"] is None


def test_governance_live_snapshot_reads_pre_bind_from_receipt_payload(monkeypatch):
    class _PreBindReceipt:
        def to_dict(self):
            return {
                "final_outcome": "COMMITTED",
                "bind_ts": "2026-04-30T00:00:00Z",
                "participation_state": "decision_shaping",
                "preservation_state": "degrading",
                "intervention_viability": "minimal",
                "pre_bind_detection_summary": {"participation_state": "decision_shaping"},
                "pre_bind_preservation_summary": {"preservation_state": "degrading"},
                "pre_bind_detection_detail": {"aggregate_index": 0.88},
                "pre_bind_preservation_detail": {"intervention_viability": {"level": "minimal"}},
            }

    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [_PreBindReceipt()],
    )

    snapshot = client.get("/v1/governance/live-snapshot", headers=_AUTH).json()["governance_layer_snapshot"]
    assert snapshot["participation_state"] == "decision_shaping"
    assert snapshot["preservation_state"] == "degrading"
    assert snapshot["intervention_viability"] == "minimal"
    assert snapshot["pre_bind_source"] == "latest_bind_receipt"
    assert snapshot["pre_bind_detection_summary"] == {"participation_state": "decision_shaping"}
    assert snapshot["pre_bind_preservation_summary"] == {"preservation_state": "degrading"}


def test_governance_live_snapshot_prefers_dedicated_pre_bind_source(monkeypatch):
    class _ReceiptWithFallbackData:
        def to_dict(self):
            return {
                "final_outcome": "COMMITTED",
                "bind_ts": "2026-04-30T00:00:00Z",
                "participation_state": "informative",
                "preservation_state": "open",
                "intervention_viability": "high",
            }

    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [_ReceiptWithFallbackData()],
    )
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot._resolve_pre_bind_from_trustlog_recent_decision",
        lambda _identity=None: {
            "participation_state": "decision_shaping",
            "preservation_state": "degrading",
            "intervention_viability": "minimal",
            "pre_bind_source": "trustlog_recent_decision",
            "pre_bind_detection_summary": {"participation_state": "decision_shaping"},
            "pre_bind_preservation_summary": {"preservation_state": "degrading"},
            "pre_bind_detection_detail": {"aggregate_index": 0.88},
            "pre_bind_preservation_detail": {"intervention_viability": {"level": "minimal"}},
        },
    )

    snapshot = client.get("/v1/governance/live-snapshot", headers=_AUTH).json()["governance_layer_snapshot"]
    assert snapshot["bind_outcome"] == "COMMITTED"
    assert snapshot["participation_state"] == "decision_shaping"
    assert snapshot["preservation_state"] == "degrading"
    assert snapshot["intervention_viability"] == "minimal"
    assert snapshot["pre_bind_source"] == "trustlog_recent_decision"


def test_governance_live_snapshot_pre_bind_retrieval_failure_is_non_fatal(monkeypatch):
    receipt = BindReceipt(final_outcome=FinalOutcome.COMMITTED, bind_ts="2026-04-30T00:00:00Z")
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [receipt],
    )

    def _raise():
        raise RuntimeError("trustlog unavailable")

    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot._resolve_pre_bind_from_trustlog_recent_decision",
        _raise,
    )

    response = client.get("/v1/governance/live-snapshot", headers=_AUTH)
    assert response.status_code == 200
    snapshot = response.json()["governance_layer_snapshot"]
    assert snapshot["bind_outcome"] == "COMMITTED"
    assert snapshot["pre_bind_source"] == "pre_bind_artifact_retrieval_failed"
    assert snapshot["participation_state"] == "unknown"
    assert snapshot["pre_bind_detection_summary"] is None

def test_governance_live_snapshot_normalizes_malformed_pre_bind_objects(monkeypatch):
    class _MalformedPreBindReceipt:
        def to_dict(self):
            return {
                "final_outcome": "BLOCKED",
                "bind_ts": "2026-04-30T00:00:00Z",
                "participation_state": "not_real",
                "preservation_state": "invalid",
                "intervention_viability": "bad",
                "pre_bind_detection_summary": "bad",
                "pre_bind_preservation_summary": [1, 2],
            }

    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [_MalformedPreBindReceipt()],
    )

    response = client.get("/v1/governance/live-snapshot", headers=_AUTH)
    assert response.status_code == 200
    snapshot = response.json()["governance_layer_snapshot"]
    assert snapshot["participation_state"] == "unknown"
    assert snapshot["preservation_state"] == "unknown"
    assert snapshot["intervention_viability"] == "unknown"
    assert snapshot["pre_bind_detection_summary"] is None
    assert snapshot["pre_bind_preservation_summary"] is None


def test_governance_live_snapshot_pre_bind_enrichment_exception_is_non_fatal(monkeypatch):
    receipt = BindReceipt(final_outcome=FinalOutcome.COMMITTED, bind_ts="2026-04-30T00:00:00Z")
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [receipt],
    )

    def _raise(_payload):
        raise RuntimeError("pre-bind boom")

    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.resolve_latest_pre_bind_snapshot_fields",
        _raise,
    )

    response = client.get("/v1/governance/live-snapshot", headers=_AUTH)
    assert response.status_code == 200
    snapshot = response.json()["governance_layer_snapshot"]
    assert snapshot["bind_outcome"] == "COMMITTED"
    assert snapshot["pre_bind_source"] == "malformed_pre_bind_artifact"
    assert snapshot["participation_state"] == "unknown"


def test_governance_live_snapshot_requires_auth():
    response = client.get("/v1/governance/live-snapshot")
    assert response.status_code in {401, 403}


def test_governance_live_snapshot_degraded_when_to_dict_raises(monkeypatch):
    class BrokenReceipt:
        def to_dict(self):
            raise RuntimeError("broken receipt")

    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [BrokenReceipt()],
    )

    response = client.get("/v1/governance/live-snapshot", headers=_AUTH)
    assert response.status_code == 200
    snapshot = response.json()["governance_layer_snapshot"]
    assert snapshot["source"] == "degraded_invalid_latest_bind_receipt"
    assert snapshot["bind_outcome"] == "UNKNOWN"
    assert snapshot["pre_bind_source"] == "none"
    assert snapshot["pre_bind_detection_summary"] is None
    assert snapshot["pre_bind_preservation_summary"] is None


def test_governance_live_snapshot_degraded_when_to_dict_not_dict(monkeypatch):
    class MalformedReceipt:
        def to_dict(self):
            return "not a dict"

    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [MalformedReceipt()],
    )

    response = client.get("/v1/governance/live-snapshot", headers=_AUTH)
    assert response.status_code == 200
    snapshot = response.json()["governance_layer_snapshot"]
    assert snapshot["source"] == "degraded_invalid_latest_bind_receipt"
    assert snapshot["bind_outcome"] == "UNKNOWN"
    assert snapshot["pre_bind_source"] == "none"
    assert snapshot["pre_bind_detection_summary"] is None
    assert snapshot["pre_bind_preservation_summary"] is None


def test_governance_live_snapshot_degraded_when_enrich_raises(monkeypatch):
    receipt = BindReceipt(final_outcome=FinalOutcome.COMMITTED, bind_ts="2026-04-30T00:00:00Z")
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [receipt],
    )

    def _raise(_payload):
        raise RuntimeError("enrich failed")

    monkeypatch.setattr("veritas_os.api.governance_live_snapshot.enrich_bind_receipt_payload", _raise)

    response = client.get("/v1/governance/live-snapshot", headers=_AUTH)
    assert response.status_code == 200
    snapshot = response.json()["governance_layer_snapshot"]
    assert snapshot["source"] == "degraded_bind_summary_enrichment_failed"
    assert snapshot["bind_outcome"] == "UNKNOWN"
    assert snapshot["pre_bind_source"] == "none"
    assert snapshot["pre_bind_detection_summary"] is None
    assert snapshot["pre_bind_preservation_summary"] is None


def test_governance_live_snapshot_degraded_when_bind_summary_raises(monkeypatch):
    receipt = BindReceipt(final_outcome=FinalOutcome.COMMITTED, bind_ts="2026-04-30T00:00:00Z")
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [receipt],
    )

    def _raise(_payload):
        raise RuntimeError("summary failed")

    monkeypatch.setattr("veritas_os.api.governance_live_snapshot.build_bind_summary_from_receipt", _raise)

    response = client.get("/v1/governance/live-snapshot", headers=_AUTH)
    assert response.status_code == 200
    snapshot = response.json()["governance_layer_snapshot"]
    assert snapshot["source"] == "degraded_bind_summary_enrichment_failed"


def test_governance_live_snapshot_degraded_when_reason_resolver_raises(monkeypatch):
    receipt = BindReceipt(final_outcome=FinalOutcome.COMMITTED, bind_ts="2026-04-30T00:00:00Z")
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [receipt],
    )

    def _raise(_payload):
        raise RuntimeError("reason failed")

    monkeypatch.setattr("veritas_os.api.governance_live_snapshot.resolve_bind_reason_code", _raise)

    response = client.get("/v1/governance/live-snapshot", headers=_AUTH)
    assert response.status_code == 200
    snapshot = response.json()["governance_layer_snapshot"]
    assert snapshot["source"] == "degraded_bind_summary_enrichment_failed"


def test_builder_degraded_for_broken_to_dict(monkeypatch):
    class BrokenReceipt:
        def to_dict(self):
            raise RuntimeError("broken")

    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [BrokenReceipt()],
    )
    snapshot = build_governance_live_snapshot()["governance_layer_snapshot"]
    assert snapshot["source"] == "degraded_invalid_latest_bind_receipt"


def test_builder_degraded_for_enrich_exception(monkeypatch):
    receipt = BindReceipt(final_outcome=FinalOutcome.COMMITTED, bind_ts="2026-04-30T00:00:00Z")
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [receipt],
    )

    def _raise(_payload):
        raise RuntimeError("enrich failed")

    monkeypatch.setattr("veritas_os.api.governance_live_snapshot.enrich_bind_receipt_payload", _raise)
    snapshot = build_governance_live_snapshot()["governance_layer_snapshot"]
    assert snapshot["source"] == "degraded_bind_summary_enrichment_failed"


def test_builder_degraded_for_bind_summary_exception(monkeypatch):
    receipt = BindReceipt(final_outcome=FinalOutcome.COMMITTED, bind_ts="2026-04-30T00:00:00Z")
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.find_bind_receipts",
        lambda: [receipt],
    )

    def _raise(_payload):
        raise RuntimeError("summary failed")

    monkeypatch.setattr("veritas_os.api.governance_live_snapshot.build_bind_summary_from_receipt", _raise)
    snapshot = build_governance_live_snapshot()["governance_layer_snapshot"]
    assert snapshot["source"] == "degraded_bind_summary_enrichment_failed"


def test_pre_bind_prefers_decision_match_over_newer_recent(monkeypatch):
    receipt = BindReceipt(
        final_outcome=FinalOutcome.COMMITTED,
        bind_ts="2026-04-30T00:00:00Z",
        decision_id="dec_target",
    )
    monkeypatch.setattr("veritas_os.api.governance_live_snapshot.find_bind_receipts", lambda: [receipt])
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.load_trust_log",
        lambda limit=20: [
            {
                "decision_id": "dec_other",
                "participation_state": "informative",
            },
            {
                "decision_id": "dec_target",
                "participation_state": "decision_shaping",
            },
        ],
    )

    snapshot = client.get("/v1/governance/live-snapshot", headers=_AUTH).json()["governance_layer_snapshot"]
    assert snapshot["pre_bind_source"] == "trustlog_matching_decision"
    assert snapshot["participation_state"] == "decision_shaping"


def test_pre_bind_uses_request_match_when_decision_absent(monkeypatch):
    receipt = BindReceipt(final_outcome=FinalOutcome.COMMITTED, bind_ts="2026-04-30T00:00:00Z")
    monkeypatch.setattr("veritas_os.api.governance_live_snapshot.find_bind_receipts", lambda: [receipt])
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.enrich_bind_receipt_payload",
        lambda payload: {**payload, "request_id": "req_target"},
    )
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.load_trust_log",
        lambda limit=20: [{"request_id": "req_target", "participation_state": "participatory"}],
    )

    snapshot = client.get("/v1/governance/live-snapshot", headers=_AUTH).json()["governance_layer_snapshot"]
    assert snapshot["pre_bind_source"] == "trustlog_matching_request"


def test_pre_bind_uses_execution_intent_match_as_third_priority(monkeypatch):
    receipt = BindReceipt(
        final_outcome=FinalOutcome.COMMITTED,
        bind_ts="2026-04-30T00:00:00Z",
        execution_intent_id="ei_target",
    )
    monkeypatch.setattr("veritas_os.api.governance_live_snapshot.find_bind_receipts", lambda: [receipt])
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.load_trust_log",
        lambda limit=20: [{"execution_intent_id": "ei_target", "participation_state": "participatory"}],
    )

    snapshot = client.get("/v1/governance/live-snapshot", headers=_AUTH).json()["governance_layer_snapshot"]
    assert snapshot["pre_bind_source"] == "trustlog_matching_execution_intent"


def test_pre_bind_uses_recent_fallback_when_no_identity_match(monkeypatch):
    receipt = BindReceipt(final_outcome=FinalOutcome.COMMITTED, bind_ts="2026-04-30T00:00:00Z", decision_id="dec_x")
    monkeypatch.setattr("veritas_os.api.governance_live_snapshot.find_bind_receipts", lambda: [receipt])
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.load_trust_log",
        lambda limit=20: [{"decision_id": "dec_y", "participation_state": "informative"}],
    )
    snapshot = client.get("/v1/governance/live-snapshot", headers=_AUTH).json()["governance_layer_snapshot"]
    assert snapshot["pre_bind_source"] == "trustlog_recent_decision"


def test_pre_bind_matching_malformed_artifact_returns_unknown(monkeypatch):
    receipt = BindReceipt(final_outcome=FinalOutcome.COMMITTED, bind_ts="2026-04-30T00:00:00Z", decision_id="dec_bad")
    monkeypatch.setattr("veritas_os.api.governance_live_snapshot.find_bind_receipts", lambda: [receipt])
    monkeypatch.setattr(
        "veritas_os.api.governance_live_snapshot.load_trust_log",
        lambda limit=20: [{"decision_id": "dec_bad", "participation_state": "bad", "pre_bind_detection_summary": "bad"}],
    )

    snapshot = client.get("/v1/governance/live-snapshot", headers=_AUTH).json()["governance_layer_snapshot"]
    assert snapshot["pre_bind_source"] == "malformed_pre_bind_artifact"
    assert snapshot["participation_state"] == "unknown"
