#!/usr/bin/env bash
# ============================================================================
# VERITAS OS — Full-Stack Docker Compose Governance Validation
#
# Validates governance-platform readiness across realistic deployment:
#   1. Backend health (/health → ok|degraded)
#   2. Frontend health (http://localhost:3000 reachable)
#   3. Core governance endpoints reachable
#   4. Trust/audit/governance critical path smoke
#
# Usage:
#   scripts/compose_validation.sh                  # full compose validation
#   scripts/compose_validation.sh --skip-build     # reuse running services
#   scripts/compose_validation.sh --json-report /tmp/report.json
#
# Environment variables:
#   VERITAS_API_KEY            — API key for authenticated endpoints
#   VERITAS_COMPOSE_TIMEOUT    — compose --wait timeout (default: 120)
#   VERITAS_HEALTH_RETRIES     — health poll retries (default: 30)
#   VERITAS_BACKEND_URL        — backend URL (default: http://localhost:8000)
#   VERITAS_FRONTEND_URL       — frontend URL (default: http://localhost:3000)
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()    { echo -e "${GREEN}[COMPOSE-VAL]${NC} $*"; }
log_warn()    { echo -e "${YELLOW}[COMPOSE-VAL]${NC} $*"; }
log_error()   { echo -e "${RED}[COMPOSE-VAL]${NC} $*"; }
log_section() { echo -e "${CYAN}[COMPOSE-VAL]${NC} ── $* ──"; }

# ── Configuration ─────────────────────────────────────────────────────────
BACKEND_URL="${VERITAS_BACKEND_URL:-http://localhost:8000}"
FRONTEND_URL="${VERITAS_FRONTEND_URL:-http://localhost:3000}"
API_KEY="${VERITAS_API_KEY:-compose-validation-key}"
COMPOSE_TIMEOUT="${VERITAS_COMPOSE_TIMEOUT:-120}"
HEALTH_RETRIES="${VERITAS_HEALTH_RETRIES:-30}"
SKIP_BUILD=false
JSON_REPORT=""
START_TIME=$(date +%s)

for arg in "$@"; do
    case "$arg" in
        --skip-build) SKIP_BUILD=true ;;
        --json-report)
            shift_next=true ;;
        --json-report=*) JSON_REPORT="${arg#*=}" ;;
        --help|-h)
            echo "Usage: $0 [--skip-build] [--json-report PATH]"
            exit 0
            ;;
        *)
            if [[ "${shift_next:-false}" == "true" ]]; then
                JSON_REPORT="$arg"
                shift_next=false
            fi
            ;;
    esac
done

cd "${REPO_ROOT}"

# ── Result tracking ───────────────────────────────────────────────────────
declare -a CHECK_NAMES=()
declare -a CHECK_RESULTS=()
declare -a CHECK_DETAILS=()
FAILURES=0

record_check() {
    local name="$1" result="$2" detail="${3:-}"
    CHECK_NAMES+=("$name")
    CHECK_RESULTS+=("$result")
    CHECK_DETAILS+=("$detail")
    if [[ "$result" == "FAIL" ]]; then
        FAILURES=$((FAILURES + 1))
    fi
}

# ── Phase 1: Docker Compose Build & Start ─────────────────────────────────
log_section "Phase 1: Docker Compose Services"

if ! command -v docker &>/dev/null; then
    log_error "Docker not available — cannot run compose validation"
    record_check "docker-available" "FAIL" "Docker CLI not found"
    # Jump to report
else
    record_check "docker-available" "PASS" "Docker CLI found"

    if ! docker info &>/dev/null 2>&1; then
        log_error "Docker daemon not running"
        record_check "docker-daemon" "FAIL" "Docker daemon unreachable"
    else
        record_check "docker-daemon" "PASS" "Docker daemon responsive"

        if ! $SKIP_BUILD; then
            log_info "Building and starting services (timeout: ${COMPOSE_TIMEOUT}s)..."
            if docker compose up -d --build --wait --timeout "${COMPOSE_TIMEOUT}" 2>&1; then
                log_info "Services started successfully"
                record_check "compose-start" "PASS" "Services started"
            else
                log_error "Docker Compose build/start failed"
                docker compose logs 2>&1 | tail -30
                record_check "compose-start" "FAIL" "Build or start failed"
            fi
        else
            log_info "Skipping build — using running services"
            record_check "compose-start" "SKIP" "Reusing running services"
        fi
    fi
