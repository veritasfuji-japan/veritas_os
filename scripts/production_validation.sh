#!/usr/bin/env bash
# ============================================================================
# VERITAS OS — Production Validation Script
#
# Runs production-like validation locally or in CI:
#   1. Python production-like tests (pytest -m "production or smoke")
#   2. Docker Compose smoke test (build + health check)
#
# Usage:
#   scripts/production_validation.sh              # full validation
#   scripts/production_validation.sh --tests-only # pytest only (no Docker)
#   scripts/production_validation.sh --docker-only # Docker smoke only
#
# Environment variables:
#   VERITAS_WEBSEARCH_KEY  — set to enable external web search tests
#   VERITAS_SKIP_DOCKER    — set to 1 to skip Docker validation
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info()  { echo -e "${GREEN}[VERITAS]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[VERITAS]${NC} $*"; }
log_error() { echo -e "${RED}[VERITAS]${NC} $*"; }

# Parse arguments
RUN_TESTS=true
RUN_DOCKER=true

for arg in "$@"; do
    case "$arg" in
        --tests-only)  RUN_DOCKER=false ;;
        --docker-only) RUN_TESTS=false ;;
        --help|-h)
            echo "Usage: $0 [--tests-only|--docker-only]"
            exit 0
            ;;
    esac
done

# Skip Docker if explicitly requested
if [[ "${VERITAS_SKIP_DOCKER:-0}" == "1" ]]; then
    RUN_DOCKER=false
fi

cd "${REPO_ROOT}"
FAILURES=0

# ── Phase 0: Security configuration guards ────────────────────────────────

log_info "Phase 0: Running security configuration guards..."
if python scripts/security/check_query_api_key_compat_flags.py; then
    log_info "Phase 0: Query API key compatibility flag guard PASSED ✓"
else
    log_error "Phase 0: Query API key compatibility flag guard FAILED ✗"
    FAILURES=$((FAILURES + 1))
fi

# ── Phase 1: Python production-like tests ─────────────────────────────────

if $RUN_TESTS; then
    log_info "Phase 1: Running production-like Python tests..."

    MARKER="production or smoke"

    # Include external tests if API key is available
    if [[ -n "${VERITAS_WEBSEARCH_KEY:-}" ]]; then
        MARKER="production or smoke or external"
        log_info "  VERITAS_WEBSEARCH_KEY detected — including external tests"
    fi

    if python -m pytest veritas_os/tests/ \
        -m "${MARKER}" \
        -v \
        --tb=short \
        --durations=10; then
        log_info "Phase 1: Python production tests PASSED ✓"
    else
        log_error "Phase 1: Python production tests FAILED ✗"
        FAILURES=$((FAILURES + 1))
    fi
fi

# ── Phase 2: Docker Compose smoke test ────────────────────────────────────

if $RUN_DOCKER; then
    log_info "Phase 2: Docker Compose smoke test..."

    if ! command -v docker &>/dev/null; then
        log_warn "Phase 2: Docker not available — skipping"
    elif ! docker info &>/dev/null; then
        log_warn "Phase 2: Docker daemon not running — skipping"
    else
        # Build and start services
        log_info "  Building and starting services..."
        if docker compose up -d --build --wait --timeout 120; then
            log_info "  Services started successfully"

            # Wait for backend health
            log_info "  Checking backend health..."
            HEALTH_OK=false
            for i in $(seq 1 30); do
                if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
                    HEALTH_OK=true
                    break
                fi
                sleep 2
            done

            if $HEALTH_OK; then
                # Validate health response
                HEALTH=$(curl -sf http://localhost:8000/health)
                STATUS=$(echo "$HEALTH" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || true)

                if [[ "$STATUS" == "ok" || "$STATUS" == "degraded" ]]; then
                    log_info "  Backend health: ${STATUS} ✓"

                    # Check OpenAPI
                    if curl -sf http://localhost:8000/openapi.json >/dev/null 2>&1; then
                        log_info "  OpenAPI schema available ✓"
                    else
                        log_warn "  OpenAPI schema not available"
                    fi
                else
                    log_error "  Backend health unexpected: ${STATUS}"
                    FAILURES=$((FAILURES + 1))
                fi
            else
                log_error "  Backend health check timed out"
                docker compose logs backend 2>&1 | tail -20
                FAILURES=$((FAILURES + 1))
            fi

            # Cleanup
            log_info "  Stopping services..."
            docker compose down --timeout 10
        else
            log_error "  Docker Compose build/start failed"
            docker compose logs 2>&1 | tail -30
            docker compose down --timeout 10 2>/dev/null || true
            FAILURES=$((FAILURES + 1))
        fi

        log_info "Phase 2: Docker smoke test completed"
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────────

echo ""
if [[ $FAILURES -eq 0 ]]; then
    log_info "═══════════════════════════════════════════"
    log_info "  Production validation PASSED ✓"
    log_info "═══════════════════════════════════════════"
    exit 0
else
    log_error "═══════════════════════════════════════════"
    log_error "  Production validation: ${FAILURES} phase(s) failed"
    log_error "═══════════════════════════════════════════"
    exit 1
fi
