#!/usr/bin/env bash
# ============================================================================
# VERITAS OS — PostgreSQL Restore Script
#
# Restores a VERITAS PostgreSQL database from a pg_dump custom-format backup.
# Supports two modes:
#   --mode=clean   Drop and recreate objects before restore (destructive).
#   --mode=test    Restore into a separate test database for validation.
#
# After restore the script optionally verifies TrustLog chain integrity via
# the VERITAS /v1/trustlog/verify API or standalone CLI.
#
# Usage:
#   scripts/restore_postgres.sh BACKUP_FILE
#   scripts/restore_postgres.sh --mode=test --verify BACKUP_FILE
#   scripts/restore_postgres.sh --mode=clean --verify BACKUP_FILE
#
# Environment variables (libpq standard):
#   PGHOST / PGPORT / PGUSER / PGPASSWORD / PGDATABASE
#   VERITAS_DATABASE_URL   — alternative DSN
#   VERITAS_API_KEY        — for /v1/trustlog/verify (optional)
#   VERITAS_BACKEND_URL    — backend base URL (default: http://localhost:8000)
#   VERITAS_RESTORE_TEST_DB — test database name (default: veritas_restore_test)
#
# Exit codes:
#   0 — restore (and optional verify) succeeded
#   1 — missing prerequisites / bad arguments
#   2 — pg_restore failed
#   3 — TrustLog verification failed
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Colours ───────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[RESTORE]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[RESTORE]${NC} $*"; }
log_error() { echo -e "${RED}[RESTORE]${NC} $*"; }

# ── Defaults ──────────────────────────────────────────────────────────────
MODE="test"              # test | clean
RUN_VERIFY=false
BACKUP_FILE=""
FRESH_TEST_DB=false
TEST_DB="${VERITAS_RESTORE_TEST_DB:-veritas_restore_test}"
BACKEND_URL="${VERITAS_BACKEND_URL:-http://localhost:8000}"
API_KEY="${VERITAS_API_KEY:-}"

# ── Parse arguments ───────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode=*)      MODE="${1#*=}"; shift ;;
        --mode)        MODE="$2"; shift 2 ;;
        --verify)      RUN_VERIFY=true; shift ;;
        --test-db=*)   TEST_DB="${1#*=}"; shift ;;
        --test-db)     TEST_DB="$2"; shift 2 ;;
        --fresh-test-db) FRESH_TEST_DB=true; shift ;;
        --help|-h)
            echo "Usage: $0 [--mode=test|clean] [--verify] [--test-db=NAME] [--fresh-test-db] BACKUP_FILE"
            exit 0
            ;;
        -*)
            log_error "Unknown option: $1"; exit 1 ;;
        *)
            BACKUP_FILE="$1"; shift ;;
    esac
done

if [[ -z "$BACKUP_FILE" ]]; then
    log_error "No backup file specified."
    echo "Usage: $0 [--mode=test|clean] [--verify] BACKUP_FILE"
    exit 1
fi

if [[ ! -f "$BACKUP_FILE" ]]; then
    log_error "Backup file not found: $BACKUP_FILE"
    exit 1
fi

if [[ "$MODE" != "test" && "$MODE" != "clean" ]]; then
    log_error "Invalid mode: $MODE (must be 'test' or 'clean')"
    exit 1
fi
if $FRESH_TEST_DB && [[ "$MODE" != "test" || ! "$TEST_DB" =~ ^[a-z_][a-z0-9_]{0,62}$ ]]; then
    log_error "--fresh-test-db requires test mode and a simple unquoted PostgreSQL test database name."
    exit 1
fi

# ── Prerequisites ─────────────────────────────────────────────────────────
for cmd in pg_restore psql; do
    if ! command -v "$cmd" &>/dev/null; then
        log_error "$cmd is not installed. Install PostgreSQL client tools."
        exit 1
    fi
done

# ── Resolve connection parameters ─────────────────────────────────────────
if [[ -z "${PGHOST:-}" && -n "${VERITAS_DATABASE_URL:-}" ]]; then
    DSN="${VERITAS_DATABASE_URL}"
    export PGUSER="${PGUSER:-$(echo "$DSN" | sed -n 's|.*://\([^:]*\):.*|\1|p')}"
    export PGPASSWORD="${PGPASSWORD:-$(echo "$DSN" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')}"
    export PGHOST="${PGHOST:-$(echo "$DSN" | sed -n 's|.*@\([^:/]*\).*|\1|p')}"
    export PGPORT="${PGPORT:-$(echo "$DSN" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')}"
    export PGDATABASE="${PGDATABASE:-$(echo "$DSN" | sed -n 's|.*/\([^?]*\).*|\1|p')}"
