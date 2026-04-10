# VERITAS OS — Operational Readiness Runbook

## Purpose

This runbook describes how to validate VERITAS OS deployment readiness across
realistic runtime and deployment conditions. It covers what is proven, what is
simulated, and what requires environment-specific confirmation.

## Quick Reference

| Command | What it does | When to use |
|---------|-------------|-------------|
| `make test-smoke` | 16 fast governance smoke tests | Every PR (automatic) |
| `make test-production` | 65+ production-like tests | Pre-release, Tier 2 |
| `make validate` | Pytest + Docker Compose smoke | Full local validation |
| `make validate-compose` | Docker Compose governance smoke | After Docker changes |
| `make validate-compose-report` | Compose validation + JSON report | Release gate |
| `make validate-live` | Live provider checks (secrets-required) | Nightly/manual |
| `make validate-live-report` | Live provider + JSON report | Release certification |
| `make validate-staged-report` | Full staged readiness report | Release certification |
| `make quality-checks` | Architecture + security scripts | Every PR (automatic) |

## Validation Tiers

### Tier 1 — Every PR (Blocking)

**Trigger**: Automatic on every PR / push to `main`
**Workflow**: `.github/workflows/main.yml`
**Duration**: ~5 min

What is proven:
- Ruff linting, Bandit static analysis
- Architecture boundary enforcement (responsibility, complexity)
- Security invariant scripts (pickle, bare-except, shell, eval, httpx)
- 16 governance smoke tests (`pytest -m smoke`)
- Full unit test suite (5800+ tests, 85% coverage gate)
- Slow tests (`pytest -m slow`)
- Frontend quality gate (ESLint, Vitest, Playwright E2E)

### Tier 2 — Release Gate (Blocking)

**Trigger**: Automatic on `v*` tag push, manual dispatch
**Workflow**: `.github/workflows/release-gate.yml`
**Duration**: ~20 min

What is proven:
- All Tier 1 checks (re-run)
- Production-like pytest suite (`pytest -m "production or smoke"`)
- Docker Compose full-stack health check
- Governance readiness report (13+ checks)
- TLS header validation
- Concurrent burst load (32 req / 8 workers)
- Governance endpoint latency budget (p95 < 500ms)

### Tier 3 — Production Validation (Advisory)

**Trigger**: Weekly (Sunday 04:00 UTC), manual dispatch
**Workflow**: `.github/workflows/production-validation.yml`
**Duration**: ~15-30 min

What is proven:
- All production tests
- TLS-specific validation suite
- Load burst validation with percentile summaries
- Docker Compose governance endpoint reachability
- External provider validation (when secrets configured)

## Running Validation Locally

### Smoke Tests (Fast, No Dependencies)

```bash
# Run the 16 fast governance smoke tests
make test-smoke

# Expected output: 16 tests pass in < 5s
```

### Production Tests (Medium, No External Services)

```bash
# Install test dependencies
pip install pytest httpx pydantic fastapi numpy cryptography

# Run all production-like tests
make test-production

# Expected output: 65+ tests pass in < 15s
```

### Docker Compose Validation

```bash
# Full-stack validation (requires Docker)
make validate-compose

# With JSON report artifact
make validate-compose-report
# Report: release-artifacts/compose-validation-report.json
```

**Expected checks** (when Docker is available):
- ✅ Docker available + daemon running
- ✅ Compose services start successfully
- ✅ Backend health: ok/degraded
- ✅ Backend subsystems: pipeline, memory, trust_log
- ✅ Frontend reachable (HTTP 200)
- ✅ OpenAPI schema valid (3.x)
- ✅ Governance policy endpoint reachable
- ✅ Governance history endpoint reachable
- ✅ Auth enforcement (/v1/decide requires API key)
- ✅ Security headers present (HSTS, X-Content-Type-Options, X-Frame-Options)

### Live Provider Validation (Secrets Required)

```bash
# Set required secrets
export OPENAI_API_KEY=sk-...
export VERITAS_STAGING_BASE_URL=https://staging.example.com
export VERITAS_WEBSEARCH_KEY=...

# Run live validation
make validate-live

# With JSON report
make validate-live-report
```

**Checks performed** (each skips gracefully when secret is absent):
- OpenAI API connectivity (cheapest possible: `/v1/models` list)
- LLM client end-to-end completion (gpt-4.1-mini, max_tokens=5)
- Staging health endpoint
- Staging TLS certificate expiry (> 30 days)
- Staging security headers (HSTS)
- Web search external test suite

### Staged Readiness Report (Full Certification)

```bash
# Generate the comprehensive readiness report
make validate-staged-report

# Or with compose + live reports included:
make validate-compose-report
make validate-live-report
python scripts/generate_staged_readiness_report.py \
  --ref $(git describe --tags --always) \
  --sha $(git rev-parse HEAD) \
  --compose-report release-artifacts/compose-validation-report.json \
  --live-report release-artifacts/live-provider-report.json \
  --output release-artifacts/staged-readiness-report.json \
  --text-output release-artifacts/staged-readiness-report.txt
```

## Report Artifacts

### Governance Readiness Report (v1.0)

Generated by `scripts/generate_release_readiness_report.py`.

```json
{
  "schema_version": "1.0",
  "report_type": "governance_readiness",
  "summary": {
    "governance_ready": true,
    "total_checks": 13,
    "passed": 13,
    "blocking_failures": 0
  }
}
```

