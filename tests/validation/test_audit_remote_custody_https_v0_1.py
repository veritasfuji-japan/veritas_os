"""Negative tests for opt-in HTTPS remote audit custody head retrieval."""
from __future__ import annotations

from pathlib import Path
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import ssl
import subprocess
import threading

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import pytest

from scripts.validation import audit_remote_custody_https_v0_1 as remote
from scripts.validation.audit_checkpoint_signed_custody_v0_1 import sign_checkpoint
from scripts.validation.audit_registry_checkpoint_v0_1 import _digest

ZERO = "0" * 64
HOST = "custody.example.invalid"
URL = "https://" + HOST + "/v1/audit/checkpoints/latest"


def fixture():
    entries = [{"packet_id": "local-A", "packet_hash": "a" * 64, "case_count": 1}]
    root = {
        "format_version": "veritas.audit-registry-checkpoint/0.1",
        "packet_count": 1, "case_count": 1, "packets": entries,
    }
    baseline = {
        **root,
        "scope": "LOCAL_UNAUTHENTICATED_AUDIT_INVENTORY",
        "origin_authentication": "NOT_PERFORMED",
        "external_anchor": "NOT_EMBEDDED",
        "snapshot_root": _digest(root),
    }
    baseline["checkpoint_hash"] = _digest(baseline)
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw,
    ).hex()
    receipt = sign_checkpoint(
        baseline,
        private_key_raw=key.private_bytes_raw(),
        sequence=1,
        previous_receipt_sha256=ZERO,
    )
    anchor = {
        "format_version": "veritas.audit-custody-remote-head/0.1",
        "scope": "LOCAL_AUDIT_OBSERVATION_ONLY",
        "signer_public_key_hex": pub,
        "latest_receipt_sha256": _digest(receipt),
        "sequence": 1,
    }
    return baseline, receipt, pub, anchor


@pytest.mark.parametrize("endpoint,hostname", [
    ("http://" + HOST + "/v1/audit/checkpoints/latest", HOST),
    ("https://attacker.invalid/v1/audit/checkpoints/latest", HOST),
    ("https://user:pass@" + HOST + "/v1/audit/checkpoints/latest", HOST),
    ("https://" + HOST + "/v1/audit/checkpoints/latest?q=x", HOST),
    ("https://" + HOST + "/v1/audit/checkpoints/latest#fragment", HOST),
    ("https://" + HOST + "/redirect", HOST),
    ("https://" + HOST + ":invalid/v1/audit/checkpoints/latest", HOST),
    ("https://" + HOST + "/v1/audit/checkpoints/latest", "not..valid"),
    ("https://" + HOST + "/v1/audit/checkpoints/latest", ""),
])
def test_malformed_target_rejected(endpoint, hostname):
    assert remote._parse_url(endpoint, hostname) is None


def test_duplicate_anchor_json_keys_never_accepted():
    with pytest.raises(ValueError, match="DUPLICATE_ANCHOR_KEY"):
        remote._reject_duplicate_keys([("sequence", 1), ("sequence", 2)])


@pytest.mark.parametrize("mutation", [
    lambda x: x.update(scope="ACTUATE_RUNTIME"),
    lambda x: x.update(sequence=True),
    lambda x: x.update(sequence=0),
    lambda x: x.update(sequence=1_000_000_001),
    lambda x: x.update(latest_receipt_sha256="invalid"),
    lambda x: x.update(signer_public_key_hex="f"),
    lambda x: x.update(unexpected="PASS"),
])
def test_invalid_head_contract_rejected(mutation):
    _, _, _, anchor = fixture()
    mutation(anchor)
    assert remote._valid_head(anchor) is False


