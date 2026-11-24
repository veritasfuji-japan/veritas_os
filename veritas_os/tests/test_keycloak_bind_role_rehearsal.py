"""Opt-in integration proof against an isolated, disposable Keycloak server."""

import asyncio
from dataclasses import replace
from datetime import datetime
import json
import os
from secrets import token_urlsafe
from time import time_ns
from uuid import uuid4

import httpx
import pytest

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
AUDIT_PAGE_LIMIT = 100


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

            writer, writer_user, writer_client = principal("bind-writer", "manage-users", "view-clients")
            reader, _, _ = principal("bind-reader", "view-users", "view-clients")
            assert writer != reader
            fixture = {
                "realm": realm, "realm_id": realm_id, "user": target, "client": application,
                "role": {"id": role["id"], "name": ROLE}, "writer": writer, "reader": reader,
                "writer_user": writer_user, "writer_client": writer_client,
            }
            if getattr(request, "param", False):
                audit_reader, _, _ = principal("bind-audit-reader", "view-events")
                expect(client.put(f"{resource}/events/config", headers=auth, json={
                    "adminEventsEnabled": True, "adminEventsDetailsEnabled": True,
                }), 204)
                fixture["audit_reader"] = audit_reader
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

        for inconclusive in ([], [unrelated[0]], [record, {**record, "id": str(uuid4())}]):
            async def audit_response():
                return inconclusive

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


def _issue_durable_grant(directory, target, event_id):
    request = {
        "target": target,
        "event_id": event_id,
        "attempt_id": str(uuid4()),
        "deployment_policy_digest": sha256_of_canonical_json({
            "profile": "disposable-keycloak-durable-rehearsal",
        }),
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


@pytest.mark.asyncio
@pytest.mark.parametrize("keycloak", [True], indirect=True)
@pytest.mark.parametrize("send", [False, True], ids=["exit-before-post", "lost-post-response"])
@pytest.mark.skipif(
    not os.getenv("VERITAS_DATABASE_URL", "").startswith("postgresql"),
    reason="requires the disposable PostgreSQL reservation store",
)
async def test_keycloak_durable_reservation_recovers_using_only_read_operations(
    keycloak, tmp_path_factory, send,
):
    """Compose the durable reservation with an isolated provider and reconnect for recovery."""
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
    attempts = [
        _issue_durable_grant(tmp_path_factory.mktemp("keycloak-durable"), target, event_id)
        for _ in range(2)
    ]
    try:
        consumptions = PostgresAtomicAuthorizationConsumptionStore()
        for attempt in attempts:
            assert await consumptions.consume_once(attempt["consumption"])
        results = await asyncio.gather(*(reserve_keycloak_dispatch(**attempt) for attempt in attempts))
        winner, = (record for record in results if record is not None)
        assert winner.state == execution.EffectExecutionState.EFFECT_UNKNOWN

        # This fixture maps the signed HTTPS identity to the disposable loopback server.
        # Only the worker holding the successful reservation result can enter this block.
        if send:
            original = attempts[results.index(winner)]
            binding = build_keycloak_role_grant_binding(**{
                field: original[field]
                for field in ("target", "event_id", "attempt_id", "deployment_policy_digest")
            })
            transport = KeycloakPostTimeout(forward=True)
            async with httpx.AsyncClient(
                base_url=ORIGIN, transport=transport, trust_env=False,
                follow_redirects=False, timeout=3,
            ) as writer:
                with pytest.raises(httpx.ReadTimeout):
                    await writer.post(
                        binding.endpoint_url.removeprefix(target.origin),
                        headers={**bearer(keycloak["writer"]), "Content-Type": "application/json"},
                        content=binding.body,
                    )
            assert transport.post_attempts == 1 and transport.upstream_status == 204

        # Discard the connection pool and load the original operation through fresh connections.
        await close_pool()
        assert await PostgresAtomicEffectStateStore().get(winner.operation_id) == winner
        for attempt in attempts:
            assert await reserve_keycloak_dispatch(**attempt) is None
        recovered = await get_keycloak_dispatch_intent(winner.operation_id)
        assert recovered is not None
        recovered_binding = verify_keycloak_role_grant_binding(
            target=recovered.target,
            event_id=recovered.event_id,
            attempt_id=recovered.attempt_id,
            deployment_policy_digest=recovered.deployment_policy_digest,
            approved_reference=recovered.approved_reference,
        )

        async with httpx.AsyncClient(base_url=ORIGIN, trust_env=False, timeout=3) as reader:
            bridge = KeycloakBridge(reader, keycloak, None)
            assert recovered_binding.endpoint_url == target.origin + bridge.path
            bridge.write_started_ms = int(datetime.fromisoformat(winner.updated_at).timestamp() * 1000)
            events = await bridge.audit_events()
            assert isinstance(events, list) and len(events) < AUDIT_PAGE_LIMIT
            payload = json.loads(recovered_binding.body)
            operation_id = bridge.audited_operation(events, role_payload=payload)
            mappings = await bridge.mappings()

        grant_events = [
            event for event in events
            if event.get("resourcePath") == bridge.audit_path and event.get("operationType") == "CREATE"
        ]
        assert len(grant_events) == int(send)
        assert (operation_id is not None) is send
        assert mappings == ([keycloak["role"]] if send else [])
        assert await PostgresAtomicEffectStateStore().get(winner.operation_id) == winner
    finally:
        await close_pool()
