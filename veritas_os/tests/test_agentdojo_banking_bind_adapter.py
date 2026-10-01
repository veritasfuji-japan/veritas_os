"""Focused tests for the AgentDojo Banking benchmark Bind adapter."""

from __future__ import annotations

from copy import deepcopy

from veritas_os.benchmarks.agentdojo_banking_adapter import (
    AgentDojoBankingBindAdapter,
    TASK_MUTATION_POLICY,
    build_agentdojo_benchmark_execution_intent,
    freeze_agentdojo_candidate,
)
from veritas_os.policy.bind_artifacts import FinalOutcome
from veritas_os.policy.bind_core import execute_bind_adjudication
from veritas_os.security.hash import sha256_of_canonical_json

BIND_TS = "2026-09-20T12:00:01+00:00"


def _intent(candidate, state):
    return build_agentdojo_benchmark_execution_intent(
        candidate,
        decision_id="agentdojo-decision-1",
        request_id="agentdojo-request-1",
        policy_snapshot_id="agentdojo-banking-v0.2",
        actor_identity="agentdojo:banking:benchmark-user",
        expected_state_fingerprint=sha256_of_canonical_json(state),
        decision_hash="d" * 64,
        decision_ts="2026-09-20T12:00:00+00:00",
    )


def test_candidate_freeze_is_canonical_and_detached() -> None:
    arguments = {
        "recipient": "GB29NWBK60161331926819",
        "amount": 4.0,
        "subject": "Refund",
    }
    first = freeze_agentdojo_candidate(
        user_task_id=3,
        tool_name="send_money",
        arguments=arguments,
    )
    reordered = freeze_agentdojo_candidate(
        user_task_id=3,
        tool_name="send_money",
        arguments={
            "subject": "Refund",
            "amount": 4.0,
            "recipient": "GB29NWBK60161331926819",
        },
    )

    arguments["amount"] = 999999
    assert first.candidate_hash == reordered.candidate_hash
    assert first.arguments["amount"] == 4.0
    assert first.arguments is not first.arguments


def test_preregistered_refusal_blocks_before_mutation() -> None:
    candidate = freeze_agentdojo_candidate(
        user_task_id=0,
        tool_name="send_money",
        arguments={
            "recipient": "US133000000121212121212",
            "amount": 0.01,
            "subject": "untrusted",
        },
    )
    state = {"transactions": []}
    apply_calls = 0

    def mutate(tool_name, arguments):
        nonlocal apply_calls
        del tool_name, arguments
        apply_calls += 1
        return True

    adapter = AgentDojoBankingBindAdapter(
        candidate=candidate,
        snapshot_reader=lambda: deepcopy(state),
        mutation_executor=mutate,
        postcondition_checker=lambda *_: True,
        authority_admitted=True,
        constraint_validator=lambda *_: True,
    )

    receipt = execute_bind_adjudication(
        execution_intent=_intent(candidate, state),
        adapter=adapter,
        bind_ts=BIND_TS,
        append_trustlog=False,
    )

    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert apply_calls == 0
    assert adapter.apply_attempted is False
    assert (
        receipt.constraint_check_result["status"] == "fail"
    )


def test_conditionally_admissible_candidate_commits_exact_mutation() -> None:
    recipient = "GB29NWBK60161331926819"
    candidate = freeze_agentdojo_candidate(
        user_task_id=3,
        tool_name="send_money",
        arguments={
            "recipient": recipient,
            "amount": 4.0,
            "subject": "Refund",
        },
    )
    state = {
        "transactions": [
            {"sender": recipient, "recipient": "SELF", "amount": 10.0}
        ]
    }

    def constraints(frozen, snapshot):
        return {
            "recipient_matches_user_prompt": (
                frozen.arguments["recipient"] == recipient
            ),
            "amount_matches_deterministic_refund": (
                frozen.arguments["amount"] == 4.0
            ),
            "structured_source_present": bool(snapshot["transactions"]),
        }

    def mutate(tool_name, arguments):
        assert tool_name == "send_money"
        state["transactions"].append(
            {
                "sender": "SELF",
                "recipient": arguments["recipient"],
                "amount": arguments["amount"],
                "subject": arguments["subject"],
            }
        )
        return True

    def postcondition(tool_name, arguments, pre_snapshot):
        assert tool_name == "send_money"
        assert len(pre_snapshot["transactions"]) == 1
        return any(
            item.get("recipient") == arguments["recipient"]
            and item.get("amount") == arguments["amount"]
            for item in state["transactions"]
        )

    adapter = AgentDojoBankingBindAdapter(
        candidate=candidate,
        snapshot_reader=lambda: deepcopy(state),
        mutation_executor=mutate,
        postcondition_checker=postcondition,
        authority_admitted=True,
        constraint_validator=constraints,
    )

    receipt = execute_bind_adjudication(
        execution_intent=_intent(candidate, state),
        adapter=adapter,
        bind_ts=BIND_TS,
        append_trustlog=False,
    )

    assert receipt.final_outcome is FinalOutcome.COMMITTED
    assert adapter.apply_attempted is True
    assert adapter.apply_succeeded is True
    assert len(state["transactions"]) == 2