fi

export PGHOST="${PGHOST:-localhost}"
export PGPORT="${PGPORT:-5432}"
export PGUSER="${PGUSER:-veritas}"
export PGDATABASE="${PGDATABASE:-veritas}"

# ── Restore ───────────────────────────────────────────────────────────────
START_TIME=$(date +%s)

# Older or externally produced backups may still contain cluster-local grants.
# Keep the schema, dispatch ordering, and audit data.
RESTORE_LIST=$(mktemp)
trap 'rm -f -- "$RESTORE_LIST"' EXIT
if ! pg_restore --list "$BACKUP_FILE" | awk '
    !($4 == "TABLE" && $5 == "DATA" && $6 == "public" && $7 == "bind_sandbox_revocation_grants")
' > "$RESTORE_LIST"; then
    log_error "Could not read the backup catalog."
    exit 2
fi

if [[ "$MODE" == "test" ]]; then
    log_info "Mode: test — restoring into database '${TEST_DB}'"
    TARGET_DB="$TEST_DB"

    # In fresh mode, CREATE fails without touching an existing database.
    if $FRESH_TEST_DB; then
        psql -X -v ON_ERROR_STOP=1 -v test_database="$TEST_DB" -v database_owner="$PGUSER" -d postgres <<'SQL' || {
CREATE DATABASE :"test_database" OWNER :"database_owner";
SQL
            log_error "Could not create fresh test database '${TEST_DB}'."
            exit 2
        }
    else
        psql -d postgres -c "DROP DATABASE IF EXISTS ${TEST_DB};" 2>/dev/null || true
        psql -d postgres -c "CREATE DATABASE ${TEST_DB} OWNER ${PGUSER};" || {
            log_error "Could not create test database '${TEST_DB}'"
            exit 2
        }
    fi
else
    log_info "Mode: clean — restoring into '${PGDATABASE}' (destructive)"
    TARGET_DB="$PGDATABASE"
fi

log_info "Restoring from: ${BACKUP_FILE}"
log_info "Target database: ${TARGET_DB}"

# Keep Sandbox dispatch fenced even if the archive restore or its verification
# fails. This database-level setting is outside the restored objects.
if ! psql -X -v ON_ERROR_STOP=1 -d "$TARGET_DB" <<'SQL'
BEGIN;
SELECT pg_catalog.pg_advisory_xact_lock(91416, 1);
SELECT pg_catalog.format(
    'ALTER DATABASE %I SET veritas.sandbox_restore_pending = %L',
    pg_catalog.current_database(), 'restoring'
) \gexec
COMMIT;
SQL
then
    log_error "Could not fence Sandbox dispatch before restore."
    exit 2
fi

PG_RESTORE_ARGS=(
    --no-owner
    --no-privileges
    --single-transaction
    --use-list="$RESTORE_LIST"
    --verbose
    -d "$TARGET_DB"
)

if [[ "$MODE" == "clean" ]]; then
    PG_RESTORE_ARGS+=( --clean --if-exists )
fi

if pg_restore "${PG_RESTORE_ARGS[@]}" "${BACKUP_FILE}"; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log_info "Archive restored in ${DURATION}s ✓"
else
    log_error "pg_restore failed (exit code: $?)"
    exit 2
fi

# ── Post-restore integrity checks ────────────────────────────────────────
log_info "Running post-restore integrity checks..."

# --no-privileges can restore this function with default PUBLIC execution.
# The function also checks the login's explicit grant before any write.
if ! psql -X -v ON_ERROR_STOP=1 -d "$TARGET_DB" <<'SQL'
DO $$
BEGIN
    IF pg_catalog.to_regprocedure('public.revoke_sandbox_authorization(text,text)') IS NOT NULL THEN
        REVOKE ALL ON FUNCTION public.revoke_sandbox_authorization(text, text) FROM PUBLIC;
        IF EXISTS (SELECT 1 FROM public.bind_sandbox_revocation_grants) THEN
            RAISE EXCEPTION 'Sandbox operator assignments must be empty after restore';
        END IF;
    END IF;
