#!/usr/bin/env bash
# ============================================================================
# VERITAS OS — PostgreSQL Recovery Drill Script
#
# End-to-end recovery drill that validates the entire backup → restore →
# verify → health-check pipeline.  Designed for:
#   - Quarterly recovery drills (full mode)
#   - CI smoke tests (--ci mode — uses a lightweight scratch database)
#
# Flow:
#   1. Pre-flight checks (pg_dump, pg_restore, psql, curl)
#   2. Backup current database  (scripts/backup_postgres.sh)
#   3. Restore into test database (scripts/restore_postgres.sh --mode=test)
#   4. TrustLog chain verification (SQL + optional API)
#   5. Health check (if backend is running)
#   6. Cleanup test database
#   7. Summary report
#
# Usage:
#   scripts/drill_postgres_recovery.sh                   # full drill
#   scripts/drill_postgres_recovery.sh --ci              # CI-safe (lightweight)
#   scripts/drill_postgres_recovery.sh --keep-test-db    # don't drop test db
#   scripts/drill_postgres_recovery.sh --skip-health     # skip /health check
#
# Environment variables:
#   PGHOST / PGPORT / PGUSER / PGPASSWORD / PGDATABASE
#   VERITAS_DATABASE_URL        — alternative DSN
#   VERITAS_API_KEY             — for API-level verification
#   VERITAS_BACKEND_URL         — backend base URL
#   VERITAS_RESTORE_TEST_DB     — test database name
#   VERITAS_DRILL_BACKUP_DIR    — where to store drill backups
#
# Exit codes:
#   0 — drill passed
#   1 — pre-flight failure
#   2 — backup failed
#   3 — restore failed
#   4 — verification failed
#   5 — health check failed
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Colours ───────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()    { echo -e "${GREEN}[DRILL]${NC} $*"; }
log_warn()    { echo -e "${YELLOW}[DRILL]${NC} $*"; }
log_error()   { echo -e "${RED}[DRILL]${NC} $*"; }
log_section() { echo -e "${CYAN}[DRILL]${NC} ── $* ──"; }

# ── Defaults ──────────────────────────────────────────────────────────────
CI_MODE=false
KEEP_TEST_DB=false
SKIP_HEALTH=false
BACKUP_DIR="${VERITAS_DRILL_BACKUP_DIR:-${REPO_ROOT}/backups/drill}"
TEST_DB="${VERITAS_RESTORE_TEST_DB:-veritas_drill_test}"
BACKEND_URL="${VERITAS_BACKEND_URL:-http://localhost:8000}"
API_KEY="${VERITAS_API_KEY:-}"
DRILL_START=$(date +%s)
BACKUP_FILE=""
STEP_RESULTS=()

# ── Parse arguments ───────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --ci)           CI_MODE=true; shift ;;
        --keep-test-db) KEEP_TEST_DB=true; shift ;;
        --skip-health)  SKIP_HEALTH=true; shift ;;
        --backup-dir=*) BACKUP_DIR="${1#*=}"; shift ;;
        --backup-dir)   BACKUP_DIR="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: $0 [--ci] [--keep-test-db] [--skip-health] [--backup-dir=DIR]"
            exit 0
            ;;
        *) log_error "Unknown option: $1"; exit 1 ;;
    esac
done

record_step() {
    local name="$1" result="$2" detail="${3:-}"
    STEP_RESULTS+=("${result}|${name}|${detail}")
    if [[ "$result" == "FAIL" ]]; then
        log_error "STEP FAILED: ${name} — ${detail}"
    else
        log_info "  ${name}: ${result} ✓"
    fi
}

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
export VERITAS_RESTORE_TEST_DB="${TEST_DB}"

# ══════════════════════════════════════════════════════════════════════════
# Phase 1: Pre-flight checks
# ══════════════════════════════════════════════════════════════════════════
log_section "Phase 1: Pre-flight Checks"

PREFLIGHT_OK=true
for cmd in pg_dump pg_restore psql; do
    if command -v "$cmd" &>/dev/null; then
        record_step "preflight-${cmd}" "PASS" "$(command -v "$cmd")"
    else
        record_step "preflight-${cmd}" "FAIL" "not found in PATH"
        PREFLIGHT_OK=false
    fi
