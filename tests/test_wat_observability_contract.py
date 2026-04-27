from __future__ import annotations

from pathlib import Path

from veritas_os.api.routes_decide import _attach_wat_contract_fields
from veritas_os.audit import wat_events
from veritas_os.security.wat_verifier import validate_local


def _configure_wat_store(monkeypatch, tmp_path: Path) -> None:
    events_path = tmp_path / "wat_events_observability.jsonl"
    monkeypatch.setattr(wat_events, "WAT_EVENTS_JSONL", events_path)
    monkeypatch.setattr(
        wat_events,
        "append_signed_decision",
        lambda *_args, **_kwargs: {"decision_id": "stub", "payload_hash": "hash"},
    )


def test_replay_binding_failure_stays_in_detail_not_minimal_summary() -> None:
    payload = {"request_id": "req-replay-1"}
    wat_shadow = {
        "operator_verbosity": "expanded",
        "validation_status": "invalid",
        "admissibility_state": "non_admissible",
        "affected_lanes": ["wat_shadow"],
        "event_ts": "2026-04-27T00:00:00Z",
        "correlation_id": "corr-1",
        "warning_context": "wat_shadow_warning",
        "warning_correlation_id": "corr-1",
        "event_lane_details": {
            "replay_binding_failure": {
                "reason": "replay_binding_incomplete",
                "required": True,
                "escalation_threshold": 4,
            },
            "revocation_transition_trace": {"status": "active", "source": "wat_events"},
        },
    }

    _attach_wat_contract_fields(payload, wat_shadow)

    summary = payload["wat_operator_summary"]
    detail = payload["wat_operator_detail"]
    assert "event_lane_details" not in summary
    assert (
        detail["verifier_output_raw"]["event_lane_details"][
            "replay_binding_failure"
        ]["reason"]
        == "replay_binding_incomplete"
    )


def test_revocation_transition_trace_stays_in_detail_not_minimal_summary() -> None:
    payload = {"request_id": "req-revoke-1"}
    wat_shadow = {
        "operator_verbosity": "expanded",
        "validation_status": "revoked_pending",
        "admissibility_state": "warning_only_shadow",
        "affected_lanes": ["wat_shadow"],
        "event_ts": "2026-04-27T00:00:00Z",
        "correlation_id": "corr-2",
        "warning_context": "wat_shadow_warning",
        "warning_correlation_id": "corr-2",
        "event_lane_details": {
            "revocation_transition_trace": {
                "status": "revoked_pending",
                "event_type": "wat_revocation_pending",
                "event_id": "evt-1",
                "source": "wat_events",
            }
        },
    }

    _attach_wat_contract_fields(payload, wat_shadow)

    summary = payload["wat_operator_summary"]
    detail = payload["wat_operator_detail"]
    assert "revocation_transition_trace" not in summary
    assert (
        detail["verifier_output_raw"]["event_lane_details"][
            "revocation_transition_trace"
        ]["event_type"]
        == "wat_revocation_pending"
    )


def test_retention_boundary_assertion_telemetry_recorded(monkeypatch, tmp_path: Path) -> None:
    _configure_wat_store(monkeypatch, tmp_path)
    event = wat_events.persist_wat_validation_event(
        wat_id="wat-retention-1",
        actor="test",
        event_type="wat_validation_failed",
        status="warning",
        details={
            "request_id": "req-retention-1",
            "observable_digest": "digest-without-ref",
        },
    )

    assertion = event["details"]["retention_boundary_assertion"]
    assert assertion["outcome"] == "passed"
    assert assertion["failed_reasons"] == []


def test_partial_validation_confirmation_failure_observable_in_logs_and_events(caplog) -> None:
    caplog.set_level("WARNING")
    signed_wat = {
        "claims": {
            "psid_full": "psid-1",
            "action_digest": "action-1",
            "observable_digest": "obs-1",
            "issuance_ts": 100,
            "expiry_ts": 200,
            "nonce": "nonce-1",
            "session_id": "session-1",
        },
        "signature": "sig",
    }
    result = validate_local(
        signed_wat=signed_wat,
        psid_full_local="psid-1",
        action_digest_local="action-1",
        observable_refs_local=None,
        observable_digest_local="obs-1",
        issuance_ts_local=100,
        expiry_ts_local=200,
        execution_nonce="nonce-1",
        session_id="session-1",
        revocation_state={"status": "active"},
        config={
            "signature_verifier": lambda _claims, _sig: True,
            "allow_partial_validation": True,
            "partial_validation_requires_confirmation": True,
            "partial_validation_confirmation": False,
        },
        now_ts=120,
        replay_cache=set(),
    )

    assert result["failure_type"] == "partial_validation_confirmation_required"
    assert "partial-validation confirmation failure" in caplog.text


def test_minimal_summary_shape_remains_unchanged() -> None:
    payload = {"request_id": "req-minimal-1"}
    wat_shadow = {
        "operator_verbosity": "expanded",
        "validation_status": "invalid",
        "admissibility_state": "warning_only_shadow",
        "affected_lanes": ["wat_shadow"],
        "event_ts": "2026-04-27T00:00:00Z",
        "correlation_id": "corr-3",
        "warning_context": "wat_shadow_warning",
        "warning_correlation_id": "corr-3",
        "event_lane_details": {"replay_binding_failure": {"reason": "replay_binding_missing"}},
    }

    _attach_wat_contract_fields(payload, wat_shadow)
    summary_keys = set(payload["wat_operator_summary"].keys())
    assert summary_keys == {
        "integrity_severity",
        "affected_lanes",
        "event_ts",
        "correlation_id",
        "warning_context",
        "warning_correlation_id",
        "operator_verbosity",
    }