END
$$;
SQL
then
    log_error "Could not verify Sandbox operator restrictions after restore."
    exit 2
fi

# Check that all three tables exist and have data
for TABLE in trustlog_entries trustlog_chain_state memory_records; do
    ROW_COUNT=$(psql -d "$TARGET_DB" -tAc "SELECT COUNT(*) FROM ${TABLE};" 2>/dev/null || echo "ERROR")
    if [[ "$ROW_COUNT" == "ERROR" ]]; then
        log_error "Table '${TABLE}' not found or query failed"
        exit 2
    fi
    log_info "  ${TABLE}: ${ROW_COUNT} rows"
done

# Verify trustlog_chain_state singleton
CHAIN_STATE=$(psql -d "$TARGET_DB" -tAc "SELECT last_hash, last_id FROM trustlog_chain_state WHERE id = 1;" 2>/dev/null || echo "")
if [[ -n "$CHAIN_STATE" ]]; then
    log_info "  trustlog_chain_state singleton present ✓"
else
    log_warn "  trustlog_chain_state singleton missing (empty database?)"
fi

# ── TrustLog verification ────────────────────────────────────────────────
if $RUN_VERIFY; then
    log_info "Running TrustLog chain verification..."

    # Try API verification first
    if [[ -n "$API_KEY" ]]; then
        VERIFY_RESP=$(curl -sf -w "\n%{http_code}" \
            -H "X-API-Key: ${API_KEY}" \
            "${BACKEND_URL}/v1/trustlog/verify" 2>/dev/null || echo -e "\n000")
        VERIFY_CODE=$(echo "$VERIFY_RESP" | tail -1)

        if [[ "$VERIFY_CODE" == "200" ]]; then
            log_info "TrustLog API verification: PASSED ✓"
        elif [[ "$VERIFY_CODE" == "000" ]]; then
            log_warn "Backend not reachable — skipping API verification"
        else
            log_error "TrustLog API verification failed (HTTP ${VERIFY_CODE})"
            exit 3
        fi
    else
        log_warn "VERITAS_API_KEY not set — skipping API verification"
    fi

    # SQL-level chain verification: check that prev_hash links are consistent
    log_info "Running SQL-level chain hash verification..."
    CHAIN_BREAKS=$(psql -d "$TARGET_DB" -tAc "
        WITH ordered AS (
            SELECT id, hash, prev_hash,
                   LAG(hash) OVER (ORDER BY id) AS expected_prev_hash
            FROM trustlog_entries
        )
        SELECT COUNT(*)
        FROM ordered
        WHERE id > (SELECT MIN(id) FROM trustlog_entries)
          AND prev_hash IS DISTINCT FROM expected_prev_hash;
    " 2>/dev/null || echo "ERROR")

    if [[ "$CHAIN_BREAKS" == "0" ]]; then
        log_info "SQL chain hash verification: PASSED (0 breaks) ✓"
    elif [[ "$CHAIN_BREAKS" == "ERROR" ]]; then
        log_warn "SQL chain hash verification: could not query"
    else
        log_error "SQL chain hash verification: ${CHAIN_BREAKS} break(s) detected"
        exit 3
    fi
fi

# ── Cleanup hint for test mode ────────────────────────────────────────────
if [[ "$MODE" == "test" ]]; then
    log_info "Test database '${TEST_DB}' retained for inspection."
    log_info "To drop: psql -d postgres -c 'DROP DATABASE ${TEST_DB};'"
fi

if ! psql -X -v ON_ERROR_STOP=1 -d "$TARGET_DB" <<'SQL'
BEGIN;
SELECT pg_catalog.pg_advisory_xact_lock(91416, 1);
SELECT pg_catalog.format(
    'ALTER DATABASE %I SET veritas.sandbox_restore_pending = %L',
    pg_catalog.current_database(), 'on'
) \gexec
COMMIT;
SQL
then
    log_error "Could not mark Sandbox dispatch ready for reconciliation."
    exit 2
fi

log_info "Restore complete."
log_info "Sandbox dispatch remains fenced until authoritative ordering is reconciled."
exit 0
