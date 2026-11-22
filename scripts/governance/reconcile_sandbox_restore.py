"""Reconcile Sandbox ordering from the authoritative PostgreSQL source."""

import argparse
import os
import sys

import psycopg
from psycopg import sql

from veritas_os.policy.native_bind_authorization import NATIVE_AUTHORIZATION_ID_PATTERN
from veritas_os.security.hash import sha256_of_canonical_json
from veritas_os.storage.sandbox_restore import LOCK_SHARED, RESTORE_READY_FOR_REPLAY, TRY_LOCK_EXCLUSIVE

ORDERING = "SELECT authorization_id, resolution FROM public.bind_sandbox_dispatch_order"
NATIVE_CONSUMPTIONS = """
    SELECT authorization_id, consumption_id, consumption_hash, idempotency_key, record::jsonb
    FROM public.bind_authorization_consumptions WHERE authorization_id ~ %s
    ORDER BY authorization_id COLLATE "C"
"""
LOCK_SOURCE = """
    LOCK TABLE public.bind_authorization_consumptions, public.bind_sandbox_dispatch_order IN SHARE MODE
"""
AUDIT = """
    SELECT audit_id, operator_role, operator_name, authorization_id, reason, resolution, recorded_at
    FROM public.bind_sandbox_revocation_audit
"""


class SandboxRestoreError(ValueError):
    """A checked recovery prerequisite was not satisfied."""


def _read_recovery_state(connection: psycopg.Connection) -> dict:
    return {
        "ordering": dict(connection.execute(ORDERING).fetchall()),
        "native_consumptions": connection.execute(NATIVE_CONSUMPTIONS, (NATIVE_AUTHORIZATION_ID_PATTERN,)).fetchall(),
    }


def recovery_digest(source: psycopg.Connection) -> str:
    """Compute the digest to record independently at the recovery cutover."""
    with source.transaction():
        source.execute(LOCK_SOURCE)
        return sha256_of_canonical_json(_read_recovery_state(source))


def reconcile(source: psycopg.Connection, target: psycopg.Connection, expected_digest: str) -> None:
    """Copy committed ordering and release the restore fence in one transaction."""
    with source.transaction(), target.transaction():
        source.execute(LOCK_SHARED)
        # A connection to the same database cannot acquire the conflicting lock.
        acquired = target.execute(TRY_LOCK_EXCLUSIVE).fetchone()
        if acquired != (True,):
            raise SandboxRestoreError("Use a separate target database with no active dispatch transaction.")
        if target.execute(RESTORE_READY_FOR_REPLAY).fetchone() != (True,):
            raise SandboxRestoreError("The target database has not completed a fenced logical restore.")

        source.execute(LOCK_SOURCE)
        target.execute(
            "LOCK TABLE public.bind_authorization_consumptions, public.bind_sandbox_dispatch_order "
            "IN SHARE ROW EXCLUSIVE MODE"
        )
        source_state = _read_recovery_state(source)
        if sha256_of_canonical_json(source_state) != expected_digest:
            raise SandboxRestoreError("The source does not match the independently recorded recovery digest.")
        authoritative = source_state["ordering"]
        restored = dict(target.execute(ORDERING).fetchall())
        if any(authoritative.get(key) != resolution for key, resolution in restored.items()):
            raise SandboxRestoreError("The source does not contain matching decisions for the restored ordering.")

        missing = {key: value for key, value in authoritative.items() if key not in restored}
        if any(value != "REVOKED_BEFORE_DISPATCH" for value in missing.values()):
            raise SandboxRestoreError("The backup lacks committed dispatch history. Restore a newer verified backup.")

        target_consumptions = target.execute(NATIVE_CONSUMPTIONS, (NATIVE_AUTHORIZATION_ID_PATTERN,)).fetchall()
        if source_state["native_consumptions"] != target_consumptions:
            raise SandboxRestoreError("Native v2 consumption records differ. Restore a matching verified backup.")

        source_audit = {row[0]: row for row in source.execute(AUDIT).fetchall()}
        target_audit = {row[0]: row for row in target.execute(AUDIT).fetchall()}
        if any(source_audit.get(key) != row for key, row in target_audit.items()):
            raise SandboxRestoreError("The source does not contain matching restored audit records.")
        with target.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO public.bind_sandbox_dispatch_order (authorization_id, resolution) VALUES (%s, %s)",
                missing.items(),
            )
            cursor.executemany(
                """INSERT INTO public.bind_sandbox_revocation_audit
                   (audit_id, operator_role, operator_name, authorization_id, reason, resolution, recorded_at)
                   OVERRIDING SYSTEM VALUE VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (row for key, row in source_audit.items() if key not in target_audit),
            )
        if source_audit:
            target.execute(
                sql.SQL("ALTER TABLE public.bind_sandbox_revocation_audit ALTER COLUMN audit_id RESTART WITH {}")
                .format(sql.Literal(max(source_audit) + 1))
            )
        target.execute(
            sql.SQL("ALTER DATABASE {} RESET veritas.sandbox_restore_pending").format(
                sql.Identifier(target.info.dbname),
            )
        )


def main() -> int:
    """Use explicitly configured administrator connections."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-recovery-digest", action="store_true", help="print the digest of the authoritative source")
    args = parser.parse_args()
    source_dsn = os.getenv("VERITAS_SANDBOX_RECOVERY_SOURCE_DSN")
    target_dsn = os.getenv("VERITAS_SANDBOX_RECOVERY_TARGET_DSN")
    expected_digest = os.getenv("VERITAS_SANDBOX_RECOVERY_SHA256")
    if not source_dsn or (not args.record_recovery_digest and (not target_dsn or not expected_digest)):
        print("Set the source DSN. Reconciliation also requires the target DSN and recorded digest.", file=sys.stderr)
        return 2
    try:
        if args.record_recovery_digest:
            with psycopg.connect(source_dsn, autocommit=True) as source:
                print(recovery_digest(source))
            return 0
        with psycopg.connect(source_dsn, autocommit=True) as source, psycopg.connect(
            target_dsn, autocommit=True,
        ) as target:
            reconcile(source, target, expected_digest)
    except SandboxRestoreError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (psycopg.Error, ValueError) as exc:
        print(f"Sandbox recovery failed ({type(exc).__name__}).", file=sys.stderr)
        return 1
    print("Sandbox dispatch ordering reconciled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
