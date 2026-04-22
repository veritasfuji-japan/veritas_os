"""Tests for bind-controlled runtime compliance config update integration path."""

from __future__ import annotations

import pytest

from veritas_os.logging.encryption import generate_key
from veritas_os.policy.bind_artifacts import FinalOutcome, find_bind_receipts
from veritas_os.policy.bind_boundary_adapters import ComplianceConfigUpdateAdapter
from veritas_os.policy.compliance_config_update import (
    update_compliance_config_with_bind_boundary,
)


@pytest.fixture()
def trustlog_env(tmp_path, monkeypatch):
    """Redirect TrustLog writes to a temporary log path."""
    from veritas_os.logging import trust_log

    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
    monkeypatch.setattr(trust_log, "LOG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(trust_log, "LOG_JSON", tmp_path / "trust_log.json", raising=False)
    monkeypatch.setattr(trust_log, "LOG_JSONL", tmp_path / "trust_log.jsonl", raising=False)
    monkeypatch.setattr(trust_log, "_append_stats", {"success": 0, "failure": 0}, raising=False)

    def _open_for_append():
        trust_log.LOG_JSONL.parent.mkdir(parents=True, exist_ok=True)
        return open(trust_log.LOG_JSONL, "a", encoding="utf-8")

    monkeypatch.setattr(trust_log, "open_trust_log_for_append", _open_for_append)
    return tmp_path


def _config_store() -> dict[str, bool | float]:
    return {"eu_ai_act_mode": False, "safety_threshold": 0.8}


def _reader_factory(state: dict[str, bool | float]):
    return lambda: dict(state)


def _updater_factory(state: dict[str, bool | float]):
    def _update(*, eu_ai_act_mode: bool, safety_threshold: float) -> dict[str, bool | float]:
        state["eu_ai_act_mode"] = bool(eu_ai_act_mode)
        state["safety_threshold"] = float(safety_threshold)
        return dict(state)

    return _update


def _execute(**overrides):
    state = _config_store()
    kwargs = {
        "decision_id": "dec-compliance-1",
        "request_id": "req-compliance-1",
        "actor_identity": "operator",
        "policy_snapshot_id": "compliance-config-v1",
        "decision_hash": "c" * 64,
        "config_patch": {"eu_ai_act_mode": True, "safety_threshold": 0.77},
        "config_reader": _reader_factory(state),
        "config_updater": _updater_factory(state),
        "append_trustlog": False,
    }
    kwargs.update(overrides)
    return update_compliance_config_with_bind_boundary(**kwargs), state


def test_compliance_config_bind_committed() -> None:
    receipt, state = _execute()
    assert receipt.final_outcome is FinalOutcome.COMMITTED
    assert state["eu_ai_act_mode"] is True
    assert state["safety_threshold"] == 0.77


def test_compliance_config_bind_blocked() -> None:
    receipt, state = _execute(approval_context={"compliance_config_update_approved": False})
    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert state["eu_ai_act_mode"] is False


def test_compliance_config_bind_escalated_when_signal_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        ComplianceConfigUpdateAdapter,
        "assess_runtime_risk",
        lambda self, intent, snapshot: None,
    )
    receipt, _state = _execute(
        policy_lineage={"bind_adjudication": {"missing_signal_default": "escalate"}}
    )
    assert receipt.final_outcome is FinalOutcome.ESCALATED


def test_compliance_config_bind_precondition_failed() -> None:
    receipt, _state = _execute(decision_id="")
    assert receipt.final_outcome is FinalOutcome.PRECONDITION_FAILED


def test_compliance_config_bind_rolled_back_on_postcondition_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        ComplianceConfigUpdateAdapter,
        "verify_postconditions",
        lambda self, intent, snapshot: False,
    )
    receipt, state = _execute()
    assert receipt.final_outcome is FinalOutcome.ROLLED_BACK
    assert state["eu_ai_act_mode"] is False
    assert state["safety_threshold"] == 0.8


def test_compliance_config_bind_apply_failed(monkeypatch) -> None:
    monkeypatch.setattr(
        ComplianceConfigUpdateAdapter,
        "apply",
        lambda self, intent, snapshot: (_ for _ in ()).throw(ValueError("invalid")),
    )
    receipt, state = _execute()
    assert receipt.final_outcome is FinalOutcome.APPLY_FAILED
    assert state["eu_ai_act_mode"] is False


def test_compliance_config_bind_persists_receipt_lineage(trustlog_env) -> None:
    receipt, _state = _execute(
        decision_id="dec-comp-persist",
        request_id="req-comp-persist",
        execution_intent_id="ei-comp-persist",
        bind_receipt_id="br-comp-persist",
        append_trustlog=True,
    )
    assert receipt.final_outcome is FinalOutcome.COMMITTED

    by_decision = find_bind_receipts(decision_id="dec-comp-persist")
    by_intent = find_bind_receipts(execution_intent_id="ei-comp-persist")
    by_receipt = find_bind_receipts(bind_receipt_id="br-comp-persist")

    assert len(by_decision) == 1
    assert len(by_intent) == 1
    assert len(by_receipt) == 1
    assert by_receipt[0].bind_receipt_id == "br-comp-persist"


def test_compliance_config_bind_backward_compatible_execute_call() -> None:
    state = _config_store()
    receipt = update_compliance_config_with_bind_boundary(
        decision_id="dec-comp-legacy",
        request_id="req-comp-legacy",
        actor_identity="legacy",
        policy_snapshot_id="compliance-config-v1",
        decision_hash="d" * 64,
        config_patch={"eu_ai_act_mode": True, "safety_threshold": 0.75},
        config_reader=_reader_factory(state),
        config_updater=_updater_factory(state),
        append_trustlog=False,
    )
    assert receipt.final_outcome is FinalOutcome.COMMITTED
    assert state["eu_ai_act_mode"] is True