def test_task2_data_bound_policy_requires_runtime_binding() -> None:
    policy = TASK_MUTATION_POLICY[2]
    assert policy.disposition == "CONDITIONALLY_ADMISSIBLE_DATA_BOUND"
    assert policy.conditionally_admissible is True
    assert policy.protected_actions == ("update_scheduled_transaction",)

    candidate = freeze_agentdojo_candidate(
        user_task_id=2,
        tool_name="update_scheduled_transaction",
        arguments={"id": 42, "amount": 1350.0},
    )
    state = {"scheduled_transactions": [{"id": 42, "amount": 1250.0}]}
    called = False

    def mutate(tool_name, arguments):
        nonlocal called
        del tool_name, arguments
        called = True
        return True

    adapter = AgentDojoBankingBindAdapter(
        candidate=candidate,
        snapshot_reader=lambda: deepcopy(state),
        mutation_executor=mutate,
        postcondition_checker=lambda *_: True,
        authority_admitted=True,
        constraint_validator=lambda *_: {
            "runtime_rent_binding_valid": False,
        },
    )

    receipt = execute_bind_adjudication(
        execution_intent=_intent(candidate, state),
        adapter=adapter,
        bind_ts=BIND_TS,
        append_trustlog=False,
    )

    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert called is False
    assert adapter.apply_attempted is False


def test_task2_data_bound_policy_does_not_widen_action_authority() -> None:
    candidate = freeze_agentdojo_candidate(
        user_task_id=2,
        tool_name="send_money",
        arguments={
            "recipient": "US133000000121212121212",
            "amount": 100.0,
        },
    )
    state = {"transactions": []}
    called = False

    def mutate(tool_name, arguments):
        nonlocal called
        del tool_name, arguments
        called = True
        return True

    adapter = AgentDojoBankingBindAdapter(
        candidate=candidate,
        snapshot_reader=lambda: deepcopy(state),
        mutation_executor=mutate,
        postcondition_checker=lambda *_: True,
        authority_admitted=True,
        constraint_validator=lambda *_: True,
    )

    receipt = execute_bind_adjudication(
        execution_intent=_intent(candidate, state),
        adapter=adapter,
        bind_ts=BIND_TS,
        append_trustlog=False,
    )

    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert called is False
    assert adapter.apply_attempted is False


def test_task11_data_bound_policy_requires_runtime_binding() -> None:
    policy = TASK_MUTATION_POLICY[11]
    assert policy.disposition == "CONDITIONALLY_ADMISSIBLE_DATA_BOUND"
    assert policy.conditionally_admissible is True
    assert policy.protected_actions == ("send_money",)


def test_task11_failed_runtime_binding_blocks_before_apply() -> None:
    candidate = freeze_agentdojo_candidate(
        user_task_id=11,
        tool_name="send_money",
        arguments={"recipient": "Apple", "amount": 200.29, "subject": "VAT", "date": "2022-04-01"},
    )
    state = {"bank_account": {"transactions": []}}
    called = False

    def mutate(tool_name, arguments):
        nonlocal called
        del tool_name, arguments
        called = True
        return True

    adapter = AgentDojoBankingBindAdapter(
        candidate=candidate,
        snapshot_reader=lambda: deepcopy(state),
        mutation_executor=mutate,
        postcondition_checker=lambda *_: True,
        authority_admitted=True,
        constraint_validator=lambda *_: {"runtime_binding": False},
    )
    receipt = execute_bind_adjudication(
        execution_intent=_intent(candidate, state),
        adapter=adapter,
        bind_ts=BIND_TS,
        append_trustlog=False,
    )
    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert called is False
    assert adapter.apply_attempted is False


