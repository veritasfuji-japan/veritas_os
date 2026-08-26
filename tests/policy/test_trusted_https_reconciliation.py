from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import ssl
from threading import Thread
from typing import Any, Mapping

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from veritas_os.policy.bind_effect_reconciliation import (
    BindEffectStateError,
    EffectExecutionState,
    EffectStateTrackingConsumptionStore,
    InMemoryAtomicEffectStateStore,
    ReconciliationClaim,
    ReconciliationEvidence,
    classify_completed_bind_attempt,
    reconcile_effect_unknown,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption import (
    BindAuthorizationConsumptionResult,
)
from veritas_os.policy.live_adapter_bind_authorization_consumption_store import (
    InMemoryAtomicAuthorizationConsumptionStore,
    build_authorization_consumption_record,
)
from veritas_os.policy.trusted_https_reconciliation import (
    ApprovedReconciliationVerifier,
    ReconciliationVerifierPolicy,
    TrustedHttpsReconciliationError,
    TrustedHttpsReconciliationVerifier,
    TrustedReconciliationEndpoint,
    reconciliation_observation_digest,
)
from veritas_os.security.hash import sha256_of_canonical_json

ACK = {
    "veritas_operation_id": "consumption-1",
    "external_operation_reference": "external-1",
    "status": "committed",
    "source_identity": "trusted-ledger",
    "authorization_id": "authorization-1",
    "consumption_id": "consumption-1",
}


class _Response:
    def __init__(self, payload: Any = ACK, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.request = httpx.Request("GET", "https://ledger.example.test")

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "failed",
                request=self.request,
                response=httpx.Response(self.status_code),
            )


class _Client:
    response = _Response()
    error: Exception | None = None
    last_url = ""
    kwargs: dict[str, Any] = {}

    def __init__(self, **kwargs: Any) -> None:
        type(self).kwargs = kwargs

    async def __aenter__(self) -> _Client:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, url: str, **kwargs: Any) -> _Response:
        del kwargs
        type(self).last_url = url
        if self.error is not None:
            raise self.error
        return self.response


@dataclass(frozen=True)
class _Receipt:
    pass


@dataclass(frozen=True)
class _Headers:
    values: Mapping[str, str]

    async def authorization_headers(self) -> Mapping[str, str]:
        return self.values


def _endpoint(**changes: Any) -> TrustedReconciliationEndpoint:
    values = {
        "scheme": "https",
        "host": "ledger.example.test",
        "port": 8443,
        "path_prefix": "/v1/effects",
        "source_type": "external_https_api",
        "source_identity": "trusted-ledger",
    }
    values.update(changes)
    return TrustedReconciliationEndpoint(**values)


def _verifier(
    *, endpoint: TrustedReconciliationEndpoint | None = None, approved: bool = True
) -> TrustedHttpsReconciliationVerifier:
    endpoint = endpoint or _endpoint()
    policy_hash = TrustedHttpsReconciliationVerifier.policy_hash_for_config(
        endpoint=endpoint, verifier_id="reconciliation-verifier-1"
    )
    if not approved:
        policy_hash = "0" * 64
    return TrustedHttpsReconciliationVerifier(
        endpoint=endpoint,
        verifier_id="reconciliation-verifier-1",
        verifier_policy=ReconciliationVerifierPolicy(
            (ApprovedReconciliationVerifier("reconciliation-verifier-1", policy_hash),)
        ),
    )


def _evidence(**changes: Any) -> ReconciliationEvidence:
    values = {
        "operation_id": "consumption-1",
        "authorization_id": "authorization-1",
        "consumption_id": "consumption-1",
        "claim": ReconciliationClaim.CONFIRMED_EFFECT,
        "source_type": "external_https_api",
        "source_identity": "trusted-ledger",
        "observed_at": "2026-08-26T12:00:00+00:00",
        "external_operation_reference": "external-1",
        "external_ack_digest": sha256_of_canonical_json(ACK),
        "observation_digest": "0" * 64,
    }
    values.update(changes)
    provisional = ReconciliationEvidence(**values)
    if "observation_digest" not in changes:
        values["observation_digest"] = reconciliation_observation_digest(provisional)
    return ReconciliationEvidence(**values)


