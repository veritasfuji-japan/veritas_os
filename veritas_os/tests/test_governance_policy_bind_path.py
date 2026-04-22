"""Tests for bind-controlled governance policy update integration path."""

from __future__ import annotations

import pytest

from veritas_os.logging.encryption import generate_key
from veritas_os.policy.bind_artifacts import FinalOutcome, find_bind_receipts
from veritas_os.policy.bind_boundary_adapters import GovernancePolicyUpdateAdapter
from veritas_os.policy.governance_policy_update import update_governance_policy_with_bind_boundary


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


def _policy_store() -> tuple[dict[str, object], list[dict[str, object]]]:
    state = {
        "version": "1",
        "updated_at": "2026-04-20T12:00:00Z",
        "updated_by": "api",
        "fuji_rules": {"pii_check": True, "self_harm_block": True},
    }
    history: list[dict[str, object]] = []
    return state, history


def _reader_factory(state: dict[str, object]):
    return lambda: dict(state)


def _updater_factory(state: dict[str, object], history: list[dict[str, object]]):
    def _update(patch: dict[str, object]) -> dict[str, object]:
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(state.get(key), dict):
                merged = dict(state[key])
                merged.update(value)
                state[key] = merged
            else:
                state[key] = value
        history.append(dict(state))
        return dict(state)

    return _update


def _rollback_factory(state: dict[str, object], history: list[dict[str, object]]):
    def _rollback(target_policy: dict[str, object], **_kwargs) -> dict[str, object]:
        state.clear()
        state.update(target_policy)
        history.append(dict(state))
        return dict(state)

    return _rollback


def _execute(**overrides):
    state, history = _policy_store()
    kwargs = {
        "decision_id": "dec-gov-1",
        "request_id": "req-gov-1",
        "actor_identity": "operator",
        "policy_snapshot_id": "policy-v1",
        "decision_hash": "h" * 64,
        "policy_patch": {"fuji_rules": {"pii_check": False}},
        "policy_reader": _reader_factory(state),
        "policy_updater": _updater_factory(state, history),
        "policy_rollback": _rollback_factory(state, history),
        "append_trustlog": False,
    }
    kwargs.update(overrides)
    return update_governance_policy_with_bind_boundary(**kwargs), state, history


def test_governance_policy_update_bind_committed() -> None:
    receipt, state, history = _execute()
    assert receipt.final_outcome is FinalOutcome.COMMITTED
    assert state["fuji_rules"]["pii_check"] is False
    assert history


def test_governance_policy_update_bind_blocked() -> None:
    receipt, state, _history = _execute(
        approval_context={"governance_policy_update_approved": False}
    )
    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert state["fuji_rules"]["pii_check"] is True


def test_governance_policy_update_bind_escalated_when_signal_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        GovernancePolicyUpdateAdapter,
        "assess_runtime_risk",
        lambda self, intent, snapshot: None,
    )
    receipt, _state, _history = _execute(
        policy_lineage={"bind_adjudication": {"missing_signal_default": "escalate"}}
    )
    assert receipt.final_outcome is FinalOutcome.ESCALATED


def test_governance_policy_update_uses_governance_bind_policy_surface(monkeypatch) -> None:
    monkeypatch.setattr(
        GovernancePolicyUpdateAdapter,
        "assess_runtime_risk",
        lambda self, intent, snapshot: None,
    )
    receipt, _state, _history = _execute(
        governance_policy={"bind_adjudication": {"missing_signal_default": "escalate"}}
    )
    assert receipt.final_outcome is FinalOutcome.ESCALATED


def test_governance_policy_update_bind_rolled_back_on_postcondition_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        GovernancePolicyUpdateAdapter,
        "verify_postconditions",
        lambda self, intent, snapshot: False,
    )
    receipt, state, history = _execute()
    assert receipt.final_outcome is FinalOutcome.ROLLED_BACK
    assert state["fuji_rules"]["pii_check"] is True
    assert len(history) >= 2


def test_governance_policy_update_bind_precondition_failed() -> None:
    receipt, _state, _history = _execute(decision_id="")
    assert receipt.final_outcome is FinalOutcome.PRECONDITION_FAILED


def test_governance_policy_update_bind_persists_receipt_lineage(trustlog_env) -> None:
    receipt, _state, _history = _execute(
        decision_id="dec-gov-persist",
        request_id="req-gov-persist",
        execution_intent_id="ei-gov-persist",
        bind_receipt_id="br-gov-persist",
        append_trustlog=True,
    )
    assert receipt.final_outcome is FinalOutcome.COMMITTED

    by_decision = find_bind_receipts(decision_id="dec-gov-persist")
    by_intent = find_bind_receipts(execution_intent_id="ei-gov-persist")
    by_receipt = find_bind_receipts(bind_receipt_id="br-gov-persist")

    assert len(by_decision) == 1
    assert len(by_intent) == 1
    assert len(by_receipt) == 1
    assert by_receipt[0].bind_receipt_id == "br-gov-persist"


def test_governance_policy_update_bind_backward_compatible_execute_call() -> None:
    state, history = _policy_store()
    receipt = update_governance_policy_with_bind_boundary(
        decision_id="dec-gov-legacy",
        request_id="req-gov-legacy",
        actor_identity="legacy",
        policy_snapshot_id="policy-v1",
        decision_hash="h" * 64,
        policy_patch={"fuji_rules": {"pii_check": False}},
        policy_reader=_reader_factory(state),
        policy_updater=_updater_factory(state, history),
        append_trustlog=False,
    )
    assert receipt.final_outcome is FinalOutcome.COMMITTED
    assert state["fuji_rules"]["pii_check"] is False


def test_governance_policy_update_bind_ignores_legacy_approval_metadata() -> None:
    receipt, state, _history = _execute(
        policy_patch={
            "fuji_rules": {"pii_check": False},
            "approval": {"approved_by": "reviewer"},
        }
    )
    assert receipt.final_outcome is FinalOutcome.COMMITTED
    assert state["fuji_rules"]["pii_check"] is False
