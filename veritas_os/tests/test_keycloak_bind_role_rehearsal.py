"""Opt-in integration proof against an isolated, disposable Keycloak server."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import json
from multiprocessing import get_all_start_methods, get_context
import os
from pathlib import Path
from secrets import token_urlsafe
import signal
import subprocess
import sys
from time import time_ns
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from veritas_os.policy import sandbox_bind_execution as execution
from veritas_os.policy import sandbox_reconciliation as reconciliation
from veritas_os.policy.bind_effect_reconciliation import (
    BindEffectStateError,
    PostgresAtomicEffectStateStore,
)
from veritas_os.policy.keycloak_dispatch_reservation import (
    get_keycloak_dispatch_intent,
    reserve_keycloak_dispatch,
)
from veritas_os.policy.keycloak_reconciliation import (
    AUDIT_PAGE_LIMIT,
    confirm_keycloak_reconciliation,
    keycloak_reconciliation_policy_digest,
    read_verified_keycloak_confirmation,
)
from veritas_os.policy.keycloak_reconciliation_observation import (
    KeycloakReconciliationObservation,
    archive_keycloak_reconciliation_observation,
    get_keycloak_reconciliation_observation,
)
from veritas_os.policy.keycloak_receipt_outcome import (
    KeycloakReceiptError,
    publish_keycloak_receipts,
    read_verified_keycloak_receipts,
)
from veritas_os.policy.keycloak_role_grant_binding import (
    ACTION,
    KeycloakRoleGrantTarget,
    build_keycloak_role_grant_binding,
    verify_keycloak_role_grant_binding,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    PostgresAtomicAuthorizationConsumptionStore,
    build_authorization_consumption_record,
)
from veritas_os.policy.native_bind_authorization import _verified_source
from veritas_os.policy.sandbox_event_store import parse_event, validate_uuid
from veritas_os.policy.sandbox_https_transport import SandboxHTTPSTransport
from veritas_os.policy.trusted_https_reconciliation import ApprovedReconciliationVerifier
from veritas_os.security.hash import sha256_of_canonical_json
from veritas_os.storage.db import close_pool
from veritas_os.tests.test_native_bind_authorization_consumption import _Revocation
from veritas_os.tests.test_saas_role_grant_bind_rehearsal import (
    READER_TOKEN, WRITER_TOKEN, WriterProvider,
)
from veritas_os.tests.test_sandbox_action_binding import contract
from veritas_os.tests.test_sandbox_action_binding_integration import issue_for_action, issue_for_payload
from veritas_os.tests.test_sandbox_pre_effect import _args, consume_fixture_authorization
from veritas_os.tests.test_sandbox_reconciliation import ReaderProvider

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("VERITAS_KEYCLOAK_REHEARSAL") != "1",
                       reason="requires a disposable local Keycloak server"),
]

ORIGIN = "http://127.0.0.1:18080"
ROLE = "report-viewer"


def expect(response: httpx.Response, status: int) -> httpx.Response:
    assert response.status_code == status
    return response


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def keycloak(request):
    """Isolate each run in a fresh realm with separate writer and reader principals."""
    realm = f"veritas-rehearsal-{uuid4().hex}"
    realm_id = str(uuid4())
    resource = f"/admin/realms/{realm}"
    with httpx.Client(base_url=ORIGIN, trust_env=False, timeout=10) as client:
        admin = expect(client.post("/realms/master/protocol/openid-connect/token", data={
            "client_id": "admin-cli",
            "grant_type": "password",
            "username": os.environ["KC_BOOTSTRAP_ADMIN_USERNAME"],
            "password": os.environ["KC_BOOTSTRAP_ADMIN_PASSWORD"],
        }), 200).json()["access_token"]
        auth = bearer(admin)
        expect(client.post("/admin/realms", headers=auth, json={
            "id": realm_id, "realm": realm, "enabled": True,
        }), 201)
        try:
            def create(path, body):
                response = expect(client.post(resource + path, headers=auth, json=body), 201)
                return response.headers["Location"].rsplit("/", 1)[1]

            application = create("/clients", {"clientId": "reports", "enabled": True})
            target = create("/users", {"username": "fixture-user", "enabled": True})
            create(f"/clients/{application}/roles", {"name": ROLE})
            role = expect(client.get(
                f"{resource}/clients/{application}/roles/{ROLE}", headers=auth,
            ), 200).json()
            managers = expect(client.get(
                f"{resource}/clients", params={"clientId": "realm-management"}, headers=auth,
            ), 200).json()
            assert len(managers) == 1
            management = managers[0]["id"]
            scopes = expect(client.get(f"{resource}/client-scopes", headers=auth), 200).json()
            admin_scope = next(scope["id"] for scope in scopes if scope["name"] == "kc-admin-api")

            def principal(name, *permissions):
                secret = token_urlsafe(32)
                app = create("/clients", {
                    "clientId": name, "enabled": True, "publicClient": False,
                    "secret": secret, "serviceAccountsEnabled": True, "fullScopeAllowed": False,
                    "standardFlowEnabled": False, "directAccessGrantsEnabled": False,
                })
                expect(client.put(
                    f"{resource}/clients/{app}/default-client-scopes/{admin_scope}",
                    headers=auth,
                ), 204)
                service_user = expect(client.get(
                    f"{resource}/clients/{app}/service-account-user", headers=auth,
                ), 200).json()["id"]
                roles = [
                    expect(client.get(
                        f"{resource}/clients/{management}/roles/{label}", headers=auth,
                    ), 200).json()
                    for label in permissions
                ]
                expect(client.post(
                    f"{resource}/users/{service_user}/role-mappings/clients/{management}",
                    headers=auth, json=roles,
                ), 204)
                expect(client.post(
                    f"{resource}/clients/{app}/scope-mappings/clients/{management}",
                    headers=auth, json=roles,
                ), 204)
                token = expect(client.post(
                    f"/realms/{realm}/protocol/openid-connect/token",
                    data={"grant_type": "client_credentials", "client_id": name,
                          "client_secret": secret},
                ), 200).json()["access_token"]

                return token, service_user, app

            writer, writer_user, writer_client = principal(
                "bind-writer", "manage-users", "view-clients"
            )
            reader, _, reader_client = principal(
                "bind-reader", "view-users", "view-clients"
            )
            assert writer != reader
            fixture = {
                "realm": realm,
                "realm_id": realm_id,
                "user": target,
                "client": application,
                "role": {"id": role["id"], "name": ROLE},
                "writer": writer,
                "reader": reader,
                "writer_user": writer_user,
                "writer_client": writer_client,
                "reader_client": reader_client,
            }
            if getattr(request, "param", False):
                audit_reader, _, audit_reader_client = principal(
                    "bind-audit-reader", "view-events"
                )
                expect(
                    client.put(
                        f"{resource}/events/config",
                        headers=auth,
                        json={
                            "adminEventsEnabled": True,
                            "adminEventsDetailsEnabled": True,
                        },
                    ),
                    204,
                )
                fixture.update(
                    audit_reader=audit_reader, audit_reader_client=audit_reader_client
                )
                if request.node.callspec.params.get("scenario") == "restore_then_resume":
                    resume_role = "report-editor"
                    create(f"/clients/{application}/roles", {"name": resume_role})
                    role_data = expect(client.get(
                        f"{resource}/clients/{application}/roles/{resume_role}", headers=auth,
                    ), 200).json()
                    fixture["resume_role"] = {"id": role_data["id"], "name": resume_role}
            yield fixture
        finally:
            expect(client.delete(resource, headers=auth), 204)


class KeycloakPostTimeout(httpx.AsyncHTTPTransport):
    """Inject a client-side timeout before forwarding or after Keycloak commits."""

    def __init__(self, *, forward: bool) -> None:
        super().__init__(trust_env=False, retries=0)
        self.forward = forward
        self.post_attempts = 0
        self.upstream_status = None
        self.role_reads = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            self.role_reads += 1
            return await super().handle_async_request(request)

        assert request.method == "POST"
        self.post_attempts += 1
        if self.forward:
            response = await super().handle_async_request(request)
            try:
                self.upstream_status = response.status_code
                expect(response, 204)
            finally:
                await response.aclose()
        raise httpx.ReadTimeout("Injected Keycloak response timeout", request=request)


class KeycloakBridge:
    """Translate only the exact test command and look up actual Keycloak state.

    The operation envelope is generated here for the Sandbox test protocol.
    Its association with the write is scoped to this run's fresh, isolated realm.
    """

    def __init__(self, client, fixture, event):
        self.client = client
        self.fixture = fixture
        self.event = event
        self.connections = 0
        self.writes = 0
        self.post_status = None
        self.reads = 0
        self.lookup_available = True
        self.request_key = None
        self.write_started_ms = None
        self.audit_path = f"users/{fixture['user']}/role-mappings/clients/{fixture['client']}"
        self.path = f"/admin/realms/{fixture['realm']}/{self.audit_path}"

    async def mappings(self):
        result = expect(await self.client.get(
            self.path, headers=bearer(self.fixture["reader"]),
        ), 200)
        return [{key: role[key] for key in ("id", "name")} for role in result.json()]

    def grant_payload(self):
        role = self.fixture["role"]
        if "audit_reader" in self.fixture:
            role = {**role, "description": f"veritas-rehearsal:{self.event['event_id']}"}
        return [role]

    async def audit_events(self, *, require_available=False):
        response = await self.client.get(
            f"/admin/realms/{self.fixture['realm']}/admin-events",
            headers=bearer(self.fixture["audit_reader"]),
            params={"resourcePath": self.audit_path, "max": AUDIT_PAGE_LIMIT},
        )
        if require_available:
            expect(response, 200)
        if response.status_code != 200:
            return []
        return response.json()

    def audited_operation(self, events, *, role_payload=None) -> str | None:
        if (
            self.write_started_ms is None
            or not isinstance(events, list)
            or len(events) >= AUDIT_PAGE_LIMIT
        ):
            return None
        payload = self.grant_payload() if role_payload is None else role_payload
        expected_roles = [{**payload[0], "composite": False}]
        matches = []
        for event in events:
            try:
                actor = event["authDetails"]
                roles = json.loads(event["representation"])
                if (
                    event["realmId"] == self.fixture["realm_id"]
                    and actor["realmId"] == self.fixture["realm_id"]
                    and actor["userId"] == self.fixture["writer_user"]
                    and actor["clientId"] == self.fixture["writer_client"]
                    and event["operationType"] == "CREATE"
                    and event["resourceType"] == "CLIENT_ROLE_MAPPING"
                    and event["resourcePath"] == self.audit_path
                    and self.write_started_ms <= event["time"] <= time_ns() // 1_000_000
                    and not event.get("error")
                    and roles == expected_roles
                ):
                    matches.append(validate_uuid(event["id"]))
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
        return matches[0] if len(matches) == 1 else None

    async def respond(self, wire):
        headers, _, body = wire.partition(b"\r\n\r\n")
        start, *fields = headers.split(b"\r\n")
        method, path, _ = start.split()
        values = dict(field.split(b": ", 1) for field in fields)
        if method == b"POST":
            assert path == b"/v1/events"
            assert values[b"Authorization"] == b"Bearer " + WRITER_TOKEN
            assert parse_event(body).model_dump() == self.event
            self.writes += 1
            self.request_key = values[b"Idempotency-Key"].decode()
            self.write_started_ms = time_ns() // 1_000_000
            try:
                response = await self.client.post(
                    self.path,
                    headers=bearer(self.fixture["writer"]),
                    json=self.grant_payload(),
                )
            except httpx.TimeoutException:
                return b""
            expect(response, 204)
            self.post_status = response.status_code
            # Keycloak completed the write. Lose the response at the Sandbox boundary.
            return b""
        assert method == b"GET"
        assert values[b"Authorization"] == b"Bearer " + READER_TOKEN
        assert not body and self.request_key is not None
        assert path == f"/v1/operations?idempotency_key={self.request_key}".encode()
        self.reads += 1
        if not self.lookup_available:
            return b"HTTP/1.1 503 Unavailable\r\nContent-Length: 0\r\n\r\n"
        mappings = await self.mappings()
        operation_id = self.event["event_id"] if self.post_status == 204 else None
        if "audit_reader" in self.fixture:
            operation_id = self.audited_operation(await self.audit_events())
        if operation_id is None or self.fixture["role"] not in mappings:
            return b"HTTP/1.1 404 Missing\r\nContent-Length: 0\r\n\r\n"
        payload = json.dumps({
            "operation_id": operation_id,
            "event_id": self.event["event_id"],
            "idempotency_key": self.request_key,
            "payload_digest": sha256_of_canonical_json(self.event),
            "state": "PERSISTED",
        }).encode()
        return (b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                + f"Content-Length: {len(payload)}\r\n\r\n".encode() + payload)

    async def connect(self, host, port, **_options):
        assert (host, port) == ("sandbox.example.invalid", 443)
        self.connections += 1
        reader = asyncio.StreamReader()
        bridge = self

        class Connection:
            def __init__(self):
                self.transport = self
                self.wire = None

            def write(self, wire):
                assert self.wire is None
                self.wire = wire

            async def drain(self):
                reader.feed_data(await bridge.respond(self.wire))
                reader.feed_eof()

            def abort(self):
                self.wire = None

        return reader, Connection()


@pytest.fixture
def keycloak_grant(keycloak, tmp_path):
    command = {
        "realm": keycloak["realm"], "user": keycloak["user"],
        "client": keycloak["client"], "role": keycloak["role"]["id"],
    }
    event = {
        "event_id": str(uuid4()),
        "message": json.dumps(command, sort_keys=True, separators=(",", ":")),
    }
    prepared = consume_fixture_authorization(*issue_for_payload(tmp_path, event))
    return command, event, prepared


async def reconcile_grant(artifact, args, event, clock):
    options = args.copy()
    historical = options.pop("governance_inputs")
    options.pop("load_current_inputs")
    reader = reconciliation.SandboxReaderPolicy(
        "keycloak-rehearsal-reader", "reader-v1", "synthetic", "sandbox",
    )
    verifier = ApprovedReconciliationVerifier(
        reconciliation.VERIFIER_ID,
        reconciliation.sandbox_reconciliation_policy_hash(options["deployment"], reader),
    )
    return await reconciliation.reconcile_sandbox_effect(
        artifact, json.dumps(event), historical_governance_inputs=historical,
        reader_policy=reader,
        verifier_policy=reconciliation.ReconciliationVerifierPolicy((verifier,)),
        provider=ReaderProvider(clock), **options,
    )


@pytest.mark.asyncio
async def test_keycloak_grant_reconciles_after_lost_response(keycloak, keycloak_grant, monkeypatch):
    command, event, prepared = keycloak_grant
    async with httpx.AsyncClient(base_url=ORIGIN, trust_env=False, timeout=3) as client:
        bridge = KeycloakBridge(client, keycloak, event)
        assert await bridge.mappings() == []
        # Exercise Keycloak's write authorization with the read-only principal.
        # An empty mapping list tests authorization without granting any role.
        expect(await client.post(
            bridge.path, headers=bearer(keycloak["reader"]), json=[],
        ), 403)
        monkeypatch.setattr(asyncio, "open_connection", bridge.connect)

        async def execute(artifact, args, request):
            transport = SandboxHTTPSTransport(endpoint_url=args["deployment"].endpoint_url)
            return await execution.execute_sandbox_bind(
                artifact, json.dumps(request), provider=WriterProvider(prepared, args),
                transport=transport, **args,
            )

        for field in command:
            artifact, args = await _args(prepared)
            changed = {**command, field: str(uuid4())}
            request = {**event, "message": json.dumps(changed, sort_keys=True,
                                                     separators=(",", ":"))}
            with pytest.raises(execution.SandboxBindExecutionError):
                await execute(artifact, args, request)

        artifact, args = await _args(prepared)
        current = prepared[3]
        revoked = replace(current.governance, authority_revocation_checker=_Revocation(
            current.governance, "revoked",
        ))
        args["load_current_inputs"] = lambda _now: replace(current, governance=revoked)
        with pytest.raises(execution.SandboxBindExecutionError):
            await execute(artifact, args, event)
        assert bridge.connections == bridge.writes == 0
        assert await bridge.mappings() == []

        artifact, args = await _args(prepared)
        observation = await execute(artifact, args, event)
        assert observation.reason_code == "TRANSPORT_FAILED_OR_UNKNOWN"
        assert bridge.writes == 1 and bridge.post_status == 204
        row = await args["effect_store"].get(observation.attempt_id)
        assert row.state == execution.EffectExecutionState.EFFECT_UNKNOWN
        with pytest.raises(execution.SandboxBindExecutionError):
            await execute(artifact, args, event)
        assert bridge.connections == bridge.writes == 1

        bridge.lookup_available = False
        unavailable = await reconcile_grant(artifact, args, event, prepared[4])
        assert unavailable.record == row and unavailable.evidence is None
        assert bridge.writes == 1

        bridge.lookup_available = True
        result = await reconcile_grant(artifact, args, event, prepared[4])
        assert result.record.state == execution.EffectExecutionState.CONFIRMED_EFFECT
        assert result.evidence is not None
        assert bridge.writes == 1 and bridge.reads == 2
        assert await bridge.mappings() == [keycloak["role"]]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "forward", [False, True], ids=["request-not-forwarded", "response-lost-after-commit"],
)
async def test_keycloak_post_timeout_keeps_effect_unknown(
    keycloak, keycloak_grant, monkeypatch, forward,
):
    _, event, prepared = keycloak_grant
    artifact, args = await _args(prepared)
    store = args["effect_store"]
    transport = SandboxHTTPSTransport(endpoint_url=args["deployment"].endpoint_url)
    upstream = KeycloakPostTimeout(forward=forward)
    async with httpx.AsyncClient(
        base_url=ORIGIN, transport=upstream, trust_env=False, timeout=3,
    ) as client:
        bridge = KeycloakBridge(client, keycloak, event)
        assert await bridge.mappings() == []
        monkeypatch.setattr(asyncio, "open_connection", bridge.connect)
        payload = json.dumps(event)
        provider = WriterProvider(prepared, args)
        observed = await execution.execute_sandbox_bind(
            artifact, payload, provider=provider, transport=transport, **args,
        )
        assert observed.reason_code == "TRANSPORT_FAILED_OR_UNKNOWN"
        assert bridge.post_status is None
        assert upstream.upstream_status == (204 if forward else None)
        row = await store.get(observed.attempt_id)
        assert row.state == execution.EffectExecutionState.EFFECT_UNKNOWN

        result = await reconcile_grant(artifact, args, event, prepared[4])
        assert bridge.reads == 1 and upstream.role_reads == 2
        assert result.record == row and result.evidence is None
        assert await store.get(observed.attempt_id) == row
        with pytest.raises(BindEffectStateError, match="BES_ARCHIVE_MISSING_OR_MISMATCHED"):
            await store.get_reconciliation(observed.attempt_id)
        assert await bridge.mappings() == ([keycloak["role"]] if forward else [])

        with pytest.raises(execution.SandboxBindExecutionError):
            await execution.execute_sandbox_bind(
                artifact, payload, provider=provider, transport=transport, **args,
            )
        assert bridge.connections == 2
        assert bridge.writes == upstream.post_attempts == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("keycloak", [True], indirect=True, ids=["admin-audit-enabled"])
@pytest.mark.parametrize(
    "role_revoked", [False, True], ids=["role-still-present", "role-revoked-before-lookup"],
)
async def test_keycloak_post_timeout_reconciliation_checks_current_role(
    keycloak, keycloak_grant, monkeypatch, role_revoked,
):
    _, event, prepared = keycloak_grant
    artifact, args = await _args(prepared)
    store = args["effect_store"]
    transport = SandboxHTTPSTransport(endpoint_url=args["deployment"].endpoint_url)
    provider = WriterProvider(prepared, args)
    payload = json.dumps(event)
    upstream = KeycloakPostTimeout(forward=True)
    async with (
        httpx.AsyncClient(base_url=ORIGIN, trust_env=False, timeout=3) as permissions_client,
        httpx.AsyncClient(base_url=ORIGIN, transport=upstream, trust_env=False, timeout=3) as client,
    ):
        bridge = KeycloakBridge(client, keycloak, event)
        expect(await permissions_client.post(
            bridge.path, headers=bearer(keycloak["audit_reader"]), json=[],
        ), 403)
        assert await bridge.mappings() == []
        assert await bridge.audit_events() == []
        monkeypatch.setattr(asyncio, "open_connection", bridge.connect)
        observed = await execution.execute_sandbox_bind(
            artifact, payload, provider=provider, transport=transport, **args,
        )
        assert observed.reason_code == "TRANSPORT_FAILED_OR_UNKNOWN"
        assert bridge.post_status is None and upstream.upstream_status == 204
        row = await store.get(observed.attempt_id)
        assert row.state == execution.EffectExecutionState.EFFECT_UNKNOWN
        assert await bridge.mappings() == [keycloak["role"]]

        events = await bridge.audit_events()
        assert len(events) == 1
        record = events[0]
        assert bridge.audited_operation(events) == record["id"]
        role = json.loads(record["representation"])[0]
        unrelated = [
            {**record, "representation": json.dumps([{**role, "description": str(uuid4())}])},
            {**record, "representation": json.dumps([{**role, "id": str(uuid4())}])},
            {**record, "authDetails": {**record["authDetails"], "userId": str(uuid4())}},
            {**record, "resourcePath": f"users/{uuid4()}/role-mappings"},
            {**record, "time": bridge.write_started_ms - 1},
            {**record, "error": "synthetic-failure"},
        ]
        for wrong_event in unrelated:
            assert bridge.audited_operation([wrong_event]) is None

        for inconclusive in (
            [],
            [unrelated[0]],
            [record, {**record, "id": str(uuid4())}],
        ):

            async def audit_response(events=inconclusive):
                return events

            with monkeypatch.context() as patch:
                patch.setattr(bridge, "audit_events", audit_response)
                unresolved = await reconcile_grant(artifact, args, event, prepared[4])
                assert unresolved.record == row and unresolved.evidence is None
                assert await store.get(observed.attempt_id) == row

        if role_revoked:
            expect(await permissions_client.request(
                "DELETE", bridge.path, headers=bearer(keycloak["writer"]), json=[keycloak["role"]],
            ), 204)
            assert await bridge.mappings() == []
            # The original success event still qualifies after the direct role is removed.
            events = await bridge.audit_events(require_available=True)
            assert bridge.audited_operation(events) == record["id"]
            assert any(event["operationType"] == "DELETE" for event in events)

        result = await reconcile_grant(artifact, args, event, prepared[4])
        if role_revoked:
            assert result.record == row and result.evidence is None
            assert await store.get(observed.attempt_id) == row
            with pytest.raises(BindEffectStateError, match="BES_ARCHIVE_MISSING_OR_MISMATCHED"):
                await store.get_reconciliation(observed.attempt_id)
        else:
            assert result.record.state == execution.EffectExecutionState.CONFIRMED_EFFECT
            assert result.evidence.evidence.external_operation_reference == record["id"]
        with pytest.raises(execution.SandboxBindExecutionError):
            await execution.execute_sandbox_bind(
                artifact, payload, provider=provider, transport=transport, **args,
            )
        assert bridge.writes == upstream.post_attempts == 1


def _issue_durable_grant(directory, target, event_id, deployment_policy_digest):
    request = {
        "target": target,
        "event_id": event_id,
        "attempt_id": str(uuid4()),
        "deployment_policy_digest": deployment_policy_digest,
    }
    binding = build_keycloak_role_grant_binding(**request)
    authorization, inputs = issue_for_action(
        directory,
        {
            "intended_action": ACTION,
            "target_system": "synthetic-keycloak",
            "target_resource": binding.endpoint_url,
            "evidence_refs": [binding.reference],
        },
        replace(contract(), id=ACTION, action_class=ACTION),
        endpoint_overrides={
            "endpoint_host": "keycloak.example.invalid", "endpoint_path_prefix": "/admin",
        },
        credential_overrides={},
    )
    _, _, context = _verified_source(
        authorization.source_runtime_risk_packet, inputs["source_inputs"], inputs["governance_inputs"],
    )
    consumption = build_authorization_consumption_record(
        live_adapter_bind_authorization_id=authorization.authorization_id,
        live_adapter_bind_authorization_hash=authorization.authorization_hash,
        idempotency_key=authorization.idempotency_key,
        bind_context_hash=authorization.bind_context_hash,
        execution_intent_id=authorization.execution_intent_id,
        execution_intent_hash=authorization.execution_intent_hash,
        endpoint_identity_binding_digest=context.endpoint_identity_binding_digest,
        credential_reference_digest=context.credential_reference_digest,
        credential_scope_binding_digest=context.credential_scope_binding_digest,
        consumed_at=authorization.valid_from,
    )
    return request | inputs | {"authorization": authorization, "consumption": consumption}


async def _dispatch_for_process_crash(attempts, writer_token, send, ready):
    consumptions = PostgresAtomicAuthorizationConsumptionStore()
    for attempt in attempts:
        assert await consumptions.consume_once(attempt["consumption"])
    results = await asyncio.gather(*(reserve_keycloak_dispatch(**attempt) for attempt in attempts))
    winner, = (record for record in results if record is not None)
    assert winner.state == execution.EffectExecutionState.EFFECT_UNKNOWN

    if send:
        original = attempts[results.index(winner)]
        binding = build_keycloak_role_grant_binding(**{
            field: original[field]
            for field in ("target", "event_id", "attempt_id", "deployment_policy_digest")
        })
        # Map the signed HTTPS identity to the disposable loopback server.
        transport = KeycloakPostTimeout(forward=True)
        async with httpx.AsyncClient(
            base_url=ORIGIN, transport=transport, trust_env=False,
            follow_redirects=False, timeout=3,
        ) as writer:
            with pytest.raises(httpx.ReadTimeout):
                await writer.post(
                    binding.endpoint_url.removeprefix(original["target"].origin),
                    headers={**bearer(writer_token), "Content-Type": "application/json"},
                    content=binding.body,
                )
        assert transport.post_attempts == 1 and transport.upstream_status == 204

    # Publish the crash checkpoint only after the reservation commit and, when
    # requested, after Keycloak has accepted the POST and its response was lost.
    ready.send_bytes(json.dumps([winner.operation_id, winner.record_hash]).encode("ascii"))
    await asyncio.Event().wait()


def _dispatch_crash_worker(attempts, writer_token, send, ready):
    asyncio.run(_dispatch_for_process_crash(attempts, writer_token, send, ready))


def _kill_dispatch_worker(attempts, writer_token, send):
    context = get_context("fork")
    checkpoint, ready = context.Pipe(duplex=False)
    with checkpoint, ready:
        worker = context.Process(
            target=_dispatch_crash_worker, args=(attempts, writer_token, send, ready),
        )
        worker.start()
        ready.close()
        try:
            assert checkpoint.poll(60), "sender did not reach the crash checkpoint"
            operation_id, record_hash = json.loads(checkpoint.recv_bytes(256))
            assert worker.is_alive()
        finally:
            if worker.is_alive():
                worker.kill()
            worker.join(timeout=10)
            assert worker.exitcode is not None, "sender did not exit after SIGKILL"
            exit_code = worker.exitcode
            worker.close()
    assert exit_code == -signal.SIGKILL
    return operation_id, record_hash


async def _check_dispatch_claims_after_crash(attempts, operation_id, record_hash):
    try:
        store = PostgresAtomicEffectStateStore()
        row = await store.get(operation_id)
        assert row is not None and row.state == execution.EffectExecutionState.EFFECT_UNKNOWN
        assert row.record_hash == record_hash
        for attempt in attempts:
            assert await reserve_keycloak_dispatch(**attempt) is None
        assert await store.get(operation_id) == row
        return row
    finally:
        await close_pool()


async def _read_durable_grant(
    operation_id, record_hash, keycloak, *, lab_deployment=None
):
    """Recover from PostgreSQL with only the two Keycloak read credentials."""
    try:
        store = PostgresAtomicEffectStateStore()
        row = await store.get(operation_id)
        assert row is not None and row.state == execution.EffectExecutionState.EFFECT_UNKNOWN
        assert row.record_hash == record_hash
        recovered = await get_keycloak_dispatch_intent(operation_id)
        assert recovered is not None
        binding = verify_keycloak_role_grant_binding(
            target=recovered.target,
            event_id=recovered.event_id,
            attempt_id=recovered.attempt_id,
            deployment_policy_digest=recovered.deployment_policy_digest,
            approved_reference=recovered.approved_reference,
        )

        recovery_methods = []

        async def require_read(request: httpx.Request) -> None:
            recovery_methods.append(request.method)
            assert request.method == "GET"

        async with httpx.AsyncClient(
            base_url=ORIGIN, trust_env=False, timeout=3, event_hooks={"request": [require_read]},
        ) as reader:
            bridge = KeycloakBridge(reader, keycloak, None)
            assert binding.endpoint_url == recovered.target.origin + bridge.path
            bridge.write_started_ms = int(datetime.fromisoformat(row.updated_at).timestamp() * 1000)
            events = await bridge.audit_events(require_available=True)
            assert isinstance(events, list) and len(events) < AUDIT_PAGE_LIMIT
            audit_id = bridge.audited_operation(events, role_payload=json.loads(binding.body))
            mappings = await bridge.mappings()
            observed_at = datetime.now(UTC)

        grant_events = [
            event for event in events
            if event.get("resourcePath") == bridge.audit_path and event.get("operationType") == "CREATE"
        ]
        observation = None
        role = {"id": recovered.target.role_id, "name": recovered.target.role_name}
        if audit_id is not None and role in mappings:
            event, = (event for event in grant_events if event.get("id") == audit_id)
            observation = KeycloakReconciliationObservation(
                reservation_record_hash=record_hash,
                approved_reference=recovered.approved_reference,
                attempt_id=recovered.attempt_id,
                audit_event_id=audit_id,
                audit_event_digest=sha256_of_canonical_json(event),
                direct_mapping_digest=sha256_of_canonical_json(role),
                mapping_observed_at=observed_at,
            )
            stale = observation.model_copy(update={"reservation_record_hash": "0" * 64})
            assert not await archive_keycloak_reconciliation_observation(operation_id, stale)
            results = await asyncio.gather(*(
                archive_keycloak_reconciliation_observation(operation_id, observation)
                for _ in range(2)
            ))
            assert sorted(results) == [False, True]

        assert await store.get(operation_id) == row
        async with httpx.AsyncClient(
            base_url=ORIGIN, trust_env=False, timeout=3, event_hooks={"request": [require_read]},
        ) as verifier_client:
            verifier = KeycloakBridge(verifier_client, keycloak, None)

            async def read_events(intent):
                assert intent.endpoint_url == recovered.target.origin + verifier.path
                return await verifier.audit_events(require_available=True)

            async def read_mappings(intent):
                assert intent.endpoint_url == recovered.target.origin + verifier.path
                return await verifier.mappings()

            async def missing_mappings(_intent):
                return []

            verifier_inputs = {
                "writer_user": keycloak["writer_user"],
                "writer_client": keycloak["writer_client"],
                "read_admin_events": read_events,
                "lab_deployment": lab_deployment,
            }
            assert await confirm_keycloak_reconciliation(
                operation_id, **verifier_inputs, read_direct_mappings=missing_mappings,
            ) is None
            assert await store.get(operation_id) == row
            confirmed = await confirm_keycloak_reconciliation(
                operation_id, **verifier_inputs, read_direct_mappings=read_mappings,
            )
            assert await confirm_keycloak_reconciliation(
                operation_id, **verifier_inputs, read_direct_mappings=read_mappings,
            ) is None

        return {
            "attempt_id": recovered.attempt_id,
            "grant_events": len(grant_events),
            "recovery_post_requests": recovery_methods.count("POST"),
            "audit_id": audit_id,
            "mappings": mappings,
            "archive": observation.model_dump(mode="json") if observation is not None else None,
            "confirmation_hash": confirmed.reconciliation_evidence_hash if confirmed else None,
        }
    finally:
        await close_pool()


async def _read_observation_after_recovery(operation_id):
    try:
        return (
            await get_keycloak_reconciliation_observation(operation_id),
            await PostgresAtomicEffectStateStore().get(operation_id),
            await read_verified_keycloak_confirmation(operation_id),
        )
    finally:
        await close_pool()


async def _reject_corrupted_confirmation_lineage(record, observation):
    from psycopg.types.json import Jsonb

    from veritas_os.storage.db import get_pool

    stored = observation.model_dump(mode="json")
    mutations = (
        None,
        Jsonb({**stored, "attempt_id": str(uuid4())}),
        Jsonb({**stored, "audit_event_digest": "0" * 64}),
    )
    pool = await get_pool()

    async def replace_observation(value):
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE bind_keycloak_dispatch_intents SET reconciliation_observation=%s "
                "WHERE operation_id=%s",
                (value, record.operation_id),
            )

    async def replace_effect(payload):
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE bind_effect_states SET execution_intent_id=%s, idempotency_key=%s, "
                "record_hash=%s, record=%s WHERE operation_id=%s",
                (
                    payload["execution_intent_id"], payload["idempotency_key"],
                    payload["record_hash"], Jsonb(payload), record.operation_id,
                ),
            )

    try:
        try:
            for value in mutations:
                await replace_observation(value)
                with pytest.raises(BindEffectStateError):
                    await read_verified_keycloak_confirmation(record.operation_id)
        finally:
            await replace_observation(Jsonb(stored))

        for field in ("execution_intent_id", "idempotency_key"):
            mismatched = record.model_dump(mode="json", exclude={"record_hash"})
            mismatched[field] = str(uuid4())
            mismatched["record_hash"] = sha256_of_canonical_json(mismatched)
            await replace_effect(mismatched)
            # Local integrity remains valid. The separate consumption must reject the mismatch.
            readback = await PostgresAtomicEffectStateStore().get(record.operation_id)
            assert readback is not None and getattr(readback, field) == mismatched[field]
            with pytest.raises(BindEffectStateError, match="KGR_DISPATCH_INTENT_READ_FAILED"):
                await read_verified_keycloak_confirmation(record.operation_id)
    finally:
        try:
            await replace_effect(record.model_dump(mode="json"))
        finally:
            await close_pool()


async def _rehearse_receipt_publication(operation_id, original, replacement, *, confirmed):
    async def publish(attempt):
        return await publish_keycloak_receipts(
            operation_id, attempt["authorization"], source_inputs=attempt["source_inputs"],
            governance_inputs=attempt["governance_inputs"], trust_inputs=attempt["trust_inputs"],
        )

    try:
        with pytest.raises(KeycloakReceiptError, match="KGR_RECEIPT_PUBLICATION_FAILED"):
            await publish(replacement)
        if not confirmed:
            with pytest.raises(KeycloakReceiptError, match="KGR_RECEIPT_PUBLICATION_FAILED"):
                await publish(original)
            return None
        first, second = await asyncio.gather(publish(original), publish(original))
        assert first == second
        await close_pool()
        assert await publish(original) == first
        return first
    finally:
        await close_pool()


async def _reject_corrupted_receipt_bundles(operation_id, bundle):
    from psycopg.types.json import Jsonb

    from veritas_os.storage.db import get_pool

    stored = bundle.model_dump(mode="json")
    missing_outcome = {key: value for key, value in stored.items() if key != "outcome_receipt"}

    def replace_outcome(**changes):
        outcome = {**stored["outcome_receipt"], **changes}
        outcome.pop("outcome_hash")
        outcome["outcome_hash"] = sha256_of_canonical_json(outcome)
        pair = {**stored, "outcome_receipt": outcome}
        pair.pop("bundle_hash")
        pair["bundle_hash"] = sha256_of_canonical_json(pair)
        return pair

    other_operation = str(uuid4())
    substituted = replace_outcome(operation_id=other_operation, outcome_receipt_id=f"outcome-{other_operation}")
    invalid_hash = {**stored, "bundle_hash": "0" * 64}
    contradictory_statuses = (
        replace_outcome(blocked=True),
        replace_outcome(escalated=True),
        replace_outcome(rolled_back=True),
        replace_outcome(rollback_status="performed"),
    )
    pool = await get_pool()

    async def replace_bundle(payload):
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE bind_keycloak_dispatch_intents SET receipt_bundle=%s WHERE operation_id=%s",
                (Jsonb(payload), operation_id),
            )

    try:
        for mutation in (missing_outcome, substituted, invalid_hash, *contradictory_statuses):
            await replace_bundle(mutation)
            with pytest.raises(KeycloakReceiptError, match="KGR_RECEIPT_READ_INTEGRITY_FAILED"):
                await read_verified_keycloak_receipts(operation_id)
    finally:
        try:
            await replace_bundle(stored)
        finally:
            await close_pool()


@pytest.mark.parametrize("keycloak", [True], indirect=True)
@pytest.mark.parametrize("send", [False, True], ids=["kill-before-post", "kill-after-lost-response"])
@pytest.mark.skipif(
    "fork" not in get_all_start_methods()
    or not os.getenv("VERITAS_DATABASE_URL", "").startswith("postgresql"),
    reason="requires POSIX process isolation and the disposable PostgreSQL reservation store",
)
def test_keycloak_durable_reservation_recovers_using_only_read_operations(
    keycloak, tmp_path, tmp_path_factory, send,
):
    """Kill the writer at a durable checkpoint and recover in a fresh interpreter."""
    target = KeycloakRoleGrantTarget(
        origin="https://keycloak.example.invalid",
        realm_name=keycloak["realm"],
        realm_id=keycloak["realm_id"],
        user_id=keycloak["user"],
        client_id=keycloak["client"],
        role_id=keycloak["role"]["id"],
        role_name=keycloak["role"]["name"],
    )
    event_id = f"assignment-{uuid4().hex}"
    policy_digest = keycloak_reconciliation_policy_digest(
        keycloak["writer_user"], keycloak["writer_client"],
    )
    attempts = [
        _issue_durable_grant(tmp_path_factory.mktemp("keycloak-durable"), target, event_id, policy_digest)
        for _ in range(2)
    ]
    operation_id, record_hash = _kill_dispatch_worker(attempts, keycloak["writer"], send)
    row = asyncio.run(_check_dispatch_claims_after_crash(attempts, operation_id, record_hash))
    original, = [a for a in attempts if a["consumption"].consumption_id == row.consumption_id]
    replacement, = [a for a in attempts if a is not original]

    readers = {
        field: keycloak[field]
        for field in ("realm", "realm_id", "user", "client", "reader", "audit_reader",
                      "writer_user", "writer_client")
    }
    result_file = tmp_path / "read-only-recovery.json"
    code = (
        "import asyncio, json, sys; from pathlib import Path; "
        "from veritas_os.tests.test_keycloak_bind_role_rehearsal import _read_durable_grant; "
        "result = asyncio.run(_read_durable_grant(sys.argv[1], sys.argv[2], json.load(sys.stdin))); "
        "Path(sys.argv[3]).write_text(json.dumps(result), encoding='utf-8')"
    )
    # The test runner has Keycloak bootstrap credentials. Pass only database settings.
    recovery_env = {
        name: os.environ[name]
        for name in (
            "VERITAS_DATABASE_URL",
            "VERITAS_DB_CONNECT_TIMEOUT",
            "VERITAS_DB_POOL_MIN_SIZE",
            "VERITAS_DB_POOL_MAX_SIZE",
            "VERITAS_DB_SSLMODE",
            "VERITAS_DB_STATEMENT_TIMEOUT_MS",
        )
        if name in os.environ
    }
    subprocess.run(
        [sys.executable, "-c", code, operation_id, record_hash, str(result_file)],
        cwd=Path(__file__).resolve().parents[2], check=True, timeout=60,
        env=recovery_env, input=json.dumps(readers), text=True,
    )
    report = json.loads(result_file.read_text(encoding="utf-8"))
    assert report["attempt_id"] == original["attempt_id"]
    assert report["grant_events"] == int(send)
    assert (report["audit_id"] is not None) is send
    assert report["mappings"] == ([keycloak["role"]] if send else [])
    archive, final_record, verified = asyncio.run(_read_observation_after_recovery(operation_id))
    if send:
        assert archive is not None
        assert archive.model_dump(mode="json") == report["archive"]
        assert str(archive.audit_event_id) == report["audit_id"]
        assert archive.reservation_record_hash == record_hash
        assert final_record is not None
        assert final_record.state == execution.EffectExecutionState.CONFIRMED_EFFECT
        assert final_record.revision == row.revision + 1
        assert final_record.reconciliation_evidence_hash == report["confirmation_hash"]
        assert final_record.reconciliation_evidence_hash is not None
        assert verified is not None
        assert verified.record == final_record and verified.observation == archive
        assert verified.intent.attempt_id == original["attempt_id"]
        asyncio.run(_reject_corrupted_confirmation_lineage(final_record, archive))
    else:
        assert archive is None and report["archive"] is None
        assert final_record == row and report["confirmation_hash"] is None
        assert verified is None
    receipts = asyncio.run(_rehearse_receipt_publication(operation_id, original, replacement, confirmed=send))
    audit_file = tmp_path / "verified-receipts.json"
    audit_code = (
        "import asyncio, json, sys; from pathlib import Path; "
        "from veritas_os.policy.keycloak_receipt_outcome import read_verified_keycloak_receipts; "
        "bundle = asyncio.run(read_verified_keycloak_receipts(sys.argv[1])); "
        "result = None if bundle is None else bundle.model_dump(mode='json'); "
        "Path(sys.argv[2]).write_text(json.dumps(result), encoding='utf-8')"
    )
    subprocess.run(
        [sys.executable, "-c", audit_code, operation_id, str(audit_file)],
        cwd=Path(__file__).resolve().parents[2], check=True, timeout=60,
        env=recovery_env,
    )
    audit_result = json.loads(audit_file.read_text(encoding="utf-8"))
    if send:
        assert receipts is not None
        assert audit_result == receipts.model_dump(mode="json")
        lineage = receipts.bind_receipt["governance_identity"]
        assert lineage["authorization_id"] == row.authorization_id
        assert lineage["consumption_id"] == row.consumption_id
        assert lineage["reconciliation_evidence_hash"] == report["confirmation_hash"]
        assert receipts.outcome_receipt["bind_receipt_id"] == receipts.bind_receipt["bind_receipt_id"]
        assert receipts.outcome_receipt["observed_effects"][0]["audit_event_id"] == report["audit_id"]
        asyncio.run(_reject_corrupted_receipt_bundles(operation_id, receipts))
    else:
        assert receipts is None and audit_result is None

    evidence_dir = os.getenv("VERITAS_KEYCLOAK_EVIDENCE_DIR")
    if evidence_dir:
        assert final_record is not None
        scenario = "kill-after-lost-response" if send else "kill-before-post"
        evidence = {
            "scenario": scenario,
            "provider_grant_events": report["grant_events"],
            "recovery_post_requests": report["recovery_post_requests"],
            "blocked_reservations": len(attempts),
            "effect_state": final_record.state.value,
            "effect_record_hash": final_record.record_hash,
            "confirmation_hash": final_record.reconciliation_evidence_hash,
            "receipt_bundle_hash": audit_result["bundle_hash"] if audit_result else None,
            "bind_receipt_hash": audit_result["bind_receipt"]["bind_receipt_hash"] if audit_result else None,
            "outcome_hash": audit_result["outcome_receipt"]["outcome_hash"] if audit_result else None,
        }
        output = Path(evidence_dir)
        output.mkdir(parents=True, exist_ok=True)
        (output / f"{scenario}.json").write_text(json.dumps(evidence), encoding="utf-8")


@pytest_asyncio.fixture
async def lab_db_pool(monkeypatch):
    """Bind each lab scenario's connection pool to its own pytest event loop."""
    from veritas_os.storage import db

    monkeypatch.setattr(db, "_pool", None)
    try:
        yield
    finally:
        await close_pool()