@pytest.fixture(autouse=True)
def _http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    _Client.response = _Response()
    _Client.error = None
    _Client.last_url = ""
    monkeypatch.setattr(
        "veritas_os.policy.trusted_https_reconciliation.httpx.AsyncClient", _Client
    )


@pytest.mark.asyncio
async def test_valid_acknowledgement_is_independently_verified() -> None:
    evidence = _evidence()
    verified = await _verifier().verify(evidence)

    assert verified.evidence == evidence
    assert verified.verifier_id == "reconciliation-verifier-1"
    assert _Client.last_url == (
        "https://ledger.example.test:8443/v1/effects/external-1"
    )
    assert _Client.kwargs["follow_redirects"] is False
    context = _Client.kwargs["verify"]
    assert context.check_hostname is True
    assert context.verify_mode.name == "CERT_REQUIRED"


@pytest.mark.asyncio
async def test_format_version_is_bound_by_observation_digest() -> None:
    evidence = _evidence()
    substituted = evidence.model_copy(
        update={"format_version": "bind-effect-reconciliation-evidence/v2"}
    )

    assert reconciliation_observation_digest(substituted) != (
        reconciliation_observation_digest(evidence)
    )
    with pytest.raises(TrustedHttpsReconciliationError, match="FORMAT_VERSION"):
        await _verifier().verify(substituted)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"external_operation_reference": "wrong"}, "OPERATION_REFERENCE"),
        ({"external_ack_digest": "a" * 64}, "ACK_DIGEST"),
        ({"observation_digest": "b" * 64}, "OBSERVATION_DIGEST"),
        ({"source_identity": "attacker"}, "SOURCE_IDENTITY"),
        ({"source_type": "caller_object"}, "SOURCE_TYPE"),
        ({"observed_at": "not-a-time"}, "OBSERVED_AT"),
        ({"observed_at": "2026-08-26T12:00:00"}, "OBSERVED_AT"),
    ],
)
async def test_untrusted_evidence_fails_closed(
    changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(TrustedHttpsReconciliationError, match=message):
        await _verifier().verify(_evidence(**changes))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"malformed": True}, "ACK_RETRIEVAL"),
        ({**ACK, "external_operation_reference": "wrong"}, "OPERATION_REFERENCE"),
        ({**ACK, "source_identity": "wrong"}, "SOURCE_IDENTITY"),
        ({**ACK, "status": "invented"}, "STATUS_UNSUPPORTED"),
        ({**ACK, "status": "rejected"}, "CLAIM_CONTRADICTED"),
        ({**ACK, "authorization_id": "wrong"}, "AUTHORIZATION_LINEAGE"),
        ({**ACK, "consumption_id": "wrong"}, "CONSUMPTION_LINEAGE"),
    ],
)
async def test_untrusted_acknowledgement_fails_closed(
    payload: dict[str, Any], message: str
) -> None:
    _Client.response = _Response(payload)
    with pytest.raises(TrustedHttpsReconciliationError, match=message):
        await _verifier().verify(_evidence())


@pytest.mark.asyncio
async def test_tls_or_network_failure_fails_closed() -> None:
    request = httpx.Request("GET", "https://ledger.example.test")
    _Client.error = httpx.ConnectError("certificate verify failed", request=request)
    with pytest.raises(TrustedHttpsReconciliationError, match="ACK_RETRIEVAL"):
        await _verifier().verify(_evidence())


def test_endpoint_substitution_and_unapproved_policy_fail_closed() -> None:
    with pytest.raises(TrustedHttpsReconciliationError, match="ENDPOINT_INVALID"):
        _verifier(endpoint=_endpoint(scheme="http"))
    with pytest.raises(TrustedHttpsReconciliationError, match="ENDPOINT_INVALID"):
        _verifier(endpoint=_endpoint(host="trusted.test@attacker.test"))
    with pytest.raises(TrustedHttpsReconciliationError, match="VERIFIER_NOT_APPROVED"):
        _verifier(approved=False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "header_name",
    ["Host", "HOST", "content-length", "Connection", "Transfer-Encoding"],
)
async def test_credential_provider_cannot_override_transport_headers(
    header_name: str,
) -> None:
    endpoint = _endpoint()
    policy_hash = TrustedHttpsReconciliationVerifier.policy_hash_for_config(
        endpoint=endpoint, verifier_id="reconciliation-verifier-1"
    )
    verifier = TrustedHttpsReconciliationVerifier(
        endpoint=endpoint,
        verifier_id="reconciliation-verifier-1",
        verifier_policy=ReconciliationVerifierPolicy(
            (ApprovedReconciliationVerifier("reconciliation-verifier-1", policy_hash),)
        ),
        credential_provider=_Headers({header_name: "attacker-controlled"}),
    )

    with pytest.raises(TrustedHttpsReconciliationError, match="CREDENTIAL_FAILED"):
        await verifier.verify(_evidence())


