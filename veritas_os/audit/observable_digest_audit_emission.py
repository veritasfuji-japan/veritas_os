"""Append-only emission for observable-digest audit entries.

This module adds one bounded side effect to the pure audit-entry layer:
append the already-built audit record to an explicit local JSONL path and
synchronize that write to the local filesystem.

It does not interpret, resolve, remediate, retry, deduplicate, authorize, or
act on the record. The emitted bytes represent exactly the contract payload
already produced by ObservableDigestFailureAuditEntry.to_contract_dict().

Ordering claim:
- append order is preserved for calls serialized through this process-local
  emitter lock;
- no distributed or cross-host ordering claim is made.

Durability claim:
- a successful receipt means the full JSONL record was written and os.fsync()
  completed for the file descriptor;
- this is a bounded local-filesystem durability claim, not a replication,
  database, WORM, or multi-host durability claim.

Failure claim:
- write/fsync/close failures are explicit;
- after a write-stage or later failure, callers must not infer that the record
  is absent and must not treat automatic retry as safe.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from veritas_os.audit.observable_digest_audit_entry import (
    ObservableDigestFailureAuditEntry,
)


_EMISSION_LOCK = threading.RLock()
_DURABILITY_FSYNC_COMPLETED = "fsync_completed"

_EMISSION_NOT_CONFIRMED = "NOT_EMITTED"
_EMISSION_UNKNOWN = "EMISSION_UNKNOWN"
_DURABILITY_UNKNOWN = "DURABILITY_UNKNOWN"


@dataclass(frozen=True)
class ObservableDigestAuditEmissionReceipt:
    """Immutable evidence that one local append completed and was fsynced."""

    event_id: str
    schema_version: str
    path: str
    record_sha256: str
    bytes_written: int
    durability: str = _DURABILITY_FSYNC_COMPLETED


class ObservableDigestAuditEmissionError(RuntimeError):
    """Explicit append-only emission failure.

    outcome intentionally distinguishes failures that happened before a
    record write from failures where record presence or durability is no
    longer safe to infer.
    """

    def __init__(
        self,
        *,
        stage: str,
        outcome: str,
        path: Path,
        record_sha256: str,
        bytes_written: int | None = None,
        detail: str,
    ) -> None:
        self.stage = stage
        self.outcome = outcome
        self.path = str(path)
        self.record_sha256 = record_sha256
        self.bytes_written = bytes_written
        super().__init__(
            "observable_digest_audit_emission_failed:"
            f" stage={stage} outcome={outcome} detail={detail}"
        )


def _canonical_record_bytes(entry: ObservableDigestFailureAuditEntry) -> bytes:
    payload = entry.to_contract_dict()
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return serialized.encode("utf-8")


def _validate_target(path: Path) -> None:
    if path.exists() and path.is_dir():
        raise ValueError("audit emission path must not be a directory")
    if path.exists() and path.is_symlink():
        raise ValueError("audit emission path must not be a symbolic link")
    if not path.parent.exists():
        raise ValueError("audit emission parent directory must already exist")
    if not path.parent.is_dir():
        raise ValueError("audit emission parent must be a directory")


def append_observable_digest_audit_entry(
    entry: ObservableDigestFailureAuditEntry,
    *,
    path: Path,
) -> ObservableDigestAuditEmissionReceipt:
    """Append one pre-built audit entry and fsync the local file.

    The caller supplies both the immutable audit entry and the target path.
    This function performs no record enrichment, semantic interpretation,
    deduplication, retry, directory creation, resolver activity, or execution.

    A successful receipt is returned only after the complete JSONL line has
    been written and os.fsync has completed.
    """

    if not isinstance(entry, ObservableDigestFailureAuditEntry):
        raise TypeError("entry must be ObservableDigestFailureAuditEntry")
    if not isinstance(path, Path):
        raise TypeError("path must be pathlib.Path")

    _validate_target(path)

    record_bytes = _canonical_record_bytes(entry)
    record_sha256 = hashlib.sha256(record_bytes).hexdigest()
    line = record_bytes + b"\n"

    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    with _EMISSION_LOCK:
        try:
            fd = os.open(path, flags, 0o600)
        except OSError as exc:
            raise ObservableDigestAuditEmissionError(
                stage="open",
                outcome=_EMISSION_NOT_CONFIRMED,
                path=path,
                record_sha256=record_sha256,
                detail=exc.__class__.__name__,
            ) from exc

        fd_open = True
        bytes_written: int | None = None
        try:
            try:
                bytes_written = os.write(fd, line)
            except OSError as exc:
                raise ObservableDigestAuditEmissionError(
                    stage="write",
                    outcome=_EMISSION_UNKNOWN,
                    path=path,
                    record_sha256=record_sha256,
                    bytes_written=bytes_written,
                    detail=exc.__class__.__name__,
                ) from exc

            if bytes_written != len(line):
                raise ObservableDigestAuditEmissionError(
                    stage="write",
                    outcome=_EMISSION_UNKNOWN,
                    path=path,
                    record_sha256=record_sha256,
                    bytes_written=bytes_written,
                    detail="short_write",
                )

            try:
                os.fsync(fd)
            except OSError as exc:
                raise ObservableDigestAuditEmissionError(
                    stage="fsync",
                    outcome=_DURABILITY_UNKNOWN,
                    path=path,
                    record_sha256=record_sha256,
                    bytes_written=bytes_written,
                    detail=exc.__class__.__name__,
                ) from exc

            try:
                os.close(fd)
                fd_open = False
            except OSError as exc:
                fd_open = False
                raise ObservableDigestAuditEmissionError(
                    stage="close",
                    outcome=_DURABILITY_UNKNOWN,
                    path=path,
                    record_sha256=record_sha256,
                    bytes_written=bytes_written,
                    detail=exc.__class__.__name__,
                ) from exc

        finally:
            if fd_open:
                try:
                    os.close(fd)
                except OSError:
                    pass

    return ObservableDigestAuditEmissionReceipt(
        event_id=entry.event_id,
        schema_version=entry.v1_schema_version,
        path=str(path),
        record_sha256=record_sha256,
        bytes_written=len(line),
    )
