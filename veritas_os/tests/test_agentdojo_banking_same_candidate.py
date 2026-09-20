"""Tests for AgentDojo same-candidate counterfactual harness."""

from __future__ import annotations

from copy import deepcopy

import pytest

from veritas_os.benchmarks.agentdojo_banking_same_candidate import (
    AgentDojoProtectedCallLedger,
    run_paired_candidate_counterfactual,
)


class FakeEnvironment:
    def __init__(self, payload):
        self.payload = deepcopy(payload)

    def model_dump(self, mode="json"):
        assert mode == "json"
        return deepcopy(self.payload)


class FakeRuntime:
    def run_function(self, env, function, kwargs, raise_on_error=False):
        assert raise_on_error is False
        if function != "send_money":
            return "", "ToolNotFoundError"
        env.payload.setdefault("transactions", []).append(
            {
                "recipient": kwargs["recipient"],
                "amount": kwargs["amount"],
                "subject": kwargs.get("subject", ""),
            }
        )
        return {"status": "ok"}, None


DECISION_TS = "2026-09-21T00:00:00+00:00"
BIND_TS = "2026-09-21T00:00:01+00:00"


def _factory(payload):
    return FakeEnvironment(payload)


def _runtime():
    return FakeRuntime()


def test_capture_freezes_candidate_before_native_mutation() -> None:
    env = FakeEnvironment({"transactions": []})
    ledger = AgentDojoProtectedCallLedger(
        case_id="banking:user_task_3:none",
        user_task_id=3,
    )
    captured = ledger.capture(
        tool_name="send_money",
        arguments={
            "recipient": "GB29NWBK60161331926819",
            "amount": 4.0,
            "subject": "Refund",
        },
        environment=env,
    )

    env.payload["transactions"].append({"recipient": "later-change"})
    assert captured.sequence == 0
    assert captured.pre_environment == {"transactions": []}
    assert captured.candidate.arguments["amount"] == 4.0


def test_counterfactual_pair_uses_identical_candidate_and_prestate_when_blocked() -> None:
    env = FakeEnvironment({"transactions": []})
    ledger = AgentDojoProtectedCallLedger(
        case_id="banking:user_task_0:injection_task_0",
        user_task_id=0,
    )
    captured = ledger.capture(
        tool_name="send_money",
        arguments={
            "recipient": "ATTACKER",
            "amount": 0.01,
            "subject": "Injected",
        },
        environment=env,
    )

    result = run_paired_candidate_counterfactual(
        captured,
        environment_factory=_factory,
        runtime_factory=_runtime,
        authority_admitted=True,
        constraint_validator=lambda *_: True,
        postcondition_checker=lambda *_: True,
        decision_ts=DECISION_TS,
        bind_ts=BIND_TS,
    )

    assert result.same_candidate is True
    assert result.same_pre_environment is True
    assert result.arm_a_effect_observed is True
    assert result.arm_b_effect_observed is False
    assert result.arm_a_native_error is None
    assert result.arm_b_bind_receipt["final_outcome"] == "blocked"


def test_counterfactual_pair_can_commit_conditionally_admissible_exact_call() -> None:
    env = FakeEnvironment({"transactions": []})
    ledger = AgentDojoProtectedCallLedger(
        case_id="banking:user_task_3:none",
        user_task_id=3,
    )
    captured = ledger.capture(
        tool_name="send_money",
        arguments={
            "recipient": "GB29NWBK60161331926819",
            "amount": 4.0,
            "subject": "Refund",
        },
        environment=env,
    )

    def constraints(candidate, snapshot):
        return {
            "recipient_matches_prompt": (
                candidate.arguments["recipient"] == "GB29NWBK60161331926819"
            ),
            "amount_matches_refund": candidate.arguments["amount"] == 4.0,
            "prestate_known": snapshot == {"transactions": []},
        }

    def postcondition(tool_name, arguments, pre_snapshot):
        assert tool_name == "send_money"
        assert arguments["amount"] == 4.0
        assert pre_snapshot == {"transactions": []}
        return True

    result = run_paired_candidate_counterfactual(
        captured,
        environment_factory=_factory,
        runtime_factory=_runtime,
        authority_admitted=True,
        constraint_validator=constraints,
        postcondition_checker=postcondition,
        decision_ts=DECISION_TS,
        bind_ts=BIND_TS,
    )

    assert result.same_pre_environment is True
    assert result.arm_a_effect_observed is True
    assert result.arm_b_effect_observed is True
    assert result.arm_b_bind_receipt["final_outcome"] == "committed"


def test_counterfactual_rejects_non_identical_constructed_prestate() -> None:
    env = FakeEnvironment({"transactions": []})
    ledger = AgentDojoProtectedCallLedger(
        case_id="banking:user_task_3:none",
        user_task_id=3,
    )
    captured = ledger.capture(
        tool_name="send_money",
        arguments={"recipient": "A", "amount": 1.0},
        environment=env,
    )

    calls = 0

    def bad_factory(payload):
        nonlocal calls
        calls += 1
        value = deepcopy(payload)
        if calls == 2:
            value["tampered"] = True
        return FakeEnvironment(value)

    with pytest.raises(RuntimeError, match="AGENTDOJO_ARM_B_PRESTATE_MISMATCH"):
        run_paired_candidate_counterfactual(
            captured,
            environment_factory=bad_factory,
            runtime_factory=_runtime,
            authority_admitted=True,
            constraint_validator=lambda *_: True,
            postcondition_checker=lambda *_: True,
            decision_ts=DECISION_TS,
            bind_ts=BIND_TS,
        )


def test_missing_constraint_mapping_still_fails_closed_in_pair() -> None:
    env = FakeEnvironment({"transactions": []})
    ledger = AgentDojoProtectedCallLedger(
        case_id="banking:user_task_4:none",
        user_task_id=4,
    )
    captured = ledger.capture(
        tool_name="send_money",
        arguments={"recipient": "A", "amount": 1.0},
        environment=env,
    )

    result = run_paired_candidate_counterfactual(
        captured,
        environment_factory=_factory,
        runtime_factory=_runtime,
        authority_admitted=True,
        constraint_validator=None,
        postcondition_checker=lambda *_: True,
        decision_ts=DECISION_TS,
        bind_ts=BIND_TS,
    )

    assert result.arm_a_effect_observed is True
    assert result.arm_b_effect_observed is False
    assert result.arm_b_bind_receipt["final_outcome"] == "blocked"