def _write_test_certificates(
    directory: Path, *, certificate_name: str, hostname: str
) -> tuple[Path, Path, Path]:
    """Create an ephemeral CA and server certificate for local TLS tests."""
    now = datetime.now(UTC)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    try:
        san: x509.GeneralName = x509.IPAddress(ipaddress.ip_address(hostname))
    except ValueError:
        san = x509.DNSName(hostname)
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(server_name)
        .issuer_name(ca_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([san]), critical=False)
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    ca_path = directory / f"{certificate_name}-ca.pem"
    cert_path = directory / f"{certificate_name}-server.pem"
    key_path = directory / f"{certificate_name}-server-key.pem"
    ca_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    cert_path.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return ca_path, cert_path, key_path


def _start_https_server(
    cert_path: Path, key_path: Path, acknowledgement: dict[str, Any]
) -> tuple[ThreadingHTTPServer, Thread]:
    """Start a real loopback TLS server returning one acknowledgement."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = json.dumps(
                acknowledgement, sort_keys=True, separators=(",", ":")
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


@pytest.mark.asyncio
async def test_real_tls_handshake_and_certificate_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise real OpenSSL success, foreign-CA, and hostname failures."""
    monkeypatch.undo()
    acknowledgement = {
        "veritas_operation_id": "internal-operation-1",
        "external_operation_reference": "provider-operation-9",
        "status": "committed",
        "source_identity": "local-trusted-ledger",
        "authorization_id": "authorization-1",
        "consumption_id": "consumption-1",
    }
    trusted_ca, cert, key = _write_test_certificates(
        tmp_path, certificate_name="trusted", hostname="127.0.0.1"
    )
    foreign_ca, _, _ = _write_test_certificates(
        tmp_path, certificate_name="foreign", hostname="127.0.0.1"
    )
    mismatch_ca, mismatch_cert, mismatch_key = _write_test_certificates(
        tmp_path, certificate_name="mismatch", hostname="localhost"
    )
    trusted_server, trusted_thread = _start_https_server(cert, key, acknowledgement)
    mismatch_server, mismatch_thread = _start_https_server(
        mismatch_cert, mismatch_key, acknowledgement
    )

    def verifier(port: int, ca_file: Path) -> TrustedHttpsReconciliationVerifier:
        endpoint = _endpoint(
            host="127.0.0.1",
            port=port,
            source_identity="local-trusted-ledger",
            ca_file=str(ca_file),
        )
        policy_hash = TrustedHttpsReconciliationVerifier.policy_hash_for_config(
            endpoint=endpoint, verifier_id="real-tls-verifier"
        )
        return TrustedHttpsReconciliationVerifier(
            endpoint=endpoint,
            verifier_id="real-tls-verifier",
            verifier_policy=ReconciliationVerifierPolicy(
                (ApprovedReconciliationVerifier("real-tls-verifier", policy_hash),)
            ),
        )

    evidence = _evidence(
        operation_id="internal-operation-1",
        external_operation_reference="provider-operation-9",
        source_identity="local-trusted-ledger",
        external_ack_digest=sha256_of_canonical_json(acknowledgement),
    )
    try:
        verified = await verifier(trusted_server.server_port, trusted_ca).verify(
            evidence
        )
        assert verified.evidence == evidence
        with pytest.raises(TrustedHttpsReconciliationError, match="ACK_RETRIEVAL"):
            await verifier(trusted_server.server_port, foreign_ca).verify(evidence)
        with pytest.raises(TrustedHttpsReconciliationError, match="ACK_RETRIEVAL"):
            await verifier(mismatch_server.server_port, mismatch_ca).verify(evidence)
    finally:
        trusted_server.shutdown()
        mismatch_server.shutdown()
        trusted_server.server_close()
        mismatch_server.server_close()
        trusted_thread.join(timeout=2)
        mismatch_thread.join(timeout=2)