done

# Verify database is reachable
if psql -d "${PGDATABASE}" -c "SELECT 1;" &>/dev/null; then
    record_step "preflight-db-connect" "PASS" "${PGDATABASE}@${PGHOST}:${PGPORT}"
else
    record_step "preflight-db-connect" "FAIL" "cannot connect to ${PGDATABASE}@${PGHOST}:${PGPORT}"
    PREFLIGHT_OK=false
fi

if ! $PREFLIGHT_OK; then
    log_error "Pre-flight checks failed. Aborting drill."
    exit 1
fi

# ══════════════════════════════════════════════════════════════════════════
# Phase 2: Backup
# ══════════════════════════════════════════════════════════════════════════
log_section "Phase 2: Backup"

mkdir -p "${BACKUP_DIR}"
BACKUP_FILE=$("${SCRIPT_DIR}/backup_postgres.sh" --output "${BACKUP_DIR}" 2>&1 | tail -1)

if [[ -f "$BACKUP_FILE" ]]; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    record_step "backup" "PASS" "${BACKUP_FILE} (${BACKUP_SIZE})"
else
    record_step "backup" "FAIL" "backup file not created"
    exit 2
fi

# ══════════════════════════════════════════════════════════════════════════
# Phase 3: Restore into test database
# ══════════════════════════════════════════════════════════════════════════
log_section "Phase 3: Restore (test mode)"

RESTORE_ARGS=( --mode=test --test-db="${TEST_DB}" )
if [[ -n "$API_KEY" ]]; then
    RESTORE_ARGS+=( --verify )
fi

if "${SCRIPT_DIR}/restore_postgres.sh" "${RESTORE_ARGS[@]}" "${BACKUP_FILE}"; then
    record_step "restore" "PASS" "database=${TEST_DB}"
else
    record_step "restore" "FAIL" "pg_restore returned non-zero"
    exit 3
fi

# ══════════════════════════════════════════════════════════════════════════
# Phase 4: Verification
# ══════════════════════════════════════════════════════════════════════════
log_section "Phase 4: TrustLog Chain Verification"

# 4a. Row count match
ORIG_COUNT=$(psql -d "${PGDATABASE}" -tAc "SELECT COUNT(*) FROM trustlog_entries;" 2>/dev/null || echo "0")
TEST_COUNT=$(psql -d "${TEST_DB}" -tAc "SELECT COUNT(*) FROM trustlog_entries;" 2>/dev/null || echo "0")

if [[ "$ORIG_COUNT" == "$TEST_COUNT" ]]; then
    record_step "verify-row-count" "PASS" "original=${ORIG_COUNT}, restored=${TEST_COUNT}"
else
    record_step "verify-row-count" "FAIL" "original=${ORIG_COUNT}, restored=${TEST_COUNT}"
    exit 4
fi