### Staged Readiness Report (v2.0)

Generated by `scripts/generate_staged_readiness_report.py`.

```json
{
  "schema_version": "2.0",
  "report_type": "staged_operational_readiness",
  "overall_readiness": {
    "governance_ready": true,
    "compose_validated": true,
    "live_provider_ok": true,
    "deployment_ready": true
  },
  "governance": { "total_checks": 13, "passed": 13 },
  "compose_validation": { "summary": { "overall": "PASS" } },
  "live_provider_validation": { "summary": { "overall": "PASS" } },
  "coverage_matrix": { ... }
}
```

### Compose Validation Report

Generated by `scripts/compose_validation.sh --json-report`.

```json
{
  "schema_version": "1.0",
  "report_type": "compose_validation",
  "summary": { "passed": 15, "failed": 0, "overall": "PASS" },
  "checks": [
    { "name": "backend-health", "result": "PASS", "detail": "status=ok" },
    { "name": "governance-policy-get", "result": "PASS", "detail": "HTTP 200" }
  ]
}
```

### Live Provider Report

Generated by `scripts/live_provider_validation.sh --json-report=`.

```json
{
  "schema_version": "1.0",
  "report_type": "live_provider_validation",
  "secrets_configured": {
    "OPENAI_API_KEY": true,
    "VERITAS_STAGING_BASE_URL": false,
    "VERITAS_WEBSEARCH_KEY": false
  },
  "summary": { "passed": 2, "skipped": 4, "overall": "PASS" }
}
```

## What Is Proven vs Simulated vs Environment-Specific

### Proven in CI (Every PR)

| Area | Proof Method |
|------|-------------|
| Security invariants | 7 static analysis scripts, blocking |
| Architecture boundaries | Responsibility boundary + complexity checks |
| Unit/integration correctness | 5800+ tests, 85% coverage |
| API contract compliance | OpenAPI schema + smoke tests |
| Docker compose topology | YAML parse + healthcheck validation |
| Governance CRUD + audit trail | HTTP API E2E with disk verification |
| TrustLog chain integrity | Hash chain + tamper detection |
| Encryption fail-closed | Missing-key raises, wrong-key fails |
| SSRF/XSS prevention | Web search security tests |
| TLS header posture | HSTS, CSP, X-Frame, X-Content-Type |
| Concurrent load baseline | 32 req burst with p95 assertion |

### Proven with Docker Compose

| Area | Proof Method |
|------|-------------|
| Container health lifecycle | Docker healthcheck + poll |
| Frontend reachability | HTTP 200 from container |
| Backend-frontend dependency order | `depends_on: service_healthy` |
| Governance endpoints via network | HTTP to containerized backend |
| Security headers from container | Response header inspection |
| Auth enforcement in container | 401/403 without API key |

### Proven with Secrets (Release/Nightly)

| Area | Proof Method |
|------|-------------|
| OpenAI API connectivity | /v1/models HTTP 200 |
| LLM client end-to-end | Minimal completion call |
| Staging TLS cert validity | Certificate expiry > 30 days |
| Staging security headers | HSTS presence check |
| Web search provider | External pytest suite |

### Requires Environment-Specific Confirmation

| Area | Why | Recommendation |
|------|-----|----------------|
| Kubernetes Helm chart | K8s not yet supported | Add when K8s support ships |
| Production TLS chain (OCSP/CRL) | Requires real cert infrastructure | Validate during deployment |
| Multi-region failover | Single-node architecture | N/A until clustering added |
| Long-duration load/stress | k6/locust not yet integrated | Run before high-traffic launches |
| Database migration | File-based storage | Validate when DB backend added |
| Monitoring integration | Env-specific (Datadog, etc.) | Validate per deployment |
| DNS/CDN configuration | Deployment-specific | Check during infrastructure setup |

## Troubleshooting

### Docker Compose validation fails

```bash
# Check if Docker is running
docker info

# Check if ports are available
lsof -i :8000
lsof -i :3000

# Manual compose debug
docker compose up --build
docker compose logs backend
```

### Live validation all skipped

All checks skip when no secrets are set. This is by design for contributor PRs.

```bash
# Verify secrets are exported
echo "OPENAI_API_KEY: ${OPENAI_API_KEY:+(set)}"
echo "VERITAS_STAGING_BASE_URL: ${VERITAS_STAGING_BASE_URL:+(set)}"
echo "VERITAS_WEBSEARCH_KEY: ${VERITAS_WEBSEARCH_KEY:+(set)}"
```

### Latency budget failures

The load tests enforce p95 latency budgets:
- `/health`: p95 < 200ms (TestClient), p95 < 500ms (burst)
- `/v1/governance/policy`: p95 < 500ms (single), p95 < 1000ms (burst)
- Staging `/health`: p95 < 800ms (HTTPS burst)

If budgets fail in CI, check:
1. CI runner resource contention
2. Application startup overhead (first request warmup)
3. Database/file I/O bottleneck

## Security Notes

- Live provider validation scripts never log API keys or secrets
- All secret-gated checks skip gracefully when secrets are absent
- Compose validation uses a test-only API key (not production)
- JSON reports contain no secrets or PII
- The `VERITAS_API_KEY` in compose validation is for test isolation only