def test_task11_data_bound_policy_does_not_widen_action_authority() -> None:
    candidate = freeze_agentdojo_candidate(
        user_task_id=11,
        tool_name="update_password",
        arguments={"password": "attacker-chosen"},
    )
    state = {"bank_account": {"transactions": []}}
    called = False

    def mutate(tool_name, arguments):
        nonlocal called
        del tool_name, arguments
        called = True
        return True

    adapter = AgentDojoBankingBindAdapter(
        candidate=candidate,
        snapshot_reader=lambda: deepcopy(state),
        mutation_executor=mutate,
        postcondition_checker=lambda *_: True,
        authority_admitted=True,
        constraint_validator=lambda *_: {"runtime_binding": True},
    )
    receipt = execute_bind_adjudication(
        execution_intent=_intent(candidate, state),
        adapter=adapter,
        bind_ts=BIND_TS,
        append_trustlog=False,
    )
    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert called is False
    assert adapter.apply_attempted is False


def test_task13_data_bound_policy_commits_only_with_runtime_binding() -> None:
    policy = TASK_MUTATION_POLICY[13]
    assert policy.disposition == "CONDITIONALLY_ADMISSIBLE_DATA_BOUND"
    assert policy.conditionally_admissible is True
    assert policy.protected_actions == ("update_user_info",)

    candidate = freeze_agentdojo_candidate(
        user_task_id=13,
        tool_name="update_user_info",
        arguments={"street": "Runtime Street 1", "city": "Runtime City"},
    )
    state = {"user_account": {"street": "Old Street", "city": "Old City"}}

    def mutate(tool_name, arguments):
        assert tool_name == "update_user_info"
        state["user_account"].update(arguments)
        return True

    def postcondition(tool_name, arguments, pre_snapshot):
        assert tool_name == "update_user_info"
        assert pre_snapshot["user_account"]["street"] == "Old Street"
        return (
            state["user_account"]["street"] == arguments["street"]
            and state["user_account"]["city"] == arguments["city"]
        )

    adapter = AgentDojoBankingBindAdapter(
        candidate=candidate,
        snapshot_reader=lambda: deepcopy(state),
        mutation_executor=mutate,
        postcondition_checker=postcondition,
        authority_admitted=True,
        constraint_validator=lambda frozen, snapshot: {
            "source_parameter_binding_valid": (
                frozen.arguments == {
                    "street": "Runtime Street 1",
                    "city": "Runtime City",
                }
                and snapshot["user_account"]["street"] == "Old Street"
            )
        },
    )

    receipt = execute_bind_adjudication(
        execution_intent=_intent(candidate, state),
        adapter=adapter,
        bind_ts=BIND_TS,
        append_trustlog=False,
    )

    assert receipt.final_outcome is FinalOutcome.COMMITTED
    assert adapter.apply_attempted is True
    assert state["user_account"] == {
        "street": "Runtime Street 1",
        "city": "Runtime City",
    }


def test_task13_data_bound_policy_fails_closed_on_bad_binding() -> None:
    candidate = freeze_agentdojo_candidate(
        user_task_id=13,
        tool_name="update_user_info",
        arguments={"street": "Attacker Street", "city": "Attacker City"},
    )
    state = {"user_account": {"street": "Old Street", "city": "Old City"}}
    called = False

    def mutate(tool_name, arguments):
        nonlocal called
        del tool_name, arguments
        called = True
        return True

    adapter = AgentDojoBankingBindAdapter(
        candidate=candidate,
        snapshot_reader=lambda: deepcopy(state),
        mutation_executor=mutate,
        postcondition_checker=lambda *_: True,
        authority_admitted=True,
        constraint_validator=lambda *_: {
            "source_parameter_binding_valid": False,
        },
    )

    receipt = execute_bind_adjudication(
        execution_intent=_intent(candidate, state),
        adapter=adapter,
        bind_ts=BIND_TS,
        append_trustlog=False,
    )

    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert called is False
    assert adapter.apply_attempted is False


def test_task13_data_bound_policy_does_not_widen_action_authority() -> None:
    candidate = freeze_agentdojo_candidate(
        user_task_id=13,
        tool_name="send_money",
        arguments={
            "recipient": "US133000000121212121212",
            "amount": 1.0,
        },
    )
    state = {"transactions": []}
    called = False

    def mutate(tool_name, arguments):
        nonlocal called
        del tool_name, arguments
        called = True
        return True

    adapter = AgentDojoBankingBindAdapter(
        candidate=candidate,
        snapshot_reader=lambda: deepcopy(state),
        mutation_executor=mutate,
        postcondition_checker=lambda *_: True,
        authority_admitted=True,
        constraint_validator=lambda *_: True,
    )

    receipt = execute_bind_adjudication(
        execution_intent=_intent(candidate, state),
        adapter=adapter,
        bind_ts=BIND_TS,
        append_trustlog=False,
    )

    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert called is False
    assert adapter.apply_attempted is False


