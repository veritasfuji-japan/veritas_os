"""PostgreSQL authority for the configured deployment's emergency halt."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
import os
from uuid import uuid4


class HaltStoreUnavailable(RuntimeError):
    """The authoritative deployment state could not be read or written."""


def enabled() -> bool:
    backend = os.getenv("VERITAS_HALT_BACKEND", "memory").strip().lower()
    if backend not in {"memory", "postgresql"}:
        raise HaltStoreUnavailable("Invalid halt backend")
    return backend == "postgresql"


def deployment() -> str:
    value = os.getenv("VERITAS_DEPLOYMENT_ID", "").strip()
    if not value:
        raise HaltStoreUnavailable("Shared halt requires VERITAS_DEPLOYMENT_ID")
    return value


_active_connection = ContextVar("halt_connection", default=None)


@contextmanager
def transaction():
    """Reuse the request's transaction for nested state checks and transitions."""
    active = _active_connection.get()
    if active is not None:
        yield active
        return
    import psycopg
    from veritas_os.storage.db import build_conninfo
    try:
        conninfo = build_conninfo()
    except (RuntimeError, ValueError) as exc:
        raise HaltStoreUnavailable("Invalid deployment halt database configuration") from exc
    try:
        with psycopg.connect(conninfo) as conn:
            token = _active_connection.set(conn)
            try:
                yield conn
            finally:
                _active_connection.reset(token)
    except psycopg.Error as exc:
        raise HaltStoreUnavailable("Deployment halt storage unavailable") from exc


def status() -> dict:
    with transaction() as conn:
        row = conn.execute(
            "SELECT halt_id, halted_at, operator, reason FROM deployment_halts WHERE deployment_id=%s",
            (deployment(),),
        ).fetchone()
    if row is None:
        raise HaltStoreUnavailable("Deployment halt has not been initialized")
    halt_id, when, actor, reason = row
    return dict(halted=halt_id is not None, halt_id=halt_id, halted_at=when.isoformat() if when else None,
                halted_by=actor, reason=reason)


def halt(*, reason: str, operator: str, startup: bool = False) -> dict:
    """Rearm on startup without replacing an existing emergency stop."""
    with transaction() as conn:
        conn.execute(
            """INSERT INTO deployment_halts (deployment_id, halt_id, halted_at, operator, reason)
               VALUES (%s,%s,clock_timestamp(),%s,%s)
               ON CONFLICT (deployment_id) DO UPDATE SET halt_id=excluded.halt_id,
               halted_at=clock_timestamp(), operator=excluded.operator, reason=excluded.reason,
               pending='{}'::jsonb WHERE NOT %s OR deployment_halts.halt_id IS NULL""",
            (deployment(), uuid4().hex, operator, reason, startup),
        )
        return status()


def resume(*, expected_halt_id: str, operator: str, expires_at: datetime | None) -> dict | None:
    """Lock before checking the database clock, including after a competing writer."""
    with transaction() as conn:
        row = conn.execute("SELECT halt_id FROM deployment_halts WHERE deployment_id=%s FOR UPDATE",
                           (deployment(),)).fetchone()
        if row is None or row[0] != expected_halt_id:
            return None
        result = conn.execute(
            """UPDATE deployment_halts SET halt_id=NULL, halted_at=NULL, operator=NULL,
               reason=NULL, pending='{}'::jsonb WHERE deployment_id=%s
               AND clock_timestamp() < %s RETURNING clock_timestamp()""",
            (deployment(), expires_at),
        ).fetchone()
        if result is None:
            return None
        return dict(resumed=True, was_halted=True, cleared_halt_id=expected_halt_id,
                    resumed_by=operator, resumed_at=result[0].isoformat())
