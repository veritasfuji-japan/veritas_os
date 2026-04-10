#!/usr/bin/env bash
# ============================================================================
# VERITAS OS — Live Provider Validation (Secrets-Required)
#
# Gated validation against real external services. Designed for:
#   - Release gate (manual trigger)
#   - Nightly CI (schedule)
#   - Local pre-release check
#
# This script NEVER runs automatically on contributor PRs.
# All checks gracefully skip when required secrets are absent.
#
# Usage:
#   scripts/live_provider_validation.sh
#   scripts/live_provider_validation.sh --json-report /tmp/live-report.json
#
# Required environment variables (all optional — absent = skip):
#   OPENAI_API_KEY             — OpenAI connectivity check
#   VERITAS_STAGING_BASE_URL   — Staging deployment TLS/health check
#   VERITAS_WEBSEARCH_KEY      — Web search provider check
#
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()    { echo -e "${GREEN}[LIVE-VAL]${NC} $*"; }
log_warn()    { echo -e "${YELLOW}[LIVE-VAL]${NC} $*"; }
log_error()   { echo -e "${RED}[LIVE-VAL]${NC} $*"; }
log_section() { echo -e "${CYAN}[LIVE-VAL]${NC} ── $* ──"; }

JSON_REPORT=""
for arg in "$@"; do
    case "$arg" in
        --json-report=*) JSON_REPORT="${arg#*=}" ;;
        --help|-h) echo "Usage: $0 [--json-report=PATH]"; exit 0 ;;
    esac
done

cd "${REPO_ROOT}"
START_TIME=$(date +%s)

declare -a CHECK_NAMES=()
declare -a CHECK_RESULTS=()
declare -a CHECK_DETAILS=()

record_check() {
    CHECK_NAMES+=("$1")
    CHECK_RESULTS+=("$2")
    CHECK_DETAILS+=("${3:-}")
}

# ── Check 1: OpenAI API Connectivity ──────────────────────────────────────
log_section "Check 1: OpenAI API Connectivity"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    log_warn "OPENAI_API_KEY not set — skipping"
    record_check "openai-connectivity" "SKIP" "OPENAI_API_KEY not set"
else
    # Minimal models list request — cheapest possible API call
    HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer ${OPENAI_API_KEY}" \
        "https://api.openai.com/v1/models" 2>/dev/null || echo "000")
    if [[ "$HTTP_CODE" == "200" ]]; then
        log_info "OpenAI API reachable: HTTP ${HTTP_CODE} ✓"
        record_check "openai-connectivity" "PASS" "HTTP ${HTTP_CODE}"
    elif [[ "$HTTP_CODE" == "401" ]]; then
        log_error "OpenAI API key invalid: HTTP ${HTTP_CODE}"
        record_check "openai-connectivity" "FAIL" "HTTP ${HTTP_CODE} — invalid key"
    else
        log_error "OpenAI API unreachable: HTTP ${HTTP_CODE}"
        record_check "openai-connectivity" "FAIL" "HTTP ${HTTP_CODE}"
    fi
fi

# ── Check 2: Staging Deployment Health ────────────────────────────────────
log_section "Check 2: Staging Deployment"

if [[ -z "${VERITAS_STAGING_BASE_URL:-}" ]]; then
    log_warn "VERITAS_STAGING_BASE_URL not set — skipping"
    record_check "staging-health" "SKIP" "VERITAS_STAGING_BASE_URL not set"
    record_check "staging-tls-cert" "SKIP" "VERITAS_STAGING_BASE_URL not set"
    record_check "staging-security-headers" "SKIP" "VERITAS_STAGING_BASE_URL not set"
else
    STAGING_URL="${VERITAS_STAGING_BASE_URL}"

    # Health check
    STAGING_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "${STAGING_URL}/health" 2>/dev/null || echo "000")
    if [[ "$STAGING_CODE" == "200" ]]; then
        log_info "Staging health: HTTP ${STAGING_CODE} ✓"
        record_check "staging-health" "PASS" "HTTP ${STAGING_CODE}"
    else
        log_error "Staging health: HTTP ${STAGING_CODE}"
        record_check "staging-health" "FAIL" "HTTP ${STAGING_CODE}"
    fi

    # TLS certificate validation
    if [[ "$STAGING_URL" == https://* ]]; then
        CERT_HOST=$(echo "$STAGING_URL" | sed 's|https://||' | cut -d/ -f1 | cut -d: -f1)
        CERT_EXPIRY=$(echo | openssl s_client -servername "$CERT_HOST" -connect "${CERT_HOST}:443" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2 || echo "")
        if [[ -n "$CERT_EXPIRY" ]]; then
            EXPIRY_EPOCH=$(date -d "$CERT_EXPIRY" +%s 2>/dev/null || echo "0")
            NOW_EPOCH=$(date +%s)
            DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))
            if [[ "$DAYS_LEFT" -gt 30 ]]; then
                log_info "TLS certificate expires in ${DAYS_LEFT} days ✓"
                record_check "staging-tls-cert" "PASS" "expires in ${DAYS_LEFT} days"
            elif [[ "$DAYS_LEFT" -gt 0 ]]; then
                log_warn "TLS certificate expires in ${DAYS_LEFT} days (< 30)"
                record_check "staging-tls-cert" "WARN" "expires in ${DAYS_LEFT} days"
            else
                log_error "TLS certificate expired or invalid"
                record_check "staging-tls-cert" "FAIL" "expired or invalid"
            fi
        else
            log_warn "Could not read TLS certificate"
            record_check "staging-tls-cert" "WARN" "certificate unreadable"
        fi

        # Security headers
        HEADERS=$(curl -sf -I "${STAGING_URL}/health" 2>/dev/null || echo "")
        HSTS=$(echo "$HEADERS" | grep -i "^Strict-Transport-Security:" | head -1 || echo "")
        if [[ -n "$HSTS" ]]; then
            log_info "HSTS header present ✓"
            record_check "staging-security-headers" "PASS" "HSTS present"
        else
            log_warn "HSTS header missing"
            record_check "staging-security-headers" "WARN" "HSTS missing"
        fi
    else
        log_warn "Staging URL is not HTTPS — skipping cert/header checks"
        record_check "staging-tls-cert" "SKIP" "URL not HTTPS"
        record_check "staging-security-headers" "SKIP" "URL not HTTPS"
    fi