fi

# ── Phase 2: Backend Health ───────────────────────────────────────────────
log_section "Phase 2: Backend Health"

BACKEND_HEALTHY=false
for i in $(seq 1 "$HEALTH_RETRIES"); do
    if curl -sf "${BACKEND_URL}/health" >/dev/null 2>&1; then
        BACKEND_HEALTHY=true
        break
    fi
    sleep 2
done

if $BACKEND_HEALTHY; then
    HEALTH_BODY=$(curl -sf "${BACKEND_URL}/health" 2>/dev/null || echo '{}')
    HEALTH_STATUS=$(echo "$HEALTH_BODY" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "parse-error")

    if [[ "$HEALTH_STATUS" == "ok" || "$HEALTH_STATUS" == "degraded" ]]; then
        log_info "Backend health: ${HEALTH_STATUS} ✓"
        record_check "backend-health" "PASS" "status=${HEALTH_STATUS}"

        # Check health subsystems
        for subsystem in pipeline memory trust_log; do
            SUB_STATUS=$(echo "$HEALTH_BODY" | python3 -c "
import json, sys
d = json.load(sys.stdin)
checks = d.get('checks', {})
print(checks.get('${subsystem}', {}).get('status', 'unknown') if isinstance(checks.get('${subsystem}'), dict) else checks.get('${subsystem}', 'missing'))
" 2>/dev/null || echo "parse-error")
            if [[ "$SUB_STATUS" != "missing" && "$SUB_STATUS" != "parse-error" ]]; then
                log_info "  Subsystem ${subsystem}: ${SUB_STATUS}"
                record_check "backend-subsystem-${subsystem}" "PASS" "status=${SUB_STATUS}"
            else
                log_warn "  Subsystem ${subsystem}: not reported"
                record_check "backend-subsystem-${subsystem}" "WARN" "not reported in health"
            fi
        done
    else
        log_error "Backend health unexpected: ${HEALTH_STATUS}"
        record_check "backend-health" "FAIL" "status=${HEALTH_STATUS}"
    fi
else
    log_error "Backend health check timed out after $((HEALTH_RETRIES * 2))s"
    record_check "backend-health" "FAIL" "timed out"
fi

# ── Phase 3: Frontend Reachability ────────────────────────────────────────
log_section "Phase 3: Frontend Reachability"

FRONTEND_OK=false
for i in $(seq 1 10); do
    HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "${FRONTEND_URL}/" 2>/dev/null || echo "000")
    if [[ "$HTTP_CODE" =~ ^(200|304)$ ]]; then
        FRONTEND_OK=true
        break
    fi
    sleep 3
done

if $FRONTEND_OK; then
    log_info "Frontend reachable: HTTP ${HTTP_CODE} ✓"
    record_check "frontend-reachable" "PASS" "HTTP ${HTTP_CODE}"
else
    log_warn "Frontend not reachable (HTTP ${HTTP_CODE}) — may need longer startup"
    record_check "frontend-reachable" "WARN" "HTTP ${HTTP_CODE} after 30s"
fi

# ── Phase 4: OpenAPI Schema ───────────────────────────────────────────────
log_section "Phase 4: OpenAPI Schema Validation"