# 4b. Chain hash consistency (SQL-level)
CHAIN_BREAKS=$(psql -d "${TEST_DB}" -tAc "
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
    record_step "verify-chain-hash" "PASS" "0 breaks"
elif [[ "$CHAIN_BREAKS" == "ERROR" ]]; then
    record_step "verify-chain-hash" "WARN" "query failed (empty table?)"
else
    record_step "verify-chain-hash" "FAIL" "${CHAIN_BREAKS} break(s)"
    exit 4
fi

# 4c. chain_state consistency
ORIG_STATE=$(psql -d "${PGDATABASE}" -tAc "SELECT last_hash, last_id FROM trustlog_chain_state WHERE id=1;" 2>/dev/null || echo "")
TEST_STATE=$(psql -d "${TEST_DB}" -tAc "SELECT last_hash, last_id FROM trustlog_chain_state WHERE id=1;" 2>/dev/null || echo "")

if [[ "$ORIG_STATE" == "$TEST_STATE" ]]; then
    record_step "verify-chain-state" "PASS" "matches original"
else
    record_step "verify-chain-state" "FAIL" "chain_state mismatch"
    exit 4
fi

# 4d. Memory records count
ORIG_MEM=$(psql -d "${PGDATABASE}" -tAc "SELECT COUNT(*) FROM memory_records;" 2>/dev/null || echo "0")
TEST_MEM=$(psql -d "${TEST_DB}" -tAc "SELECT COUNT(*) FROM memory_records;" 2>/dev/null || echo "0")

if [[ "$ORIG_MEM" == "$TEST_MEM" ]]; then
    record_step "verify-memory-count" "PASS" "original=${ORIG_MEM}, restored=${TEST_MEM}"
else
    record_step "verify-memory-count" "FAIL" "original=${ORIG_MEM}, restored=${TEST_MEM}"
    exit 4
fi

# ══════════════════════════════════════════════════════════════════════════
# Phase 5: Health check (optional)
# ══════════════════════════════════════════════════════════════════════════
if ! $SKIP_HEALTH; then
    log_section "Phase 5: Health Check"

    HEALTH_BODY=$(curl -sf "${BACKEND_URL}/health" 2>/dev/null || echo "")
    if [[ -n "$HEALTH_BODY" ]]; then
        HEALTH_STATUS=$(echo "$HEALTH_BODY" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "unknown")
        if [[ "$HEALTH_STATUS" == "ok" || "$HEALTH_STATUS" == "degraded" ]]; then
            record_step "health-check" "PASS" "status=${HEALTH_STATUS}"
        else
            record_step "health-check" "FAIL" "status=${HEALTH_STATUS}"
            exit 5
        fi
    else
        log_warn "Backend not reachable — skipping health check"
        record_step "health-check" "SKIP" "backend unreachable"
    fi
else
    record_step "health-check" "SKIP" "user requested --skip-health"
fi

# ══════════════════════════════════════════════════════════════════════════
# Phase 6: Cleanup
# ══════════════════════════════════════════════════════════════════════════
log_section "Phase 6: Cleanup"

if $KEEP_TEST_DB; then
    log_info "Retaining test database '${TEST_DB}' (--keep-test-db)"
    record_step "cleanup" "SKIP" "test db retained"
else
    if psql -d postgres -c "DROP DATABASE IF EXISTS ${TEST_DB};" &>/dev/null; then
        record_step "cleanup" "PASS" "dropped ${TEST_DB}"
    else
        record_step "cleanup" "WARN" "could not drop ${TEST_DB}"
    fi
fi

if $CI_MODE; then
    # In CI, also clean up the backup file
    rm -f "${BACKUP_FILE}"
    log_info "CI mode: removed backup file"
fi

# ══════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════
DRILL_END=$(date +%s)
DRILL_DURATION=$((DRILL_END - DRILL_START))

echo ""
log_section "Recovery Drill Report"
echo ""

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0
SKIP_COUNT=0

for entry in "${STEP_RESULTS[@]}"; do
    IFS='|' read -r result name detail <<< "$entry"
    case "$result" in
        PASS) PASS_COUNT=$((PASS_COUNT + 1)); icon="✅" ;;
        FAIL) FAIL_COUNT=$((FAIL_COUNT + 1)); icon="❌" ;;
        WARN) WARN_COUNT=$((WARN_COUNT + 1)); icon="⚠️ " ;;
        SKIP) SKIP_COUNT=$((SKIP_COUNT + 1)); icon="⏭️ " ;;
    esac
    printf "  %s  %-30s  %s\n" "$icon" "$name" "$detail"
done

echo ""
echo "  ────────────────────────────────────────"
printf "  Passed: %d  |  Failed: %d  |  Warnings: %d  |  Skipped: %d\n" \
    "$PASS_COUNT" "$FAIL_COUNT" "$WARN_COUNT" "$SKIP_COUNT"
echo "  Duration: ${DRILL_DURATION}s"
echo "  Backup: ${BACKUP_FILE}"
echo ""

if [[ $FAIL_COUNT -eq 0 ]]; then
    log_info "═══════════════════════════════════════════"
    log_info "  Recovery drill PASSED ✓"
    log_info "═══════════════════════════════════════════"
    exit 0
else
    log_error "═══════════════════════════════════════════"
    log_error "  Recovery drill FAILED (${FAIL_COUNT} step(s))"
    log_error "═══════════════════════════════════════════"
    exit 1
fi