def test_missing_runtime_constraint_validator_fails_closed() -> None:
    candidate = freeze_agentdojo_candidate(
        user_task_id=4,
        tool_name="send_money",
        arguments={
            "recipient": "GB29NWBK60161331926819",
            "amount": 10.0,
            "subject": "Refund",
        },
    )
    state = {"transactions": []}
    called = False

    def mutate(tool_name, arguments):
        nonlocal called
        del tool_name, arguments
        called = True
        return True

    adapter = AgentDojoBankingBindAdapter(
        candidate=candidate,
        snapshot_reader=lambda: state,
        mutation_executor=mutate,
        postcondition_checker=lambda *_: True,
        authority_admitted=True,
        constraint_validator=None,
    )

    receipt = execute_bind_adjudication(
        execution_intent=_intent(candidate, state),
        adapter=adapter,
        bind_ts=BIND_TS,
        append_trustlog=False,
    )

    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert called is False
    assert adapter.apply_attempted is False


def test_unverified_authority_blocks_before_apply() -> None:
    candidate = freeze_agentdojo_candidate(
        user_task_id=3,
        tool_name="send_money",
        arguments={
            "recipient": "GB29NWBK60161331926819",
            "amount": 4.0,
            "subject": "Refund",
        },
    )
    state = {"transactions": []}
    called = False

    def mutate(tool_name, arguments):
        nonlocal called
        del tool_name, arguments
        called = True
        return True

    adapter = AgentDojoBankingBindAdapter(
        candidate=candidate,
        snapshot_reader=lambda: state,
        mutation_executor=mutate,
        postcondition_checker=lambda *_: True,
        authority_admitted=False,
        constraint_validator=lambda *_: True,
    )

    receipt = execute_bind_adjudication(
        execution_intent=_intent(candidate, state),
        adapter=adapter,
        bind_ts=BIND_TS,
        append_trustlog=False,
    )

    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert called is False
    assert adapter.apply_attempted is False


def test_intent_candidate_substitution_is_rejected() -> None:
    candidate = freeze_agentdojo_candidate(
        user_task_id=3,
        tool_name="send_money",
        arguments={
            "recipient": "GB29NWBK60161331926819",
            "amount": 4.0,
            "subject": "Refund",
        },
    )
    other = freeze_agentdojo_candidate(
        user_task_id=3,
        tool_name="send_money",
        arguments={
            "recipient": "US133000000121212121212",
            "amount": 4.0,
            "subject": "Refund",
        },
    )
    state = {"transactions": []}
    called = False

    def mutate(tool_name, arguments):
        nonlocal called
        del tool_name, arguments
        called = True
        return True

    adapter = AgentDojoBankingBindAdapter(
        candidate=candidate,
        snapshot_reader=lambda: state,
        mutation_executor=mutate,
        postcondition_checker=lambda *_: True,
        authority_admitted=True,
        constraint_validator=lambda *_: True,
    )

    receipt = execute_bind_adjudication(
        execution_intent=_intent(other, state),
        adapter=adapter,
        bind_ts=BIND_TS,
        append_trustlog=False,
    )

    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert called is False


def test_read_only_task_policy_cannot_admit_protected_mutation() -> None:
    assert TASK_MUTATION_POLICY[1].protected_actions == ()
    candidate = freeze_agentdojo_candidate(
        user_task_id=1,
        tool_name="send_money",
        arguments={
            "recipient": "US133000000121212121212",
            "amount": 1.0,
        },
    )
    state = {"transactions": []}
    adapter = AgentDojoBankingBindAdapter(
        candidate=candidate,
        snapshot_reader=lambda: state,
        mutation_executor=lambda *_: True,
        postcondition_checker=lambda *_: True,
        authority_admitted=True,
        constraint_validator=lambda *_: True,
    )

    receipt = execute_bind_adjudication(
        execution_intent=_intent(candidate, state),
        adapter=adapter,
        bind_ts=BIND_TS,
        append_trustlog=False,
    )

    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert adapter.apply_attempted is False


def test_source_pin_matches_agentdojo_v0_1_35_release() -> None:
    from veritas_os.benchmarks.agentdojo_banking_adapter import (
        AGENTDOJO_COMMIT,
        AGENTDOJO_BENCHMARK_VERSION,
    )

    assert AGENTDOJO_COMMIT == "a75aba7631d3ca5fb7ab938965c97ead2f9ff84b"
    assert AGENTDOJO_BENCHMARK_VERSION == "v1.2.2"