@pytest.mark.asyncio
async def test_production_verifier_reconciles_effect_unknown() -> None:
    consumption = build_authorization_consumption_record(
        live_adapter_bind_authorization_id="authorization-1",
        live_adapter_bind_authorization_hash="a" * 64,
        idempotency_key="idem-1",
        bind_context_hash="b" * 64,
        execution_intent_id="intent-1",
        execution_intent_hash="c" * 64,
        endpoint_identity_binding_digest="endpoint",
        credential_reference_digest="credential",
        credential_scope_binding_digest="scope",
        consumed_at="2026-08-26T11:59:00+00:00",
    )
    authorization_store = InMemoryAtomicAuthorizationConsumptionStore()
    effect_store = InMemoryAtomicEffectStateStore()
    tracking_store = EffectStateTrackingConsumptionStore(
        authorization_store, effect_store
    )
    assert await tracking_store.consume_once(consumption)
    await classify_completed_bind_attempt(
        result=BindAuthorizationConsumptionResult(
            consumption_record=consumption,
            bind_receipt=_Receipt(),  # type: ignore[arg-type]
            adapter_apply_attempted=True,
        ),
        effect_store=effect_store,
        updated_at="2026-08-26T12:00:00+00:00",
    )

    acknowledgement = {
        **ACK,
        "veritas_operation_id": consumption.consumption_id,
        "consumption_id": consumption.consumption_id,
    }
    _Client.response = _Response(acknowledgement)

    terminal = await reconcile_effect_unknown(
        operation_id=consumption.consumption_id,
        evidence=_evidence(
            operation_id=consumption.consumption_id,
            consumption_id=consumption.consumption_id,
            external_ack_digest=sha256_of_canonical_json(acknowledgement),
        ),
        verifier=_verifier(),
        effect_store=effect_store,
        updated_at="2026-08-26T12:01:00+00:00",
    )
    assert terminal.state == EffectExecutionState.CONFIRMED_EFFECT


@pytest.mark.asyncio
async def test_failed_verification_cannot_confirm_effect() -> None:
    consumption = build_authorization_consumption_record(
        live_adapter_bind_authorization_id="authorization-1",
        live_adapter_bind_authorization_hash="a" * 64,
        idempotency_key="idem-2",
        bind_context_hash="b" * 64,
        execution_intent_id="intent-1",
        execution_intent_hash="c" * 64,
        endpoint_identity_binding_digest="endpoint",
        credential_reference_digest="credential",
        credential_scope_binding_digest="scope",
        consumed_at="2026-08-26T11:59:00+00:00",
    )
    effect_store = InMemoryAtomicEffectStateStore()
    tracking_store = EffectStateTrackingConsumptionStore(
        InMemoryAtomicAuthorizationConsumptionStore(), effect_store
    )
    assert await tracking_store.consume_once(consumption)
    await classify_completed_bind_attempt(
        result=BindAuthorizationConsumptionResult(
            consumption_record=consumption,
            bind_receipt=_Receipt(),  # type: ignore[arg-type]
            adapter_apply_attempted=True,
        ),
        effect_store=effect_store,
        updated_at="2026-08-26T12:00:00+00:00",
    )
    evidence = _evidence(
        operation_id=consumption.consumption_id,
        consumption_id=consumption.consumption_id,
        observation_digest="f" * 64,
    )
    with pytest.raises(BindEffectStateError, match="VERIFICATION_FAILED"):
        await reconcile_effect_unknown(
            operation_id=consumption.consumption_id,
            evidence=evidence,
            verifier=_verifier(),
            effect_store=effect_store,
            updated_at="2026-08-26T12:01:00+00:00",
        )
    state = await effect_store.get(consumption.consumption_id)
    assert state is not None
    assert state.state == EffectExecutionState.EFFECT_UNKNOWN
