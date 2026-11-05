"""J3-06 inert receiver-owned E3-model: SQLite logical admission, NOT network E3.

Research-only: fixture HMAC keys, caller-supplied synthetic time, local STOP,
and SQLite transactions. A successful DB commit does NOT prove that time
sampling and physical commit are atomic. No production import or external I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from collections.abc import Iterator
import hashlib
import hmac
import json
import sqlite3
from pathlib import Path
from typing import Callable, Literal

Status = Literal["DENY_NO_ENTRY", "ENTRY_COMMITTED_ONCE", "UNKNOWN_NO_RETRY"]


@dataclass(frozen=True)
class Operation:
    attempt_id: str
    target: str
    owner_incarnation: str
    body: bytes

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


@dataclass(frozen=True)
class FixtureEvidence:
    issuer: str
    attempt_id: str
    target: str
    owner_incarnation: str
    body_sha256: str
    checked_utc_ms: int
    checked_mono_ms: int
    expires_utc_ms: int
    signature: str


@dataclass(frozen=True)
class FixtureClock:
    utc_ms: int
    mono_ms: int
    uncertainty_ms: int = 0
    trusted_in_fixture: bool = True


@dataclass(frozen=True)
class AdmissionResult:
    status: Status
    reason: str
    sequence: int | None = None


def _signed_payload(e: FixtureEvidence) -> bytes:
    values = {
        "issuer": e.issuer,
        "attempt_id": e.attempt_id,
        "target": e.target,
        "owner_incarnation": e.owner_incarnation,
        "body_sha256": e.body_sha256,
        "checked_utc_ms": e.checked_utc_ms,
        "checked_mono_ms": e.checked_mono_ms,
        "expires_utc_ms": e.expires_utc_ms,
    }
    return json.dumps(values, sort_keys=True, separators=(",", ":")).encode()


def sign_fixture_evidence(
    *, issuer: str, key: bytes, operation: Operation,
    checked_utc_ms: int, checked_mono_ms: int, expires_utc_ms: int,
) -> FixtureEvidence:
    """HMAC is a local test fixture, NOT a production issuer trust root."""
    e = FixtureEvidence(
        issuer, operation.attempt_id, operation.target,
        operation.owner_incarnation, operation.digest,
        checked_utc_ms, checked_mono_ms, expires_utc_ms, "",
    )
    return FixtureEvidence(
        issuer, e.attempt_id, e.target, e.owner_incarnation, e.body_sha256,
        e.checked_utc_ms, e.checked_mono_ms, e.expires_utc_ms,
        hmac.new(key, _signed_payload(e), hashlib.sha256).hexdigest(),
    )


class InertReceiverAdmission:
    """One SQLite file, one local STOP domain; no network and no external effect.

    A pre-registered attempt is claimed (IN_PROGRESS) and durably committed
    BEFORE the final admission transaction. Crash after claim leaves UNKNOWN
    and never permits another admission attempt.
    """

    def __init__(self, path: str | Path, *, fixture_keys: dict[str, bytes]):
        if set(fixture_keys) != {"Sanction", "VERITAS"}:
            raise ValueError("exactly two fixture issuers required")
        self.path = str(path)
        self._keys = dict(fixture_keys)
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS gate_state (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                stopped INTEGER NOT NULL, stop_epoch INTEGER NOT NULL
            )""")
            db.execute("""INSERT OR IGNORE INTO gate_state
                (singleton, stopped, stop_epoch) VALUES (1,0,0)""")
            db.execute("""CREATE TABLE IF NOT EXISTS attempts (
                attempt_id TEXT PRIMARY KEY, target TEXT NOT NULL,
                owner TEXT NOT NULL, digest TEXT NOT NULL,
                state TEXT NOT NULL, reason TEXT NOT NULL,
                stop_epoch INTEGER, admitted_utc_ms INTEGER
            )""")

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        try:
            db.execute("PRAGMA busy_timeout=15000")
            db.execute("PRAGMA synchronous=FULL")
            yield db
        finally:
            db.close()

    def register(self, op: Operation) -> bool:
        if not all(type(v) is str and v for v in (
            op.attempt_id, op.target, op.owner_incarnation
        )) or type(op.body) is not bytes or not op.body:
            raise ValueError("invalid frozen operation")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            cur = db.execute("""INSERT OR IGNORE INTO attempts
                (attempt_id,target,owner,digest,state,reason)
                VALUES (?,?,?,?,'PENDING','REGISTERED')""", (
                op.attempt_id, op.target, op.owner_incarnation, op.digest
            ))
            db.commit()
            return cur.rowcount == 1

    def stop(self) -> int:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""UPDATE gate_state SET stopped=1,
                stop_epoch=stop_epoch+1 WHERE singleton=1""")
            epoch = db.execute(
                "SELECT stop_epoch FROM gate_state WHERE singleton=1"
            ).fetchone()[0]
            db.commit()
            return epoch

    def snapshot(self, attempt_id: str) -> tuple[str, str, int | None] | None:
        with self._db() as db:
            row = db.execute(
                "SELECT state,reason,stop_epoch FROM attempts WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            return tuple(row) if row else None

    def _valid(
        self, op: Operation, evidence: tuple[FixtureEvidence, ...],
        clock: FixtureClock,
    ) -> str | None:
        if (
            type(clock) is not FixtureClock
            or clock.trusted_in_fixture is not True
            or any(type(v) is not int for v in (
                clock.utc_ms, clock.mono_ms, clock.uncertainty_ms
            ))
            or clock.uncertainty_ms < 0
        ):
            return "CLOCK_UNTRUSTED"
        if (
            type(evidence) is not tuple or len(evidence) != 2
            or any(type(e) is not FixtureEvidence for e in evidence)
            or {e.issuer for e in evidence} != set(self._keys)
        ):
            return "ISSUER_SET_INVALID"
        lower = clock.utc_ms - clock.uncertainty_ms
        upper = clock.utc_ms + clock.uncertainty_ms
        for e in evidence:
            expected = hmac.new(
                self._keys[e.issuer], _signed_payload(e), hashlib.sha256
            ).hexdigest()
            if type(e.signature) is not str or not hmac.compare_digest(expected, e.signature):
                return "SIGNATURE_INVALID"
            if (
                e.attempt_id != op.attempt_id
                or e.target != op.target
                or e.owner_incarnation != op.owner_incarnation
                or e.body_sha256 != op.digest
            ):
                return "BINDING_INVALID"
            if not (
                0 <= lower - e.checked_utc_ms
                and upper - e.checked_utc_ms <= 2000
                and 0 <= clock.mono_ms - e.checked_mono_ms <= 2000
                and upper < e.expires_utc_ms
            ):
                return "TIME_OR_EXPIRY_INVALID"
        return None

    def attempt_admit(
        self, op: Operation, evidence: tuple[FixtureEvidence, ...],
        clock: FixtureClock, *,
        lose_receipt: bool = False,
        before_commit: Callable[[], None] | None = None,
    ) -> AdmissionResult:
        """Commit E3_MODEL, never a real receiver admission or external effect.

        before_commit is a TEST-ONLY hook exposing a clock-sample/commit gap.
        It is deliberately not an enforcement primitive.
        """
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT target,owner,digest,state
                FROM attempts WHERE attempt_id=?""", (op.attempt_id,)).fetchone()
            if row is None:
                db.commit()
                return AdmissionResult("DENY_NO_ENTRY", "NOT_REGISTERED")
            if row[3] != "PENDING":
                db.commit()
                return AdmissionResult("DENY_NO_ENTRY", "ALREADY_CLAIMED")
            db.execute("""UPDATE attempts SET state='IN_PROGRESS',
                reason='CLAIMED_NO_RETRY' WHERE attempt_id=?""", (op.attempt_id,))
            db.commit()

        # An unexpected process crash from this point leaves a durable
        # IN_PROGRESS row. The same attempt cannot be re-claimed after restart.
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            state = db.execute(
                "SELECT state FROM attempts WHERE attempt_id=?", (op.attempt_id,)
            ).fetchone()
            if state != ("IN_PROGRESS",):
                db.commit()
                return AdmissionResult("DENY_NO_ENTRY", "CLAIM_STATE_CHANGED")
            gate = db.execute(
                "SELECT stopped,stop_epoch FROM gate_state WHERE singleton=1"
            ).fetchone()
            if row[:3] != (op.target, op.owner_incarnation, op.digest):
                reason = "REGISTERED_BINDING_MISMATCH"
            elif gate[0]:
                reason = "STOP_EFFECTIVE"
            else:
                reason = self._valid(op, evidence, clock)
            if reason is not None:
                db.execute("""UPDATE attempts SET state='DENIED',reason=?,
                    stop_epoch=? WHERE attempt_id=?""",
                    (reason, gate[1], op.attempt_id))
                db.commit()
                return AdmissionResult("DENY_NO_ENTRY", reason)
            if before_commit is not None:
                try:
                    before_commit()
                except Exception:
                    db.execute("""UPDATE attempts SET state='UNKNOWN',
                        reason='HOOK_INTERRUPTED' WHERE attempt_id=?""",
                        (op.attempt_id,))
                    db.commit()
                    return AdmissionResult("UNKNOWN_NO_RETRY", "HOOK_INTERRUPTED")
            # Logical DB admission is serialized with STOP in this DB, but
            # physical time can advance after the above sample. NOT Strict RC1.
            db.execute("""UPDATE attempts SET state='ADMITTED',
                reason='E3_MODEL_ONLY',stop_epoch=?,admitted_utc_ms=?
                WHERE attempt_id=?""", (gate[1], clock.utc_ms, op.attempt_id))
            sequence = db.execute(
                "SELECT rowid FROM attempts WHERE attempt_id=?", (op.attempt_id,)
            ).fetchone()[0]
            db.commit()
            if lose_receipt:
                return AdmissionResult("UNKNOWN_NO_RETRY", "RECEIPT_LOST")
            return AdmissionResult("ENTRY_COMMITTED_ONCE", "E3_MODEL_ONLY", sequence)
