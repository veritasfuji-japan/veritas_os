"""Standalone local custody head store and read-only HTTPS publication.

The writer is an offline, explicit custodian action. The HTTPS server has no
publish/update endpoint and may run under a separate read-only OS identity.
SQLite protects concurrent updates and ordinary API misuse, NOT a malicious
custodian OS administrator or whole-disk rollback. A verifier must separately
pin signer identity and its own minimum acceptable sequence (#2451).
"""
from __future__ import annotations

import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import ssl
import stat
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from scripts.validation.audit_checkpoint_signed_custody_v0_1 import (
    _SIGNED_KEYS,
    _format_receipt,
    _message,
    verify_signed_reference,
)
from scripts.validation.audit_registry_checkpoint_v0_1 import _digest
from scripts.validation.audit_remote_custody_https_v0_1 import (
    _FORMAT as REMOTE_FORMAT,
    _PATH as REMOTE_PATH,
    _SCOPE as REMOTE_SCOPE,
    _SHA,
)
from veritas_os.security.hash import canonical_json_dumps, sha256_hex

MAX_ENTRIES = 4096
ZERO = "0" * 64


class _Corruption(Exception):
    """A history gap, unsigned rewrite, or malformed local storage state."""


class _Capacity(Exception):
    """Avoid accepting or returning a truncated registry."""


def _open(db: Path, *, readonly: bool) -> sqlite3.Connection:
    if not isinstance(db, Path) or not db.is_absolute():
        raise ValueError("ABSOLUTE_CUSTODY_DB_PATH_REQUIRED")
    info = db.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("CUSTODY_STORE_NOT_REGULAR_FILE")
    if not readonly and info.st_uid != os.geteuid():
        raise PermissionError("CUSTODY_WRITER_NOT_OWNER")
    if readonly:
        conn = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=5, isolation_level=None)
        conn.execute("PRAGMA query_only=ON")
    else:
        conn = sqlite3.connect(db, timeout=5, isolation_level=None)
        conn.execute("PRAGMA synchronous=FULL")
    return conn


