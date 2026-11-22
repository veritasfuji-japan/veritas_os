"""Database-local dispatch fence for the supported logical restore workflow."""

# Restore, replay, and the worker use this transaction-scoped lock in the
# target database. The database setting is read from the catalog so connection
# options and session-level settings cannot change the recovery status.
LOCK_SHARED = "SELECT pg_catalog.pg_advisory_xact_lock_shared(91416, 1)"
TRY_LOCK_EXCLUSIVE = "SELECT pg_catalog.pg_try_advisory_xact_lock(91416, 1)"
_RECOVERY_SETTING_EXISTS = """
    SELECT EXISTS (
        SELECT 1 FROM pg_catalog.pg_db_role_setting AS settings
        JOIN pg_catalog.pg_database AS database ON database.oid = settings.setdatabase
        WHERE database.datname = pg_catalog.current_database()
          AND settings.setrole = 0
          AND {condition}
    )
"""
RECOVERY_PENDING = _RECOVERY_SETTING_EXISTS.format(
    condition="settings.setconfig && ARRAY['veritas.sandbox_restore_pending=restoring', "
    "'veritas.sandbox_restore_pending=on']",
)
RESTORE_READY_FOR_REPLAY = _RECOVERY_SETTING_EXISTS.format(
    condition="'veritas.sandbox_restore_pending=on' = ANY(settings.setconfig)",
)