@pytest.mark.asyncio
@pytest.mark.parametrize("keycloak", [True], indirect=True)
@pytest.mark.parametrize(
    "scenario",
    [
        "cancel_first",
        "restore_pending",
        pytest.param(
            "restore_after_grant",
            marks=pytest.mark.skipif(
                os.getenv("VERITAS_SANDBOX_RESTORE_E2E") != "1",
                reason="requires PostgreSQL backup clients",
            ),
        ),
        pytest.param(
            "restore_then_resume",
            marks=pytest.mark.skipif(
                os.getenv("VERITAS_SANDBOX_RESTORE_E2E") != "1",
                reason="requires PostgreSQL backup clients",
            ),
        ),
        "lost_commit",
        "contention",
        "substituted",
        "slow_recheck",
        "risk_expires",
        "lost_response",
    ],
)
async def test_keycloak_lab_executor_https_boundary(
    keycloak,
    scenario,
    tmp_path,
    monkeypatch,
    lab_db_pool,
):
    """Count POSTs through the actual Executor and disposable Keycloak realm."""
    from datetime import timedelta
    import ssl

    from pydantic import SecretBytes
    from veritas_os.policy import keycloak_lab_executor as module
    from veritas_os.policy.keycloak_dispatch_reservation import (
        KeycloakDispatchOrder,
        revoke_keycloak_authorization,
    )
    from veritas_os.policy.keycloak_role_grant_binding import KeycloakLabDeployment
    from veritas_os.policy.sandbox_pre_effect import (
        SandboxClockReading,
        SandboxCurrentInputs,
    )
    from veritas_os.tests.test_native_bind_authorization_consumption import _fresh

    host = "keycloak.example.invalid"
    cert = tmp_path / "lab.pem"
    tls_key = tmp_path / "lab-key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-keyout",
            str(tls_key),
            "-out",
            str(cert),
            "-subj",
            f"/CN={host}",
            "-addext",
            f"subjectAltName=DNS:{host}",
        ],
        check=True,
        capture_output=True,
    )
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(cert, tls_key)
    target = KeycloakRoleGrantTarget(
        "https://" + host,
        keycloak["realm"],
        keycloak["realm_id"],
        keycloak["user"],
        keycloak["client"],
        keycloak["role"]["id"],
        keycloak["role"]["name"],
    )
    posts = []
    event_id = f"lab-{uuid4()}"

    async with httpx.AsyncClient(
        base_url=ORIGIN, trust_env=False, timeout=3
    ) as upstream:

        async def forward(reader, writer):
            try:
                raw = await reader.readuntil(b"\r\n\r\n")
                request, *lines = raw.decode("ascii").split("\r\n")[:-2]
                method, path, _ = request.split(" ")
                headers = dict(line.split(": ", 1) for line in lines)
                payload = await reader.readexactly(int(headers["Content-Length"]))
                assert method == "POST" and path == expected_path
                posts.append(payload)
                response = await upstream.post(
                    path,
                    content=payload,
                    headers={
                        "Authorization": headers["Authorization"],
                        "Content-Type": "application/json",
                    },
                )
                assert response.status_code == 204
                if scenario != "lost_response":
                    writer.write(
                        b"HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n"
                    )
                    await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(forward, "127.0.0.1", 0, ssl=tls)
        async with server:
            deployment = KeycloakLabDeployment(
                target,
                server.sockets[0].getsockname()[1],
                cert.read_text(),
                keycloak["writer_user"],
                keycloak["writer_client"],
                keycloak["audit_reader_client"],
                keycloak["reader_client"],
                "credential-ref:keycloak:lab-writer:v1",
                "keycloak:role-grant",
            )

            def issue(directory, *, deployment=deployment, event_id=event_id):
                attempt_id = str(uuid4())
                binding = build_keycloak_role_grant_binding(
                    target=deployment.target,
                    event_id=event_id,
                    attempt_id=attempt_id,
                    deployment_policy_digest=deployment.digest(),
                )
                directory.mkdir()
                action_contract = replace(
                    contract(),
                    id=ACTION,
                    action_class=ACTION,
                    human_approval_rules={"required": True, "minimum_approvals": 1},
                )
                artifact, inputs = issue_for_action(
                    directory,
                    {
                        "intended_action": ACTION,
                        "target_system": "synthetic-keycloak",
                        "target_resource": binding.endpoint_url,
                        "evidence_refs": [binding.reference],
                        "required_human_approval": True,
                    },
                    action_contract,
                    endpoint_overrides={
                        "endpoint_host": host,
                        "endpoint_path_prefix": "/admin",
                    },
                    credential_overrides={
                        "credential_reference_id": deployment.writer_reference_id,
                        "credential_scope": deployment.writer_scope,
                    },
                )
                return attempt_id, binding, artifact, inputs

            first = issue(tmp_path / "first")
            second = issue(tmp_path / "second") if scenario == "contention" else None
            expected_path = first[1].endpoint_url.removeprefix(target.origin)
            clock_advanced = False

            def wiring(issued, *, deployment=deployment, event_id=event_id):
                attempt_id, _, artifact, inputs = issued
                gov, source = inputs["governance_inputs"], inputs["source_inputs"]
                initial = gov.verification_now + timedelta(seconds=1)
                elapsed = 0
                loads = 0

                def clock():
                    now = initial + timedelta(seconds=elapsed)
                    uncertainty = 0.25 if scenario == "risk_expires" and elapsed else 0
                    return SandboxClockReading(now, elapsed, now, uncertainty)

                def load_current(now):
                    nonlocal elapsed, loads, clock_advanced
                    loads += 1
                    # Runner speed does not determine the age of fixture evidence.
                    if scenario == "risk_expires" and loads == 3:
                        risk, fresh_source = _fresh(
                            inputs,
                            now,
                            valid_until=(now + timedelta(seconds=0.75)).isoformat(),
                        )
                        elapsed += 0.5
                        clock_advanced = True
                    else:
                        risk, fresh_source = _fresh(inputs, now)
                        if scenario == "slow_recheck" and loads == 3:
                            elapsed += 2
                            clock_advanced = True
                    return SandboxCurrentInputs(fresh_source, gov, risk)

                _, _, context = _verified_source(
                    artifact.source_runtime_risk_packet, source, gov
                )

                async def credential():
                    return module.KeycloakLabWriterCredential(
                        SecretBytes(keycloak["writer"].encode()),
                        context.credential_reference_digest,
                        context.credential_scope_binding_digest,
                        clock().now + timedelta(seconds=15),
                    )

                executor = module.KeycloakLabExecutor(
                    deployment,
                    trusted_clock=clock,
                    load_current_inputs=load_current,
                    resolve_writer=credential,
                )
                return executor, dict(
                    authorization=artifact,
                    event_id=event_id,
                    attempt_id=attempt_id,
                    issuance_source_inputs=source,
                    governance_inputs=gov,
                    trust_inputs=inputs["trust_inputs"],
                )

            executor, args = wiring(first)
            if scenario == "lost_response":
                for reader in ("reader", "audit_reader"):
                    headers = bearer(keycloak[reader])
                    expect(
                        await upstream.post(expected_path, headers=headers, json=[]),
                        403,
                    )
                    expect(
                        await upstream.delete(
                            f"/admin/realms/{target.realm_name}/admin-events",
                            headers=headers,
                        ),
                        403,
                    )
            if scenario == "cancel_first":
                assert (
                    await revoke_keycloak_authorization(
                        target=target,
                        deployment_policy_digest=deployment.digest(),
                        source_inputs=args["issuance_source_inputs"],
                        **{
                            k: v
                            for k, v in args.items()
                            if k != "issuance_source_inputs"
                        },
                    )
                    == KeycloakDispatchOrder.REVOKED
                )
                assert await executor.execute(**args) is None
            elif scenario == "restore_pending":
                from psycopg import sql

                from veritas_os.storage import db, sandbox_restore

                bridge = KeycloakBridge(upstream, keycloak, None)
                before_events = await bridge.audit_events(require_available=True)
                before_mappings = await bridge.mappings()
                assert len(before_events) < AUDIT_PAGE_LIMIT

                pool = await db.get_pool()
                async with pool.connection() as conn:
                    database = sql.Identifier(conn.info.dbname)
                    await conn.execute(
                        sql.SQL(
                            "ALTER DATABASE {} SET veritas.sandbox_restore_pending TO 'on'"
                        ).format(database)
                    )
                try:
                    assert await executor.execute(**args) is None
                    async with pool.connection() as conn:
                        result = await conn.execute(sandbox_restore.RECOVERY_PENDING)
                        assert await result.fetchone() == (True,)
                    assert await bridge.audit_events(require_available=True) == before_events
                    assert await bridge.mappings() == before_mappings
                finally:
                    async with pool.connection() as conn:
                        await conn.execute(
                            sql.SQL(
                                "ALTER DATABASE {} RESET veritas.sandbox_restore_pending"
                            ).format(database)
                        )
            elif scenario in {"restore_after_grant", "restore_then_resume"}:
                from urllib.parse import urlsplit

                import psycopg
                from psycopg.conninfo import conninfo_to_dict, make_conninfo

                from scripts.governance.reconcile_sandbox_restore import (
                    SandboxRestoreError,
                    reconcile,
                    recovery_digest,
                )
                from veritas_os.storage import db, sandbox_restore

                source_dsn = db.build_conninfo()
                database = f"keycloak_restore_{uuid4().hex}"
                target_dsn = make_conninfo(source_dsn, dbname=database)
                env = os.environ.copy()
                for key, value in conninfo_to_dict(source_dsn).items():
                    if key in {"host", "port", "user", "password", "dbname", "sslmode"}:
                        name = "PGDATABASE" if key == "dbname" else f"PG{key.upper()}"
                        env[name] = value
                scripts = Path(__file__).resolve().parents[2] / "scripts"

                async def backup():
                    await asyncio.to_thread(
                        subprocess.run,
                        ["bash", str(scripts / "backup_postgres.sh"), "--output", str(tmp_path)],
                        env=env, check=True, capture_output=True, timeout=60,
                    )
                    (archive,) = tmp_path.glob("veritas_*.dump")
                    return archive

                if scenario == "restore_after_grant":
                    archive = await backup()
                bridge = KeycloakBridge(upstream, keycloak, None)
                assert await bridge.audit_events(require_available=True) == []
                assert await bridge.mappings() == []
                result = await executor.execute(**args)
                assert result is not None and result.observation == "HTTP_204_UNVERIFIED"
                assert posts == [first[1].body]
                before_events = await bridge.audit_events(require_available=True)
                before_mappings = await bridge.mappings()
                assert len(before_events) == 1
                assert before_mappings == [
                    {"id": keycloak["role"]["id"], "name": keycloak["role"]["name"]}
                ]
                if scenario == "restore_then_resume":
                    archive = await backup()
                await asyncio.to_thread(
                    subprocess.run,
                    [
                        "bash", str(scripts / "restore_postgres.sh"),
                        "--mode=test", "--test-db", database, str(archive),
                    ],
                    env=env, check=True, capture_output=True, timeout=60,
                )
                with (
                    psycopg.connect(source_dsn, autocommit=True) as source,
                    psycopg.connect(target_dsn, autocommit=True) as restored,
                ):
                    assert restored.execute(sandbox_restore.RECOVERY_PENDING).fetchone() == (True,)
                    digest = recovery_digest(source)
                    if scenario == "restore_after_grant":
                        with pytest.raises(
                            SandboxRestoreError, match="backup lacks committed dispatch history"
                        ):
                            reconcile(source, restored, digest)
                        assert restored.execute(sandbox_restore.RECOVERY_PENDING).fetchone() == (True,)
                    else:
                        reconcile(source, restored, digest)
                        assert restored.execute(sandbox_restore.RECOVERY_PENDING).fetchone() == (False,)
                assert posts == [first[1].body]
                assert await bridge.audit_events(require_available=True) == before_events
                assert await bridge.mappings() == before_mappings
                if scenario == "restore_then_resume":
                    await close_pool()
                    target_url = urlsplit(source_dsn)._replace(path=f"/{database}").geturl()
                    monkeypatch.setenv("VERITAS_DATABASE_URL", target_url)
                    pool = await db.get_pool()
                    async with pool.connection() as conn:
                        assert conn.info.dbname == database

                    with pytest.raises(module.KeycloakLabExecutionError):
                        await executor.execute(**args)
                    assert posts == [first[1].body]
                    assert await bridge.audit_events(require_available=True) == before_events
                    assert await bridge.mappings() == before_mappings

                    role = keycloak["resume_role"]
                    resume_deployment = replace(
                        deployment,
                        target=replace(target, role_id=role["id"], role_name=role["name"]),
                    )
                    resume_event_id = f"lab-{uuid4()}"
                    resumed = issue(
                        tmp_path / "resumed",
                        deployment=resume_deployment,
                        event_id=resume_event_id,
                    )
                    resumed_executor, resumed_args = wiring(
                        resumed, deployment=resume_deployment, event_id=resume_event_id
                    )
                    result = await resumed_executor.execute(**resumed_args)
                    assert result is not None and result.observation == "HTTP_204_UNVERIFIED"
                    assert posts == [first[1].body, resumed[1].body]
                    after_events = await bridge.audit_events(require_available=True)
                    assert len(after_events) == 2 and before_events[0] in after_events
                    (new_event,) = [event for event in after_events if event not in before_events]
                    assert new_event["authDetails"]["userId"] == keycloak["writer_user"]
                    assert new_event["operationType"] == "CREATE"
                    assert new_event["resourceType"] == "CLIENT_ROLE_MAPPING"
                    assert any(
                        entry["id"] == role["id"]
                        for entry in json.loads(new_event["representation"])
                    )
                    assert sorted(item["id"] for item in await bridge.mappings()) == sorted(
                        [keycloak["role"]["id"], role["id"]]
                    )
            elif scenario == "lost_commit":
                commit = module.reserve_and_commit_keycloak_dispatch
                committed = False

                async def unacknowledged(**inputs):
                    nonlocal committed
                    committed = await commit(**inputs) is not None
                    assert committed
                    raise RuntimeError("fixture lost the commitment response")

                monkeypatch.setattr(
                    module, "reserve_and_commit_keycloak_dispatch", unacknowledged
                )
                with pytest.raises(module.KeycloakLabExecutionError):
                    await executor.execute(**args)
                assert committed
            elif scenario == "substituted":
                with pytest.raises(module.KeycloakLabExecutionError):
                    await executor.execute(**(args | {"attempt_id": str(uuid4())}))
            elif scenario == "contention":
                another, other_args = wiring(second)
                results = await asyncio.gather(
                    executor.execute(**args), another.execute(**other_args)
                )
                assert sum(result is not None for result in results) == 1
                assert [result.observation for result in results if result] == [
                    "HTTP_204_UNVERIFIED"
                ]
                assert posts == [first[1].body] or posts == [second[1].body]
            else:
                result = await executor.execute(**args)
                assert result is not None and result.observation == "TRANSPORT_UNKNOWN"
                effect = await PostgresAtomicEffectStateStore().get(result.operation_id)
                assert (
                    effect is not None
                    and effect.state == execution.EffectExecutionState.EFFECT_UNKNOWN
                )
                if scenario == "lost_response":
                    evidence = await _read_durable_grant(
                        effect.operation_id,
                        effect.record_hash,
                        keycloak,
                        lab_deployment=deployment,
                    )
                    assert (
                        evidence["grant_events"] == 1
                        and evidence["recovery_post_requests"] == 0
                    )
                    assert evidence["confirmation_hash"] is not None
                    receipts = await publish_keycloak_receipts(
                        effect.operation_id, first[2], **first[3]
                    )
                    assert (
                        await read_verified_keycloak_receipts(effect.operation_id)
                        == receipts
                    )
                    assert posts == [first[1].body]
                else:
                    assert clock_advanced

            expected_posts = {
                "contention": 1,
                "lost_response": 1,
                "restore_after_grant": 1,
                "restore_then_resume": 2,
            }
            assert len(posts) == expected_posts.get(scenario, 0)