def create_store(db: Path, *, signer_public_key_hex: str) -> str:
    """Create one custodian-owned store; never replace an existing store."""
    if (
        not isinstance(db, Path) or not db.is_absolute()
        or not isinstance(signer_public_key_hex, str)
        or not _SHA.fullmatch(signer_public_key_hex)
    ):
        return "INPUT_INVALID"
    try:
        parent = db.parent.stat()
        if (
            not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != os.geteuid()
            or parent.st_mode & 0o022
        ):
            return "UNSAFE_CUSTODY_DIRECTORY"
        flags = os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(db, flags, 0o600)
        os.close(fd)
    except FileExistsError:
        return "STORE_ALREADY_EXISTS"
    except OSError:
        return "STORAGE_UNAVAILABLE"
    try:
        with _open(db, readonly=False) as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=DELETE;
                CREATE TABLE config (
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    public_key_hex TEXT NOT NULL
                );
                CREATE TABLE receipts (
                    sequence INTEGER PRIMARY KEY CHECK(sequence > 0),
                    receipt_hash TEXT NOT NULL UNIQUE,
                    previous_hash TEXT NOT NULL,
                    receipt_json TEXT NOT NULL
                );
                CREATE TRIGGER immutable_receipts_update
                BEFORE UPDATE ON receipts BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY'); END;
                CREATE TRIGGER immutable_receipts_delete
                BEFORE DELETE ON receipts BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY'); END;
                CREATE TRIGGER immutable_config_update
                BEFORE UPDATE ON config BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_CONFIG'); END;
                CREATE TRIGGER immutable_config_delete
                BEFORE DELETE ON config BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_CONFIG'); END;
                """
            )
            conn.execute(
                "INSERT INTO config (id, public_key_hex) VALUES (1, ?)",
                (signer_public_key_hex,),
            )
            conn.commit()
        return "STORE_CREATED"
    except (sqlite3.Error, OSError, ValueError):
        # Never silently overwrite or recreate a partially initialized store.
        return "STORAGE_UNAVAILABLE"


def _state(conn: sqlite3.Connection) -> tuple[str, int, str]:
    config = conn.execute("SELECT public_key_hex FROM config WHERE id=1").fetchall()
    if len(config) != 1 or not isinstance(config[0][0], str) or not _SHA.fullmatch(config[0][0]):
        raise _Corruption
    pub = config[0][0]
    count = conn.execute("SELECT count(*) FROM receipts").fetchone()[0]
    if not 0 <= count <= MAX_ENTRIES:
        raise _Capacity
    rows = conn.execute(
        "SELECT sequence, receipt_hash, previous_hash, receipt_json "
        "FROM receipts ORDER BY sequence LIMIT ?",
        (MAX_ENTRIES + 1,),
    ).fetchall()
    if len(rows) != count:
        raise _Corruption
    previous = ZERO
    key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub))
    for expected, (sequence, digest, parent, raw) in enumerate(rows, start=1):
        try:
            receipt = json.loads(raw)
            if (
                type(sequence) is not int or sequence != expected
                or not isinstance(digest, str) or not _SHA.fullmatch(digest)
                or not isinstance(parent, str) or not hmac.compare_digest(parent, previous)
                or not _format_receipt(receipt)
                or receipt["sequence"] != sequence
                or not hmac.compare_digest(_digest(receipt), digest)
                or not hmac.compare_digest(receipt["previous_receipt_sha256"], parent)
                or not hmac.compare_digest(
                    receipt["signer_key_id"], sha256_hex(bytes.fromhex(pub))
                )
            ):
                raise _Corruption
            signed = {name: receipt[name] for name in _SIGNED_KEYS}
            key.verify(bytes.fromhex(receipt["signature_ed25519"]), _message(signed))
        except (TypeError, KeyError, ValueError, InvalidSignature) as exc:
            raise _Corruption from exc
        previous = digest
    return pub, count, previous


def publish(db: Path, *, reference: Any, receipt: Any) -> str:
    """Validate the signer and perform exact-next-sequence CAS under BEGIN IMMEDIATE."""
    try:
        with _open(db, readonly=False) as conn:
            conn.execute("BEGIN IMMEDIATE")
            pub, sequence, previous = _state(conn)
            trusted = verify_signed_reference(
                reference=reference, receipt=receipt,
                trusted_public_key_hex=pub,
                expected_head_sha256=_digest(receipt),
            )
            if trusted != "SIGNED_LOCAL_BASELINE_VERIFIED":
                conn.rollback()
                return "UNTRUSTED_CUSTODY_RECEIPT"
            if type(receipt["sequence"]) is not int:
                conn.rollback()
                return "UNTRUSTED_CUSTODY_RECEIPT"
            if receipt["sequence"] == sequence and hmac.compare_digest(
                _digest(receipt), previous,
            ):
                conn.rollback()
                return "ALREADY_PUBLISHED"
            if (
                sequence >= MAX_ENTRIES
                or receipt["sequence"] != sequence + 1
                or receipt["previous_receipt_sha256"] != previous
            ):
                conn.rollback()
                return "HEAD_CONFLICT_OR_ROLLBACK"
            conn.execute(
                "INSERT INTO receipts (sequence, receipt_hash, previous_hash, receipt_json) "
                "VALUES (?, ?, ?, ?)",
                (
                    receipt["sequence"], _digest(receipt),
                    receipt["previous_receipt_sha256"],
                    canonical_json_dumps(receipt),
                ),
            )
            conn.commit()
            return "NEW_HEAD_PUBLISHED"
    except _Capacity:
        return "CAPACITY_REACHED"
    except _Corruption:
        return "HISTORY_INCOMPLETE"
    except (OSError, sqlite3.Error, ValueError, PermissionError):
        return "STORAGE_UNAVAILABLE"


def read_head(db: Path) -> tuple[str, dict[str, Any] | None]:
    """Independently recheck every retained signature/sequence before publication."""
    try:
        with _open(db, readonly=True) as conn:
            pub, count, latest = _state(conn)
        if not count:
            return "HEAD_UNAVAILABLE", None
        return "HEAD_OBSERVED", {
            "format_version": REMOTE_FORMAT,
            "scope": REMOTE_SCOPE,
            "signer_public_key_hex": pub,
            "latest_receipt_sha256": latest,
            "sequence": count,
        }
    except _Capacity:
        return "CAPACITY_REACHED", None
    except _Corruption:
        return "HISTORY_INCOMPLETE", None
    except (OSError, sqlite3.Error, ValueError, PermissionError):
        return "STORAGE_UNAVAILABLE", None


def make_readonly_handler(db: Path) -> type[BaseHTTPRequestHandler]:
    """A GET-only HTTP handler. The caller MUST serve it over verified TLS."""
    class ReadOnly(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != REMOTE_PATH:
                self.send_error(404)
                return
            status, head = read_head(db)
            if status != "HEAD_OBSERVED" or head is None:
                self.send_error(503, "CUSTODY_HEAD_UNAVAILABLE")
                return
            data = canonical_json_dumps(head).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:
            self.send_error(405, "READ_ONLY")

        def do_PUT(self) -> None:
            self.send_error(405, "READ_ONLY")

        def do_DELETE(self) -> None:
            self.send_error(405, "READ_ONLY")

        def log_message(self, *_: Any) -> None:
            pass

    return ReadOnly


def serve_tls(
    db: Path, *, certificate: Path, private_key: Path,
    listen_host: str = "127.0.0.1", port: int = 8443,
) -> None:
    """Separate read-only service process. No DB writer or signer code paths."""
    if not isinstance(listen_host, str) or type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("INVALID_LISTENER")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=str(certificate), keyfile=str(private_key))
    with ThreadingHTTPServer((listen_host, port), make_readonly_handler(db)) as server:
        server.socket = context.wrap_socket(server.socket, server_side=True)
        server.serve_forever()
