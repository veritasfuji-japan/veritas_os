#!/usr/bin/env bash
# ============================================================================
# VERITAS OS — PostgreSQL Logical Backup Script
#
# Creates a compressed logical backup of the VERITAS PostgreSQL database using
# pg_dump in custom format (-Fc).  The backup includes all three core tables:
#   - memory_records
#   - trustlog_entries
#   - trustlog_chain_state
#
# Usage:
#   scripts/backup_postgres.sh                          # defaults
#   scripts/backup_postgres.sh --output /backups        # custom directory
#   scripts/backup_postgres.sh --tables-only            # data only (no DDL)
#   PGHOST=db.prod PGUSER=veritas scripts/backup_postgres.sh
#
# Environment variables (libpq standard):
#   PGHOST           — PostgreSQL host       (default: localhost)
#   PGPORT           — PostgreSQL port       (default: 5432)
#   PGUSER           — PostgreSQL user       (default: veritas)
#   PGPASSWORD       — PostgreSQL password   (or use .pgpass / PGPASSFILE)
#   PGDATABASE       — Database name         (default: veritas)
#   VERITAS_DATABASE_URL — alternative DSN (parsed if PG* vars are unset)
#
# Exit codes:
#   0 — backup completed successfully
#   1 — missing prerequisites
#   2 — pg_dump failed
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Colours ───────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[BACKUP]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[BACKUP]${NC} $*"; }
log_error() { echo -e "${RED}[BACKUP]${NC} $*"; }

# ── Defaults ──────────────────────────────────────────────────────────────
OUTPUT_DIR="${REPO_ROOT}/backups"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TABLES_ONLY=false
PARALLEL_JOBS=1

# ── Parse arguments ───────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --output)      OUTPUT_DIR="$2"; shift 2 ;;
        --output=*)    OUTPUT_DIR="${1#*=}"; shift ;;
        --tables-only) TABLES_ONLY=true; shift ;;
        --jobs)        PARALLEL_JOBS="$2"; shift 2 ;;
        --jobs=*)      PARALLEL_JOBS="${1#*=}"; shift ;;
        --help|-h)
            echo "Usage: $0 [--output DIR] [--tables-only] [--jobs N]"
            exit 0
            ;;
        *) log_error "Unknown option: $1"; exit 1 ;;
    esac
done

# ── Prerequisites ─────────────────────────────────────────────────────────
if ! command -v pg_dump &>/dev/null; then
    log_error "pg_dump is not installed. Install PostgreSQL client tools."
    exit 1
fi

# ── Resolve connection parameters ─────────────────────────────────────────
# If standard PG* env vars are not set, try to parse VERITAS_DATABASE_URL.
if [[ -z "${PGHOST:-}" && -n "${VERITAS_DATABASE_URL:-}" ]]; then
    # postgresql://user:pass@host:port/dbname
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

# ── Prepare output directory ──────────────────────────────────────────────
mkdir -p "${OUTPUT_DIR}"
BACKUP_FILE="${OUTPUT_DIR}/veritas_${TIMESTAMP}.dump"

log_info "Starting backup of ${PGDATABASE}@${PGHOST}:${PGPORT}"
log_info "Output: ${BACKUP_FILE}"

# ── Build pg_dump command ─────────────────────────────────────────────────
PG_DUMP_ARGS=(
    -Fc                         # Custom format (compressed, pg_restore-compatible)
    --no-owner                  # Omit ownership (portable across envs)
    --no-privileges             # Omit GRANT/REVOKE
    --verbose
)

if $TABLES_ONLY; then
    PG_DUMP_ARGS+=( --data-only )
fi

if [[ "$PARALLEL_JOBS" -gt 1 ]]; then
    PG_DUMP_ARGS+=( --jobs="$PARALLEL_JOBS" )
fi

# ── Execute backup ────────────────────────────────────────────────────────
START_TIME=$(date +%s)

if pg_dump "${PG_DUMP_ARGS[@]}" -f "${BACKUP_FILE}" "${PGDATABASE}"; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)

    log_info "Backup completed in ${DURATION}s"
    log_info "File size: ${BACKUP_SIZE}"
    log_info "File: ${BACKUP_FILE}"

    # ── Verify backup is readable ─────────────────────────────────────────
    if pg_restore --list "${BACKUP_FILE}" >/dev/null 2>&1; then
        log_info "Backup integrity check: OK ✓"
    else
        log_warn "Backup integrity check: pg_restore --list returned non-zero"
    fi

    # ── Print table of contents summary ───────────────────────────────────
    TABLE_COUNT=$(pg_restore --list "${BACKUP_FILE}" 2>/dev/null | grep -c "TABLE DATA" || true)
    log_info "Tables in backup: ${TABLE_COUNT}"

    echo "${BACKUP_FILE}"
    exit 0
else
    log_error "pg_dump failed (exit code: $?)"
    rm -f "${BACKUP_FILE}"
    exit 2
fi
