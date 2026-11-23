"""Exercise the Sandbox Bind path against an in-process SaaS role-grant model."""

import asyncio
from dataclasses import replace
import json

import pytest
from pydantic import SecretBytes

from veritas_os.policy import sandbox_bind_execution as execution
from veritas_os.policy import sandbox_reconciliation as reconciliation
from veritas_os.policy.sandbox_event_store import parse_event
from veritas_os.policy.sandbox_https_transport import SandboxHTTPSTransport
from veritas_os.policy.trusted_https_reconciliation import ApprovedReconciliationVerifier
from veritas_os.security.hash import sha256_of_canonical_json
from veritas_os.tests.test_native_bind_authorization_consumption import _Revocation
from veritas_os.tests.test_sandbox_action_binding_integration import issue_for_payload
from veritas_os.tests.test_sandbox_credential_resolution_integration import Provider
from veritas_os.tests.test_sandbox_https_transport import TOKEN as READER_TOKEN, Writer
from veritas_os.tests.test_sandbox_pre_effect import _args, consume_fixture_authorization
from veritas_os.tests.test_sandbox_reconciliation import ReaderProvider

pytestmark = pytest.mark.slow

TENANT = "fixture-tenant"
USER = "fixture-user"
ROLE = "report-viewer"
GRANT = {"tenant": TENANT, "user": USER, "role": ROLE}
WRITER_TOKEN = b"synthetic-test-writer-token-no-live-access"


def grant_event(**updates: str) -> dict[str, str]:
    return {
        "event_id": "12345678-1234-4234-8234-123456789abc",
        "message": json.dumps(GRANT | updates, sort_keys=True),
    }


@pytest.fixture(scope="module")
def consumed_grant(tmp_path_factory):
    artifact, inputs = issue_for_payload(
        tmp_path_factory.mktemp("saas-role-grant"), grant_event(),
    )
    return consume_fixture_authorization(artifact, inputs)


class WriterProvider(Provider):
    """Use fixture material that satisfies the real HTTP writer's length check."""

    async def resolve(self, request, *, expected_metadata_digest):
        credential = await super().resolve(
            request, expected_metadata_digest=expected_metadata_digest,
        )
        return credential.model_copy(update={"material": SecretBytes(WRITER_TOKEN)})


class DirectoryConnection(Writer):
    """Apply POSTs to synthetic membership state and expose evidence only via GET."""

    def __init__(self, directory, incoming, *, lose_ack):
        super().__init__()
        self.directory = directory
        self.incoming = incoming
        self.lose_ack = lose_ack

    def write(self, wire: bytes) -> None:
        super().write(wire)
        headers, _, body = wire.partition(b"\r\n\r\n")
        request_line, *fields = headers.decode().split("\r\n")
        method, path, _ = request_line.split()
        header_map = {}
        for field in fields:
            name, value = field.split(":", 1)
            header_map[name.lower()] = value.strip()
        if method == "POST":
            assert path == "/v1/events"
            assert header_map["authorization"] == "Bearer " + WRITER_TOKEN.decode()
            key = header_map["idempotency-key"]
            event = parse_event(body)
            grant = json.loads(event.message)
            self.directory.changes.append((grant["tenant"], grant["user"], grant["role"]))
            self.directory.operations[key] = {
                "operation_id": "22222222-2222-4222-8222-222222222222",
                "idempotency_key": key,
                "event_id": event.event_id,
                "payload_digest": sha256_of_canonical_json(event.model_dump()),
                "state": "PERSISTED",
            }
            if not self.lose_ack:
                self.respond(201, self.directory.operations[key])
        else:
            assert method == "GET"
            assert header_map["authorization"] == "Bearer " + READER_TOKEN.decode()
            prefix = "/v1/operations?idempotency_key="
            assert path.startswith(prefix)
            operation = self.directory.operations.get(path.removeprefix(prefix))
            if operation is None:
                self.respond(404, {})
            else:
                self.respond(200, operation)
        self.incoming.feed_eof()

    def respond(self, status: int, operation: dict) -> None:
        body = json.dumps(operation).encode()
        self.incoming.feed_data(
            (f"HTTP/1.1 {status} Test\r\nContent-Type: application/json\r\n"
             f"Content-Length: {len(body)}\r\n\r\n").encode() + body,
        )