@pytest.mark.asyncio
async def test_transport_failure_never_enters_registry(monkeypatch):
    baseline, receipt, pub, _ = fixture()
    def failure(**_):
        raise OSError("offline / wrong CA / failed DNS")
    async def access(**_):
        raise AssertionError("must not query registry")
    monkeypatch.setattr(remote, "_fetch_blocking", failure)
    monkeypatch.setattr(remote, "check_registry_against_signed_reference", access)
    assert await remote.verify_registry_against_https_custody(
        reference=baseline, receipt=receipt,
        endpoint=URL, expected_hostname=HOST, ca_bundle=Path("independent-ca.pem"),
        trusted_signer_public_key_hex=pub, minimum_sequence=1,
    ) == "REMOTE_ANCHOR_UNAVAILABLE"


@pytest.mark.asyncio
async def test_public_key_substitution_fails_before_registry(monkeypatch):
    baseline, receipt, pub, anchor = fixture()
    wrong = dict(anchor, signer_public_key_hex="f" * 64)
    monkeypatch.setattr(remote, "_fetch_blocking", lambda **_: wrong)
    async def access(**_):
        raise AssertionError("wrong signer trusted")
    monkeypatch.setattr(remote, "check_registry_against_signed_reference", access)
    result = await remote.verify_registry_against_https_custody(
        reference=baseline, receipt=receipt,
        endpoint=URL, expected_hostname=HOST, ca_bundle=Path("anchor-ca.pem"),
        trusted_signer_public_key_hex=pub, minimum_sequence=1,
    )
    assert result == "REMOTE_SIGNER_PIN_MISMATCH"


@pytest.mark.asyncio
async def test_remote_rollback_detected_with_external_minimum(monkeypatch):
    baseline, receipt, pub, anchor = fixture()
    monkeypatch.setattr(remote, "_fetch_blocking", lambda **_: anchor)
    assert await remote.verify_registry_against_https_custody(
        reference=baseline, receipt=receipt,
        endpoint=URL, expected_hostname=HOST, ca_bundle=Path("anchor-ca.pem"),
        trusted_signer_public_key_hex=pub, minimum_sequence=2,
    ) == "REMOTE_HEAD_SEQUENCE_ROLLBACK"


@pytest.mark.asyncio
async def test_receipt_sequence_mismatch_rejected(monkeypatch):
    baseline, receipt, pub, anchor = fixture()
    monkeypatch.setattr(remote, "_fetch_blocking", lambda **_: dict(anchor, sequence=2))
    assert await remote.verify_registry_against_https_custody(
        reference=baseline, receipt=receipt,
        endpoint=URL, expected_hostname=HOST, ca_bundle=Path("anchor-ca.pem"),
        trusted_signer_public_key_hex=pub, minimum_sequence=1,
    ) == "REMOTE_RECEIPT_SEQUENCE_MISMATCH"


@pytest.mark.asyncio
async def test_valid_remote_pin_delegates_signed_verification(monkeypatch):
    baseline, receipt, pub, anchor = fixture()
    monkeypatch.setattr(remote, "_fetch_blocking", lambda **_: anchor)
    called = []
    async def verify(**kw):
        called.append(kw)
        return "HISTORY_DIVERGED"
    monkeypatch.setattr(remote, "check_registry_against_signed_reference", verify)
    result = await remote.verify_registry_against_https_custody(
        reference=baseline, receipt=receipt,
        endpoint=URL, expected_hostname=HOST, ca_bundle=Path("anchor-ca.pem"),
        trusted_signer_public_key_hex=pub, minimum_sequence=1,
    )
    assert result == "HISTORY_DIVERGED"
    assert called == [{
        "reference": baseline,
        "receipt": receipt,
        "trusted_public_key_hex": pub,
        "expected_head_sha256": anchor["latest_receipt_sha256"],
    }]


@pytest.mark.asyncio
async def test_missing_external_trust_inputs_prevents_transport(monkeypatch):
    baseline, receipt, pub, _ = fixture()
    def access(**_):
        raise AssertionError("must not fetch anchor")
    monkeypatch.setattr(remote, "_fetch_blocking", access)
    for key, minimum in (("", 1), (pub, True), (pub, 0)):
        result = await remote.verify_registry_against_https_custody(
            reference=baseline, receipt=receipt,
            endpoint=URL, expected_hostname=HOST, ca_bundle=Path("anchor-ca.pem"),
            trusted_signer_public_key_hex=key, minimum_sequence=minimum,
        )
        assert result == "EXTERNAL_TRUST_REQUIRED"