fi

# ── Check 3: Web Search Provider ──────────────────────────────────────────
log_section "Check 3: Web Search Provider"

if [[ -z "${VERITAS_WEBSEARCH_KEY:-}" ]]; then
    log_warn "VERITAS_WEBSEARCH_KEY not set — skipping"
    record_check "websearch-provider" "SKIP" "VERITAS_WEBSEARCH_KEY not set"
else
    # Run external pytest tests
    if python -m pytest veritas_os/tests/ -m external -v --tb=short -q 2>&1; then
        log_info "Web search external tests passed ✓"
        record_check "websearch-provider" "PASS" "external tests passed"
    else
        log_error "Web search external tests failed"
        record_check "websearch-provider" "FAIL" "external tests failed"
    fi
fi

# ── Check 4: LLM Client Smoke (minimal) ──────────────────────────────────
log_section "Check 4: LLM Client Smoke"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    log_warn "OPENAI_API_KEY not set — skipping LLM smoke"
    record_check "llm-client-smoke" "SKIP" "OPENAI_API_KEY not set"
else
    # Minimal completion to verify the LLM client path works end-to-end
    LLM_RESULT=$(python3 -c "
import os, sys
try:
    from veritas_os.core.llm_client import get_llm_client
    client = get_llm_client()
    resp = client.complete('Say OK', model='gpt-4.1-mini', max_tokens=5)
    print('PASS' if resp and len(resp.strip()) > 0 else 'FAIL')
except Exception as e:
    print(f'FAIL:{e}')
" 2>&1 || echo "FAIL:exception")

    if [[ "$LLM_RESULT" == "PASS" ]]; then
        log_info "LLM client smoke passed ✓"
        record_check "llm-client-smoke" "PASS" "completion successful"
    else
        log_error "LLM client smoke failed: ${LLM_RESULT}"
        record_check "llm-client-smoke" "FAIL" "${LLM_RESULT}"
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────────
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

log_section "Live Provider Validation Report"
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

if [[ $SKIP_COUNT -eq ${#CHECK_NAMES[@]} ]]; then
    log_warn "All checks skipped — no secrets configured"
    log_warn "Set OPENAI_API_KEY / VERITAS_STAGING_BASE_URL / VERITAS_WEBSEARCH_KEY to enable"
fi

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
    'report_type': 'live_provider_validation',
    'generated_at': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
    'duration_seconds': int(sys.argv[4]),
    'secrets_configured': {
        'OPENAI_API_KEY': bool(sys.argv[5]),
        'VERITAS_STAGING_BASE_URL': bool(sys.argv[6]),
        'VERITAS_WEBSEARCH_KEY': bool(sys.argv[7]),
    },
    'summary': {
        'passed': sum(1 for c in checks if c['result'] == 'PASS'),
        'failed': sum(1 for c in checks if c['result'] == 'FAIL'),
        'warnings': sum(1 for c in checks if c['result'] == 'WARN'),
        'skipped': sum(1 for c in checks if c['result'] == 'SKIP'),
        'overall': 'PASS' if not any(c['result'] == 'FAIL' for c in checks) else 'FAIL',
    },
    'checks': checks,
}
with open(sys.argv[8], 'w') as f:
    json.dump(report, f, indent=2)
print(f'JSON report written: {sys.argv[8]}')
" \
    "$(IFS='|'; echo "${CHECK_NAMES[*]}")" \
    "$(IFS='|'; echo "${CHECK_RESULTS[*]}")" \
    "$(IFS='|'; echo "${CHECK_DETAILS[*]}")" \
    "$DURATION" \
    "${OPENAI_API_KEY:+yes}" \
    "${VERITAS_STAGING_BASE_URL:+yes}" \
    "${VERITAS_WEBSEARCH_KEY:+yes}" \
    "$JSON_REPORT"
fi

# ── Exit ──────────────────────────────────────────────────────────────────
if [[ $FAIL_COUNT -gt 0 ]]; then
    exit 1
fi
exit 0
