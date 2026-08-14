"""Run deterministic external-bind scenarios against a local HTTP fixture.

The fixture transport is deliberately test-only: it maps adapter-approved,
public-looking HTTPS URLs to a loopback receiver without changing the
``WebhookBindAdapter`` URL or SSRF checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from typing import Any, Mapping
from urllib.request import Request, urlopen

from veritas_os.policy.bind_artifacts import ExecutionIntent, hash_bind_receipt
from veritas_os.policy.bind_core import execute_bind_adjudication
from veritas_os.policy.webhook_bind_adapter import WebhookBindAdapter, WebhookResponse
from veritas_os.security.hash import canonical_json_dumps, sha256_of_canonical_json

FIXED_TIMESTAMP = "2026-08-13T00:00:00Z"
FIXTURE_HOST = "external-bind-poc.example.test"
BASE_URL = f"https://{FIXTURE_HOST}"
SNAPSHOT = {"case_id": "synthetic-case-001", "state": "pending"}
AFTER = {"case_id": "synthetic-case-001", "state": "review_created"}
HMAC_SECRET = b"test-only-external-bind-poc-secret"


@dataclass
class FixtureState:
    """Mutable synthetic receiver state and sanitized request observations."""

    state: dict[str, Any] = field(default_factory=lambda: dict(SNAPSHOT))
    requests: list[dict[str, Any]] = field(default_factory=list)
    fail_postcondition: bool = False


class _Handler(BaseHTTPRequestHandler):
    state: FixtureState

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/v1/decide":
            self._reply(405, {"error": "method_not_allowed"})
            return
        if self.path == "/snapshot":
            self._record(None)
            self._reply(200, self.state.state)
            return
        if self.path == "/postcondition":
            self._record(None)
            payload = dict(self.state.state)
            if self.state.fail_postcondition:
                payload["verified"] = False
            else:
                payload["verified"] = payload.get("state") == "review_created"
            self._reply(200, payload)
            return
        self._reply(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        body = self._read_body()
        if self.path == "/v1/decide":
            self._record(body)
            self._reply(
                200,
                {
                    "decision_id": "decision-synthetic-001",
                    "decision_status": "allow",
                    "chosen": "create_human_review_task",
                },
            )
            return
        if self.path == "/action":
            self._record(body)
            self.state.state = dict(AFTER)
            self._reply(200, {"accepted": True})
            return
        if self.path == "/compensate":
            self._record(body)
            self.state.state = dict(SNAPSHOT)
            self._reply(200, {"compensated": True})
            return
        self._reply(404, {"error": "not_found"})

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        value = json.loads(raw) if raw else {}
        return value if isinstance(value, dict) else {}

    def _record(self, body: dict[str, Any] | None) -> None:
        self.state.requests.append(
            {"method": self.command, "path": self.path, "body": body}
        )

    def _reply(self, status: int, body: Mapping[str, Any]) -> None:
        encoded = canonical_json_dumps(dict(body)).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        del format, args


class LocalFixture:
    """Context-managed localhost receiver that shuts down cleanly."""

    def __init__(self, *, fail_postcondition: bool = False) -> None:
        self.state = FixtureState(fail_postcondition=fail_postcondition)
        handler = type("ScenarioHandler", (_Handler,), {"state": self.state})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self) -> LocalFixture:
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


@dataclass
class FixtureTransport:
    """Test-only transport preserving the adapter request flow."""

    origin: str

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
        del allow_redirects
        if not url.startswith(BASE_URL):
            raise RuntimeError("fixture transport received an unexpected target")
        local_url = self.origin + url.removeprefix(BASE_URL)
        data = None
        if json_body is not None:
            data = canonical_json_dumps(dict(json_body)).encode("utf-8")
        request = Request(local_url, data=data, headers=dict(headers or {}), method=method)
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = json.loads(response.read().decode("utf-8"))
            return WebhookResponse(response.status, body)


def _post_decision_candidate(fixture: LocalFixture) -> dict[str, Any]:
    payload = {
        "query": "Select a synthetic case handling action",
        "options": ["create_human_review_task", "take_no_action"],
        "context": {"data_classification": "synthetic_only"},
    }
    request = Request(
        fixture.origin + "/v1/decide",
        data=canonical_json_dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=2) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _adapter(fixture: LocalFixture) -> WebhookBindAdapter:
    return WebhookBindAdapter(
        snapshot_url=BASE_URL + "/snapshot",
        action_url=BASE_URL + "/action",
        postcondition_url=BASE_URL + "/postcondition",
        compensation_url=BASE_URL + "/compensate",
        action_payload={"case_id": "synthetic-case-001", "operation": "create_review"},
        compensation_payload={"case_id": "synthetic-case-001", "operation": "undo"},
        expected_postcondition={"verified": True},
        allowed_hosts={FIXTURE_HOST},
        hmac_secret=HMAC_SECRET,
        dns_resolver=lambda hostname: ["93.184.216.34"],
        transport=FixtureTransport(fixture.origin),
    )


def run_scenario(name: str) -> dict[str, Any]:
    """Run one deterministic scenario and return reviewer-facing evidence."""
    fail_postcondition = name == "rolled-back"
    with LocalFixture(fail_postcondition=fail_postcondition) as fixture:
        decision = _post_decision_candidate(fixture)
        prepared = {
            "decision_id": decision["decision_id"],
            "execution_status": "not_executed",
            "requires_bind_adjudication": True,
        }
        approved = name != "blocked"
        intent = ExecutionIntent(
            execution_intent_id=f"intent-{name}",
            decision_id=prepared["decision_id"],
            request_id=f"request-{name}",
            policy_snapshot_id="policy-synthetic-001",
            actor_identity="synthetic-reviewer",
            target_system="synthetic_webhook",
            target_resource=f"{FIXTURE_HOST}/action",
            intended_action="create_human_review_task",
            decision_hash=sha256_of_canonical_json(decision),
            decision_ts=FIXED_TIMESTAMP,
            expected_state_fingerprint=sha256_of_canonical_json(SNAPSHOT),
            approval_context={"external_webhook_action_approved": approved},
        )
        receipt = execute_bind_adjudication(
            execution_intent=intent,
            adapter=_adapter(fixture),
            bind_ts=FIXED_TIMESTAMP,
            bind_receipt_id=f"receipt-{name}",
            append_trustlog=False,
        )
        action_posts = sum(
            item["method"] == "POST" and item["path"] == "/action"
            for item in fixture.state.requests
        )
        compensation_posts = sum(
            item["method"] == "POST" and item["path"] == "/compensate"
            for item in fixture.state.requests
        )
        return {
            "scenario": name,
            "path": [
                "Decision Candidate",
                "/v1/decide",
                "non-executing bind preparation",
                "Bind Boundary adjudication",
                "WebhookBindAdapter",
                "external effect simulation",
                "postcondition verification",
                "final bind evidence",
            ],
            "execution_intent_id": intent.execution_intent_id,
            "decision_id": intent.decision_id,
            "final_outcome": receipt.final_outcome.value,
            "idempotency_status": receipt.idempotency_status,
            "rollback_status": receipt.rollback_status,
            "target_description": _adapter(fixture).describe_target(),
            "external_post_occurred": action_posts > 0,
            "action_post_count": action_posts,
            "compensation_post_count": compensation_posts,
            "receipt_hash": hash_bind_receipt(receipt),
            "verification_result": {
                "authority": receipt.authority_check_result,
                "drift": receipt.drift_check_result,
                "reason_code": receipt.bind_reason_code,
                "postcondition_satisfied": receipt.final_outcome.value == "COMMITTED",
                "compensation_verified": receipt.rollback_status == "rolled_back",
            },
        }


def run_all(output_dir: Path) -> dict[str, dict[str, Any]]:
    """Execute all scenarios, validate outcomes, and write canonical evidence."""
    expected = {"committed": "COMMITTED", "blocked": "BLOCKED", "rolled-back": "ROLLED_BACK"}
    results = {name: run_scenario(name) for name in expected}
    for name, outcome in expected.items():
        if results[name]["final_outcome"] != outcome:
            raise RuntimeError(f"{name} produced {results[name]['final_outcome']}, expected {outcome}")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, result in results.items():
        (output_dir / f"{name}.json").write_text(
            canonical_json_dumps(result) + "\n", encoding="utf-8"
        )
    manifest = {
        "format_version": 1,
        "synthetic_data_only": True,
        "scenarios": {
            name: {"file": f"{name}.json", "final_outcome": item["final_outcome"]}
            for name, item in results.items()
        },
    }
    (output_dir / "manifest.json").write_text(
        canonical_json_dumps(manifest) + "\n", encoding="utf-8"
    )
    return results
