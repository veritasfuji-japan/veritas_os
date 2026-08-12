"""Tests for the fail-closed webhook bind adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping

import pytest

from veritas_os.policy.bind_artifacts import (
    ExecutionIntent,
    FinalOutcome,
    canonical_bind_receipt_json,
)
from veritas_os.policy.bind_core import BindAdapterContract, execute_bind_adjudication
from veritas_os.policy.webhook_bind_adapter import WebhookBindAdapter, WebhookResponse
from veritas_os.security.hash import sha256_of_canonical_json


class TransportError(RuntimeError):
    pass


@dataclass
class FakeTransport:
    responses: dict[tuple[str, str], list[WebhookResponse | Exception]]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
        timeout: float,
        allow_redirects: bool = False,
    ) -> WebhookResponse:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers or {}),
                "json_body": dict(json_body or {}),
                "timeout": timeout,
                "allow_redirects": allow_redirects,
            }
        )
        queued = self.responses.get((method, url), [])
        if not queued:
            raise TransportError(f"unexpected call: {method} {url}")
        response = queued.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def count(self, method: str, url: str) -> int:
        return sum(
            1 for call in self.calls if call["method"] == method and call["url"] == url
        )


PUBLIC_IP = ["93.184.216.34"]
SNAPSHOT_URL = "https://hooks.example.test/snapshot?token=secret"
ACTION_URL = "https://hooks.example.test/action?token=secret"
POSTCONDITION_URL = "https://hooks.example.test/postcondition?token=secret"
COMPENSATION_URL = "https://hooks.example.test/compensate?token=secret"


def intent(**overrides: Any) -> ExecutionIntent:
    values = {
        "execution_intent_id": "ei-1",
        "decision_id": "dec-1",
        "request_id": "req-1",
        "policy_snapshot_id": "snap-1",
        "actor_identity": "ops",
        "target_system": "external_webhook",
        "target_resource": "hooks.example.test/action",
        "intended_action": "external_webhook_action",
        "decision_hash": "a" * 64,
        "decision_ts": "2026-07-13T00:00:00Z",
        "expected_state_fingerprint": sha256_of_canonical_json({"state": "before"}),
        "approval_context": {"external_webhook_action_approved": True},
    }
    values.update(overrides)
    return ExecutionIntent(**values)


def transport_for_success() -> FakeTransport:
    return FakeTransport(
        {
            ("GET", SNAPSHOT_URL): [
                WebhookResponse(200, {"state": "before"}),
                WebhookResponse(200, {"state": "after"}),
            ],
            ("POST", ACTION_URL): [WebhookResponse(200, {"accepted": True})],
            ("GET", POSTCONDITION_URL): [
                WebhookResponse(200, {"state": "after", "nested": {"ok": True}})
            ],
        }
    )


def adapter(
    transport: FakeTransport | None = None, **overrides: Any
) -> WebhookBindAdapter:
    values = {
        "snapshot_url": SNAPSHOT_URL,
        "action_url": ACTION_URL,
        "postcondition_url": POSTCONDITION_URL,
        "action_payload": {"op": "set", "value": 1},
        "expected_postcondition": {"nested": {"ok": True}},
        "allowed_hosts": {"hooks.example.test"},
        "hmac_secret": "super-secret",
        "transport": transport or transport_for_success(),
        "dns_resolver": lambda hostname: PUBLIC_IP,
    }
    values.update(overrides)
    return WebhookBindAdapter(**values)


def test_contract_fingerprint_and_sanitized_description() -> None:
    subject = adapter()
    assert isinstance(subject, BindAdapterContract)
    snapshot = {"b": 2, "a": 1}
    assert subject.fingerprint_state(snapshot) == sha256_of_canonical_json(snapshot)
    assert "token=secret" not in subject.describe_target()
    assert "super-secret" not in repr(subject)


def test_authority_requires_explicit_true() -> None:
    subject = adapter()
    assert subject.validate_authority(intent(), {}) is True
    assert (
        subject.validate_authority(
            intent(approval_context={"external_webhook_action_approved": False}), {}
        )
        is False
    )
    assert subject.validate_authority(intent(approval_context={}), {}) is False
    assert subject.validate_authority(intent(approval_context=None), {}) is False


@pytest.mark.parametrize(
    "approval_context",
    [
        {"external_webhook_action_approved": False},
        {},
        None,
    ],
)
def test_authority_failure_prevents_action_post(approval_context: Any) -> None:
    fake = transport_for_success()
    receipt = execute_bind_adjudication(
        execution_intent=intent(approval_context=approval_context),
        adapter=adapter(fake),
        append_trustlog=False,
    )
    assert receipt.final_outcome is FinalOutcome.BLOCKED
    assert fake.count("POST", ACTION_URL) == 0


def test_successful_governed_execution_commits_and_posts_once() -> None:
    fake = transport_for_success()
    receipt = execute_bind_adjudication(
        execution_intent=intent(),
        adapter=adapter(fake),
        append_trustlog=False,
    )
    assert receipt.final_outcome is FinalOutcome.COMMITTED
    assert fake.count("POST", ACTION_URL) == 1
    call = next(call for call in fake.calls if call["method"] == "POST")
    assert call["allow_redirects"] is False
    assert call["headers"]["X-Veritas-Decision-Id"] == "dec-1"
    assert call["headers"]["X-Veritas-Execution-Intent-Id"] == "ei-1"
    assert call["headers"]["X-Veritas-Signature"].startswith("sha256=")
    assert "super-secret" not in json.dumps(call)


def test_constraint_and_runtime_risk_failures_prevent_action_post() -> None:
    for subject in [
        adapter(action_payload=[]),
        adapter(action_url="https://evil.example.test/action"),
    ]:
        fake = subject.transport
        receipt = execute_bind_adjudication(
            execution_intent=intent(),
            adapter=subject,
            append_trustlog=False,
        )
        assert receipt.final_outcome is FinalOutcome.BLOCKED
        assert fake.count("POST", ACTION_URL) == 0


@pytest.mark.parametrize(
    "responses,expected",
    [
        (
            {("GET", SNAPSHOT_URL): [TransportError("timeout")]},
            FinalOutcome.SNAPSHOT_FAILED,
        ),
        (
            {("GET", SNAPSHOT_URL): [WebhookResponse(200, [])]},
            FinalOutcome.SNAPSHOT_FAILED,
        ),
        (
            {("GET", SNAPSHOT_URL): [WebhookResponse(500, {})]},
            FinalOutcome.SNAPSHOT_FAILED,
        ),
    ],
)
def test_snapshot_failures_fail_closed(
    responses: dict[tuple[str, str], list[Any]], expected: FinalOutcome
) -> None:
    fake = FakeTransport(responses)
    receipt = execute_bind_adjudication(
        execution_intent=intent(),
        adapter=adapter(fake),
        append_trustlog=False,
    )
    assert receipt.final_outcome is expected
    assert fake.count("POST", ACTION_URL) == 0


@pytest.mark.parametrize(
    "action_response",
    [
        TransportError("timeout"),
        WebhookResponse(500, {}),
        WebhookResponse(302, {"redirect": True}),
        WebhookResponse(200, []),
    ],
)
def test_action_failures_are_not_committed_and_do_not_retry(
    action_response: Any,
) -> None:
    fake = FakeTransport(
        {
            ("GET", SNAPSHOT_URL): [WebhookResponse(200, {"state": "before"})],
            ("POST", ACTION_URL): [action_response],
        }
    )
    receipt = execute_bind_adjudication(
        execution_intent=intent(),
        adapter=adapter(fake),
        append_trustlog=False,
    )
    assert receipt.final_outcome is FinalOutcome.APPLY_FAILED
    assert fake.count("POST", ACTION_URL) == 1


@pytest.mark.parametrize(
    "postcondition_response",
    [
        TransportError("timeout"),
        WebhookResponse(500, {}),
        WebhookResponse(200, []),
        WebhookResponse(200, {"nested": {"ok": False}}),
    ],
)
def test_postcondition_failures_do_not_commit_without_compensation(
    postcondition_response: Any,
) -> None:
    fake = FakeTransport(
        {
            ("GET", SNAPSHOT_URL): [WebhookResponse(200, {"state": "before"})],
            ("POST", ACTION_URL): [WebhookResponse(200, {"accepted": True})],
            ("GET", POSTCONDITION_URL): [postcondition_response],
        }
    )
    receipt = execute_bind_adjudication(
        execution_intent=intent(),
        adapter=adapter(fake),
        append_trustlog=False,
    )
    assert receipt.final_outcome is FinalOutcome.ESCALATED
    assert receipt.rollback_status == "manual_intervention_required"


def test_idempotency_key_is_deterministic_and_excludes_secret() -> None:
    first = adapter(hmac_secret="secret-a")
    second = adapter(hmac_secret="secret-b")
    changed = adapter(hmac_secret="secret-a", action_payload={"op": "set", "value": 2})
    assert first.build_idempotency_key(intent()) == second.build_idempotency_key(
        intent()
    )
    assert first.build_idempotency_key(intent()) != changed.build_idempotency_key(
        intent()
    )


def test_replay_does_not_duplicate_external_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import veritas_os.policy.bind_core.core as core

    first_fake = transport_for_success()
    first = execute_bind_adjudication(
        execution_intent=intent(),
        adapter=adapter(first_fake),
        append_trustlog=False,
    )
    monkeypatch.setattr(core, "_idempotency_replay_enabled", lambda **_: True)
    monkeypatch.setattr(core, "_find_duplicate_bind_receipt", lambda **_: first)
    replay_fake = transport_for_success()
    replay = execute_bind_adjudication(
        execution_intent=intent(),
        adapter=adapter(replay_fake),
        append_trustlog=True,
    )
    assert replay.idempotency_status == "replayed"
    assert replay_fake.count("POST", ACTION_URL) == 0


def test_successful_compensation_reports_rolled_back() -> None:
    fake = FakeTransport(
        {
            ("GET", SNAPSHOT_URL): [
                WebhookResponse(200, {"state": "before"}),
                WebhookResponse(200, {"state": "compensated"}),
            ],
            ("POST", ACTION_URL): [WebhookResponse(200, {"accepted": True})],
            ("GET", POSTCONDITION_URL): [
                WebhookResponse(200, {"nested": {"ok": False}})
            ],
            ("POST", COMPENSATION_URL): [WebhookResponse(200, {"compensated": True})],
        }
    )
    receipt = execute_bind_adjudication(
        execution_intent=intent(),
        adapter=adapter(
            fake, compensation_url=COMPENSATION_URL, compensation_payload={"undo": True}
        ),
        append_trustlog=False,
    )
    assert receipt.final_outcome is FinalOutcome.ROLLED_BACK
    assert fake.count("POST", COMPENSATION_URL) == 1


def test_failed_compensation_does_not_claim_rollback() -> None:
    fake = FakeTransport(
        {
            ("GET", SNAPSHOT_URL): [WebhookResponse(200, {"state": "before"})],
            ("POST", ACTION_URL): [WebhookResponse(200, {"accepted": True})],
            ("GET", POSTCONDITION_URL): [
                WebhookResponse(200, {"nested": {"ok": False}})
            ],
            ("POST", COMPENSATION_URL): [WebhookResponse(500, {})],
        }
    )
    receipt = execute_bind_adjudication(
        execution_intent=intent(),
        adapter=adapter(fake, compensation_url=COMPENSATION_URL),
        append_trustlog=False,
    )
    assert receipt.final_outcome is FinalOutcome.ESCALATED
    assert receipt.rollback_status == "manual_intervention_required"


def test_unacknowledged_compensation_does_not_claim_rollback() -> None:
    fake = FakeTransport(
        {
            ("GET", SNAPSHOT_URL): [WebhookResponse(200, {"state": "before"})],
            ("POST", ACTION_URL): [WebhookResponse(200, {"accepted": True})],
            ("GET", POSTCONDITION_URL): [
                WebhookResponse(200, {"nested": {"ok": False}})
            ],
            ("POST", COMPENSATION_URL): [WebhookResponse(200, {"accepted": True})],
        }
    )
    receipt = execute_bind_adjudication(
        execution_intent=intent(),
        adapter=adapter(fake, compensation_url=COMPENSATION_URL),
        append_trustlog=False,
    )
    assert receipt.final_outcome is FinalOutcome.ESCALATED
    assert receipt.rollback_status == "manual_intervention_required"


def test_invalid_action_configuration_is_blocked_without_escaping_bind_core() -> None:
    for subject in [
        adapter(action_url="https://hooks.example.test:invalid/action"),
        adapter(action_payload={"invalid": object()}),
    ]:
        fake = subject.transport
        receipt = execute_bind_adjudication(
            execution_intent=intent(),
            adapter=subject,
            append_trustlog=False,
        )
        assert receipt.final_outcome is FinalOutcome.BLOCKED
        assert fake.count("POST", ACTION_URL) == 0


def test_resolver_exception_is_a_runtime_deny() -> None:
    def failing_resolver(hostname: str) -> list[str]:
        del hostname
        raise ValueError("resolver failed")

    fake = transport_for_success()
    receipt = execute_bind_adjudication(
        execution_intent=intent(),
        adapter=adapter(fake, dns_resolver=failing_resolver),
        append_trustlog=False,
    )
    assert receipt.final_outcome is FinalOutcome.SNAPSHOT_FAILED
    assert fake.count("POST", ACTION_URL) == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"action_url": "http://hooks.example.test/action"},
        {"action_url": "https://evil.example.test/action"},
        {"action_url": "https://user:pass@hooks.example.test/action"},
        {"action_url": "https://hooks.example.test/action#frag"},
        {"dns_resolver": lambda hostname: ["127.0.0.1"]},
        {"dns_resolver": lambda hostname: ["10.0.0.1"]},
        {"dns_resolver": lambda hostname: ["169.254.1.1"]},
    ],
)
def test_url_security_rejections_prevent_action(kwargs: dict[str, Any]) -> None:
    subject = adapter(**kwargs)
    fake = subject.transport
    receipt = execute_bind_adjudication(
        execution_intent=intent(),
        adapter=subject,
        append_trustlog=False,
    )
    assert receipt.final_outcome in {FinalOutcome.BLOCKED, FinalOutcome.SNAPSHOT_FAILED}
    assert fake.count("POST", ACTION_URL) == 0


def test_secret_absent_from_errors_and_receipt() -> None:
    fake = FakeTransport({("GET", SNAPSHOT_URL): [TransportError("super-secret")]})
    receipt = execute_bind_adjudication(
        execution_intent=intent(),
        adapter=adapter(fake),
        append_trustlog=False,
    )
    serialized = canonical_bind_receipt_json(receipt)
    assert "super-secret" not in serialized
    with pytest.raises(RuntimeError) as excinfo:
        adapter(fake)._request("GET", SNAPSHOT_URL, headers={}, json_body=None)
    assert "super-secret" not in str(excinfo.value)
    assert excinfo.value.__cause__ is None