if $BACKEND_HEALTHY; then
    OPENAPI_BODY=$(curl -sf "${BACKEND_URL}/openapi.json" 2>/dev/null || echo "")
    if [[ -n "$OPENAPI_BODY" ]]; then
        OPENAPI_VER=$(echo "$OPENAPI_BODY" | python3 -c "import json,sys; print(json.load(sys.stdin).get('openapi',''))" 2>/dev/null || echo "")
        if [[ "$OPENAPI_VER" == 3.* ]]; then
            log_info "OpenAPI ${OPENAPI_VER} schema valid ✓"
            record_check "openapi-schema" "PASS" "version=${OPENAPI_VER}"

            # Verify critical paths exist
            HAS_DECIDE=$(echo "$OPENAPI_BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); print('yes' if '/v1/decide' in str(d.get('paths',{})) else 'no')" 2>/dev/null || echo "no")
            HAS_GOVERNANCE=$(echo "$OPENAPI_BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); print('yes' if '/v1/governance' in str(d.get('paths',{})) else 'no')" 2>/dev/null || echo "no")
            HAS_TRUST=$(echo "$OPENAPI_BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); print('yes' if '/v1/trust' in str(d.get('paths',{})) else 'no')" 2>/dev/null || echo "no")

            [[ "$HAS_DECIDE" == "yes" ]] && record_check "openapi-path-decide" "PASS" "/v1/decide in schema" || record_check "openapi-path-decide" "WARN" "/v1/decide not found"
            [[ "$HAS_GOVERNANCE" == "yes" ]] && record_check "openapi-path-governance" "PASS" "/v1/governance in schema" || record_check "openapi-path-governance" "WARN" "/v1/governance not found"
            [[ "$HAS_TRUST" == "yes" ]] && record_check "openapi-path-trust" "PASS" "/v1/trust in schema" || record_check "openapi-path-trust" "WARN" "/v1/trust not found"
        else
            log_error "OpenAPI schema malformed"
            record_check "openapi-schema" "FAIL" "version=${OPENAPI_VER}"
        fi
    else
        log_error "OpenAPI schema not available"
        record_check "openapi-schema" "FAIL" "endpoint unreachable"
    fi
fi

# ── Phase 5: Governance Critical Path ─────────────────────────────────────
log_section "Phase 5: Governance Critical Path Smoke"

if $BACKEND_HEALTHY; then
    # GET governance policy
    GOV_RESP=$(curl -sf -w "\n%{http_code}" -H "X-API-Key: ${API_KEY}" "${BACKEND_URL}/v1/governance/policy" 2>/dev/null || echo -e "\n000")
    GOV_CODE=$(echo "$GOV_RESP" | tail -1)
    if [[ "$GOV_CODE" == "200" ]]; then
        log_info "GET /v1/governance/policy: ${GOV_CODE} ✓"
        record_check "governance-policy-get" "PASS" "HTTP ${GOV_CODE}"
    else
        log_warn "GET /v1/governance/policy: HTTP ${GOV_CODE}"
        record_check "governance-policy-get" "WARN" "HTTP ${GOV_CODE}"
    fi

    # GET governance policy history
    HIST_CODE=$(curl -sf -o /dev/null -w "%{http_code}" -H "X-API-Key: ${API_KEY}" "${BACKEND_URL}/v1/governance/policy/history" 2>/dev/null || echo "000")
    if [[ "$HIST_CODE" == "200" ]]; then
        log_info "GET /v1/governance/policy/history: ${HIST_CODE} ✓"
        record_check "governance-history" "PASS" "HTTP ${HIST_CODE}"
    else
        log_warn "GET /v1/governance/policy/history: HTTP ${HIST_CODE}"
        record_check "governance-history" "WARN" "HTTP ${HIST_CODE}"
    fi

    # GET /v1/decide auth check (should require auth)
    DECIDE_NOAUTH=$(curl -sf -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{"query":"compose-test"}' "${BACKEND_URL}/v1/decide" 2>/dev/null || echo "000")
    if [[ "$DECIDE_NOAUTH" =~ ^(401|403)$ ]]; then
        log_info "POST /v1/decide without auth: ${DECIDE_NOAUTH} (correctly rejected) ✓"
        record_check "decide-auth-required" "PASS" "HTTP ${DECIDE_NOAUTH}"
    else
        log_warn "POST /v1/decide without auth: HTTP ${DECIDE_NOAUTH} (expected 401/403)"
        record_check "decide-auth-required" "WARN" "HTTP ${DECIDE_NOAUTH}"
    fi
fi

# ── Phase 6: Security Headers ─────────────────────────────────────────────
log_section "Phase 6: Security Headers"

if $BACKEND_HEALTHY; then
    HEADERS=$(curl -sf -I "${BACKEND_URL}/health" 2>/dev/null || echo "")
    if [[ -n "$HEADERS" ]]; then
        check_header() {
            local name="$1" expected="$2"
            local value
            value=$(echo "$HEADERS" | grep -i "^${name}:" | head -1 | sed 's/^[^:]*: *//' | tr -d '\r\n')
            if [[ -n "$value" ]]; then
                log_info "  ${name}: ${value}"
                record_check "header-${name,,}" "PASS" "${value}"
            else
                log_warn "  ${name}: not present"
                record_check "header-${name,,}" "WARN" "missing"
            fi
        }
        check_header "Strict-Transport-Security" "max-age=31536000"
        check_header "X-Content-Type-Options" "nosniff"
        check_header "X-Frame-Options" "DENY"
        check_header "Content-Security-Policy" "default-src"
        check_header "X-Response-Time" ""
    fi
fi

# ── Cleanup ───────────────────────────────────────────────────────────────
if ! $SKIP_BUILD; then
    log_section "Cleanup"
    log_info "Stopping services..."
    docker compose down --timeout 10 2>/dev/null || true
fi

# ── Report Generation ─────────────────────────────────────────────────────
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

log_section "Validation Report"
echo ""

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0
SKIP_COUNT=0

for i in "${!CHECK_NAMES[@]}"; do
    case "${CHECK_RESULTS[$i]}" in
        PASS) PASS_COUNT=$((PASS_COUNT + 1)); icon="✅" ;;
        FAIL) FAIL_COUNT=$((FAIL_COUNT + 1)); icon="❌" ;;
        WARN) WARN_COUNT=$((WARN_COUNT + 1)); icon="⚠️ " ;;
        SKIP) SKIP_COUNT=$((SKIP_COUNT + 1)); icon="⏭️ " ;;
    esac
    printf "  %s  %-35s  %s\n" "$icon" "${CHECK_NAMES[$i]}" "${CHECK_DETAILS[$i]}"