@pytest.mark.asyncio
async def test_invalid_remote_head_fails_closed(monkeypatch):
    monkeypatch.setattr(remote, "_fetch_blocking", lambda **_: {"pass": True})
    status, anchor = await remote.fetch_https_anchor(
        endpoint=URL, expected_hostname=HOST, ca_bundle=Path("anchor-ca.pem"),
    )
    assert status == "REMOTE_ANCHOR_INVALID" and anchor is None


# These tests exercise actual TLS socket handshakes, not a mocked fetch.


def _make_tls_certs(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    ca = tmp_path / "ca.pem"
    ca_key = tmp_path / "ca.key"
    key = tmp_path / "server.key"
    csr = tmp_path / "server.csr"
    cert = tmp_path / "server.pem"
    ext = tmp_path / "ext.cnf"
    ext.write_text("subjectAltName=DNS:localhost\nextendedKeyUsage=serverAuth\n")
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-days", "1", "-keyout", str(ca_key), "-out", str(ca),
        "-subj", "/CN=VERITAS Remote Custody Synthetic CA",
    ], check=True, capture_output=True)
    subprocess.run([
        "openssl", "req", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(key), "-out", str(csr),
        "-subj", "/CN=localhost",
    ], check=True, capture_output=True)
    subprocess.run([
        "openssl", "x509", "-req", "-days", "1", "-in", str(csr),
        "-CA", str(ca), "-CAkey", str(ca_key), "-CAcreateserial",
        "-out", str(cert), "-extfile", str(ext),
    ], check=True, capture_output=True)
    return ca, cert, key


@contextmanager
def synthetic_https_anchor(tmp_path, anchor, *, status_code=200, content_type="application/json"):
    ca, cert, key = _make_tls_certs(tmp_path)
    body = (
        json.dumps(anchor, separators=(",", ":")).encode("utf-8")
        if not isinstance(anchor, bytes) else anchor
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != remote._PATH:
                self.send_error(404)
                return
            self.send_response(status_code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(cert), str(key))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield (
            "https://localhost:" + str(server.server_port) + remote._PATH,
            ca,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.asyncio
async def test_real_https_ca_and_hostname_authentication(tmp_path):
    _, _, _, anchor = fixture()
    with synthetic_https_anchor(tmp_path / "first", anchor) as (url, ca):
        state, observed = await remote.fetch_https_anchor(
            endpoint=url, expected_hostname="localhost", ca_bundle=ca,
        )
        assert state == "REMOTE_ANCHOR_OBSERVED"
        assert observed == anchor
        assert (await remote.fetch_https_anchor(
            endpoint=url, expected_hostname="wronghost", ca_bundle=ca,
        ))[0] == "REMOTE_ENDPOINT_INVALID"
        wrong_ca, _, _ = _make_tls_certs(tmp_path / "independent")
        assert (await remote.fetch_https_anchor(
            endpoint=url, expected_hostname="localhost",
            ca_bundle=wrong_ca,
        ))[0] == "REMOTE_ANCHOR_UNAVAILABLE"


@pytest.mark.asyncio
async def test_real_https_refuses_redirect_oversized_body_and_invalid_json(tmp_path):
    _, _, _, anchor = fixture()
    conditions = [
        (anchor, 302, "application/json"),
        (b"x" * 5000, 200, "application/json"),
        (b'{"sequence":1,"sequence":2}', 200, "application/json"),
        (anchor, 200, "text/html"),
    ]
    for n, (body, status_code, content_type) in enumerate(conditions):
        folder = tmp_path / str(n)
        folder.mkdir()
        with synthetic_https_anchor(
            folder, body, status_code=status_code, content_type=content_type,
        ) as (url, ca):
            state, observed = await remote.fetch_https_anchor(
                endpoint=url, expected_hostname="localhost", ca_bundle=ca,
            )
            assert state != "REMOTE_ANCHOR_OBSERVED"
            assert observed is None