class SyntheticDirectory:
    """A test-only directory with no DNS, sockets, or service credentials."""

    def __init__(self, *, lose_ack: bool = False):
        self.changes = []
        self.operations = {}
        self.connections = []
        self.lose_ack = lose_ack

    async def connect(self, host, port, **kwargs):
        assert (host, port) == ("sandbox.example.invalid", 443)
        incoming = asyncio.StreamReader()
        writer = DirectoryConnection(self, incoming, lose_ack=self.lose_ack)
        self.connections.append(writer)
        return incoming, writer


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["tenant", "user", "role", "revoked"])
async def test_mismatch_or_revocation_prevents_the_saas_write(
    consumed_grant, monkeypatch, case,
):
    artifact, args = await _args(consumed_grant)
    directory = SyntheticDirectory()
    monkeypatch.setattr(asyncio, "open_connection", directory.connect)
    transport = SandboxHTTPSTransport(endpoint_url=args["deployment"].endpoint_url)
    provider = WriterProvider(consumed_grant, args)
    payload = grant_event()
    if case == "revoked":
        current = consumed_grant[3]
        revoked_governance = replace(
            current.governance,
            authority_revocation_checker=_Revocation(current.governance, "revoked"),
        )
        args["load_current_inputs"] = lambda _now: replace(
            current, governance=revoked_governance,
        )
    else:
        payload = grant_event(**{case: "different-fixture-value"})

    with pytest.raises(execution.SandboxBindExecutionError):
        await execution.execute_sandbox_bind(
            artifact, json.dumps(payload), provider=provider, transport=transport, **args,
        )

    assert transport.send_calls == 0
    assert directory.connections == []
    assert directory.changes == []
    assert directory.operations == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("lose_ack", [False, True])
async def test_exact_grant_writes_once_and_only_lookup_confirms_effect(
    consumed_grant, monkeypatch, lose_ack,
):
    artifact, args = await _args(consumed_grant)
    directory = SyntheticDirectory(lose_ack=lose_ack)
    monkeypatch.setattr(asyncio, "open_connection", directory.connect)
    transport = SandboxHTTPSTransport(endpoint_url=args["deployment"].endpoint_url)
    provider = WriterProvider(consumed_grant, args)
    payload = json.dumps(grant_event())

    observation = await execution.execute_sandbox_bind(
        artifact, payload, provider=provider, transport=transport, **args,
    )
    assert observation.reason_code == (
        "TRANSPORT_FAILED_OR_UNKNOWN" if lose_ack else "HTTP_201_MATCHING_ACK"
    )
    row = await args["effect_store"].get(observation.attempt_id)
    assert row.state == execution.EffectExecutionState.EFFECT_UNKNOWN
    assert directory.changes == [(TENANT, USER, ROLE)]
    assert transport.send_calls == len(directory.connections) == 1
    assert len(directory.connections[0].writes) == 1

    with pytest.raises(execution.SandboxBindExecutionError):
        await execution.execute_sandbox_bind(
            artifact, payload, provider=provider, transport=transport, **args,
        )
    assert transport.send_calls == len(directory.connections) == 1
    assert directory.changes == [(TENANT, USER, ROLE)]

    history = args.pop("governance_inputs")
    args.pop("load_current_inputs")
    reader = reconciliation.SandboxReaderPolicy(
        "saas-fixture-reader", "reader-v1", "synthetic", "sandbox",
    )
    verifier = ApprovedReconciliationVerifier(
        reconciliation.VERIFIER_ID,
        reconciliation.sandbox_reconciliation_policy_hash(args["deployment"], reader),
    )
    reader_provider = ReaderProvider(consumed_grant[4])
    result = await reconciliation.reconcile_sandbox_effect(
        artifact, payload, historical_governance_inputs=history, reader_policy=reader,
        verifier_policy=reconciliation.ReconciliationVerifierPolicy((verifier,)),
        provider=reader_provider, **args,
    )
    assert result.record.state == execution.EffectExecutionState.CONFIRMED_EFFECT
    assert result.evidence is not None
    assert reader_provider.calls[0].credential_scope == reconciliation.LOOKUP_SCOPE
    assert reader.credential_reference_id != args["deployment"].credential_reference_id
    assert len(directory.connections) == 2
    assert len(directory.connections[1].writes) == 1
    assert directory.connections[1].writes[0].startswith(
        f"GET /v1/operations?idempotency_key={artifact.idempotency_key} ".encode(),
    )
    assert directory.changes == [(TENANT, USER, ROLE)]