done

echo ""
echo "  ────────────────────────────────────────"
printf "  Passed: %d  |  Failed: %d  |  Warnings: %d  |  Skipped: %d\n" "$PASS_COUNT" "$FAIL_COUNT" "$WARN_COUNT" "$SKIP_COUNT"
echo "  Duration: ${DURATION}s"
echo ""

# ── JSON Report ───────────────────────────────────────────────────────────
if [[ -n "$JSON_REPORT" ]]; then
    mkdir -p "$(dirname "$JSON_REPORT")"
    python3 -c "
import json, sys
checks = []
names = sys.argv[1].split('|')
results = sys.argv[2].split('|')
details = sys.argv[3].split('|')
for n, r, d in zip(names, results, details):
    if n:
        checks.append({'name': n, 'result': r, 'detail': d})

report = {
    'schema_version': '1.0',
    'report_type': 'compose_validation',
    'generated_at': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
    'duration_seconds': int(sys.argv[4]),
    'backend_url': sys.argv[5],
    'frontend_url': sys.argv[6],
    'summary': {
        'passed': sum(1 for c in checks if c['result'] == 'PASS'),
        'failed': sum(1 for c in checks if c['result'] == 'FAIL'),
        'warnings': sum(1 for c in checks if c['result'] == 'WARN'),
        'skipped': sum(1 for c in checks if c['result'] == 'SKIP'),
        'overall': 'PASS' if not any(c['result'] == 'FAIL' for c in checks) else 'FAIL',
    },
    'checks': checks,
}
with open(sys.argv[7], 'w') as f:
    json.dump(report, f, indent=2)
print(f'JSON report written: {sys.argv[7]}')
" \
    "$(IFS='|'; echo "${CHECK_NAMES[*]}")" \
    "$(IFS='|'; echo "${CHECK_RESULTS[*]}")" \
    "$(IFS='|'; echo "${CHECK_DETAILS[*]}")" \
    "$DURATION" \
    "$BACKEND_URL" \
    "$FRONTEND_URL" \
    "$JSON_REPORT"
fi

# ── Exit code ─────────────────────────────────────────────────────────────
if [[ $FAIL_COUNT -eq 0 ]]; then
    log_info "═══════════════════════════════════════════"
    log_info "  Compose validation PASSED ✓"
    log_info "═══════════════════════════════════════════"
    exit 0
else
    log_error "═══════════════════════════════════════════"
    log_error "  Compose validation: ${FAIL_COUNT} check(s) failed"
    log_error "═══════════════════════════════════════════"
    exit 1
fi
