# VERITAS OS — Production Validation Strategy

## Overview

This document describes the **production-like validation** strategy for VERITAS OS.
It complements the existing unit/integration test suite (5300+ tests, 87% coverage)
with production-realistic verification that exercises external dependencies,
deployment topology, and fail-closed security controls.

## Test Profiles

| Profile | Marker | CI Trigger | Description |
|---------|--------|------------|-------------|
| **Unit** | *(default)* | Every push/PR | Fast, isolated, mocked dependencies |
| **Slow** | `@pytest.mark.slow` | Every push/PR (parallel job) | Heavier computation, larger datasets |
| **Production** | `@pytest.mark.production` | `workflow_dispatch` / opt-in | Production-like flows with real subsystems |
| **Smoke** | `@pytest.mark.smoke` | `workflow_dispatch` / opt-in | Lightweight deployment verification |
| **External** | `@pytest.mark.external` | `workflow_dispatch` + secrets | Tests requiring live network/API keys |

## Running Production Validation

### Local Execution

```bash
# Run all production-like tests (no external deps needed)
make test-production

# Run only smoke tests
pytest -m smoke veritas_os/tests/

# Run production tests with verbose output
pytest -m production veritas_os/tests/ -v --tb=long

# Run external tests (requires API keys)
VERITAS_WEBSEARCH_KEY=<key> pytest -m external veritas_os/tests/
```

### CI Execution

Production validation runs as a **separate GitHub Actions workflow** (`production-validation.yml`):

- **Trigger**: `workflow_dispatch` (manual) or schedule (weekly)
- **Not in default CI**: Avoids flaky external dependency failures blocking PRs
- **Secrets**: Optional `VERITAS_WEBSEARCH_KEY` for external tests

### Docker Compose Validation

```bash
# Full stack validation script
scripts/production_validation.sh

# Or manually:
docker compose up -d --build
curl -sf http://localhost:8000/health | python3 -m json.tool
docker compose down
```

## Verification Matrix

### 1. FastAPI + Frontend + Docker Compose Smoke (`test_production_smoke.py`)

| What | How | Production Gap Closed |
|------|-----|----------------------|
| `/health` response contract | TestClient | Health endpoint returns documented shape |
| `/v1/health` alias | TestClient | Versioned endpoint works |
| `X-Response-Time` header | TestClient | Observability headers present |
| Health subsystem checks | TestClient | Pipeline, memory, trust_log reported |
| OpenAPI schema validity | TestClient | `/openapi.json` well-formed |
| `/docs` availability | TestClient | Swagger UI accessible |
| `/v1/decide` contract | TestClient | Auth required, structured responses |
| Governance policy GET | TestClient | Policy readable via API |
| Governance history | TestClient | Audit trail accessible |
| `docker-compose.yml` syntax | YAML parse | Services defined correctly |
| Backend healthcheck | YAML parse | Healthcheck configured |
| Frontend depends_on | YAML parse | Service dependency order |
| Dockerfile validity | File check | Multi-stage build with healthcheck |

### 2. TrustLog Write/Read/Verify (`test_production_trustlog.py`)

| What | How | Production Gap Closed |
|------|-----|----------------------|
| Single append + read | Real TrustLog (temp dir) | Full write path exercised |
| Chain integrity (10 entries) | `verify_trust_log()` | Hash chain verified |
| Tamper detection | Corrupt JSONL + verify | Integrity violation detected |
| Encrypted round-trip | Encrypt + decrypt | At-rest encryption works |
| Stats increment | `get_trust_log_stats()` | Monitoring counters correct |
| Concurrent appends | 5 threads × 4 writes | Thread-safety verified |
| Signed decision append | `append_signed_decision()` | Ed25519 signing works |
| Signed chain verify | `verify_trustlog_chain()` | Multi-entry chain valid |
| Signed export | `export_signed_trustlog()` | All entries exportable |
| Signed tamper detection | Corrupt + verify | Signature mismatch detected |

### 3. Replay Artifact Generation (`test_production_replay.py`)

| What | How | Production Gap Closed |
|------|-----|----------------------|
| JSON serialisability | `json.dumps/loads` | Snapshot structure valid |
| Required fields present | Field check | Audit completeness |
| Stage ordering | Name sequence | Pipeline stage order preserved |
| JSONL persistence (5) | File write + read | Multi-entry persistence |
| Single JSON persistence | File write + read | Individual snapshot storage |
| Large batch (100) | File write + read | Scale behaviour |
| Pipeline version present | Field check | Traceability maintained |
| Nested data round-trip | Deep structure | Complex payloads preserved |
| Unicode content | Japanese text | i18n data integrity |
| Empty stages handled | Edge case | Graceful degradation |

### 4. Governance Policy E2E (`test_production_governance.py`)

| What | How | Production Gap Closed |
|------|-----|----------------------|
| GET current policy | HTTP API | Policy readable |
| UPDATE fuji_rules | HTTP PUT + disk verify | Persistence verified |
| UPDATE risk_thresholds | HTTP PUT | Threshold changes applied |
| UPDATE auto_stop | HTTP PUT | Safety controls updatable |
| UPDATE log_retention | HTTP PUT | Audit config changeable |
| History after update | HTTP GET | Audit trail recorded |
| Invalid audit_level rejected | HTTP PUT | Validation enforced |
| Non-dict payload rejected | HTTP PUT | Type safety |
| Idempotent updates | Double PUT | Consistent state |

### 5. Web Search Validation (`test_production_web_search.py`)

| What | How | Production Gap Closed |
|------|-----|----------------------|
| Private host blocking | `_sanitize_websearch_url()` | SSRF prevention |
| Unicode normalisation | `_canonicalize_hostname()` | IDN homograph defence |
| Internal TLD blocking | `_is_obviously_private_or_local_host()` | DNS rebinding defence |
| Response structure | Mocked HTTP | API contract verified |
| Empty query handling | Direct call | Edge case covered |
| Long query truncation | Direct call | Input bounds enforced |
| Control char stripping | String ops | Injection prevention |
| HTML injection safety | Mocked HTTP | XSS prevention |
| No-key graceful failure | Direct call | Fail-safe without config |

### 6. Encryption Fail-Closed (`test_production_encryption.py`)

| What | How | Production Gap Closed |
|------|-----|----------------------|
| Key generation (base64) | `generate_key()` | Valid 256-bit keys |
| Key uniqueness | 10 generations | No key reuse |
| Missing key → None | `_get_key_bytes()` | Explicit null return |
| Missing key → encrypt raises | `encrypt()` | Fail-closed enforced |
| Invalid base64 raises | `_get_key_bytes()` | Misconfiguration detected |
| Wrong key length raises | `_get_key_bytes()` | Key size enforced |
| Encrypt/decrypt round-trip | Full cycle | Functional encryption |
| Wrong key fails | Cross-key decrypt | Key isolation |
| Empty string encryption | Edge case | Empty payloads handled |
| `is_encryption_enabled` True | Valid key | Correct status report |
| `is_encryption_enabled` False | No key | Correct status report |

## Architecture: CI Role Separation

```
┌─────────────────────────────────────────────────────────┐
│                    main.yml (Every PR)                    │
├─────────────────────────────────────────────────────────┤
│  lint → dependency-audit → test (py3.11/3.12)           │
│  test-slow → frontend (lint/test/e2e)                   │
│  Coverage gate: 85% minimum                              │
└─────────────────────────────────────────────────────────┘
                          │
                    Does NOT run
                          │
┌─────────────────────────────────────────────────────────┐
│          production-validation.yml (Manual/Weekly)        │
├─────────────────────────────────────────────────────────┤
│  production-tests: pytest -m "production or smoke"       │
│  docker-smoke: docker compose up + health check          │
│  external-tests: pytest -m external (if secrets set)     │
└─────────────────────────────────────────────────────────┘
```

## Remaining Production Risks

| Risk | Status | Mitigation |
|------|--------|------------|
| Live LLM API validation | Not covered | Requires paid API keys; add `@external` tests when keys available |
| Full Docker compose E2E | Script-ready, not in CI | `scripts/production_validation.sh` runs locally |
| Database persistence | N/A (file-based) | TrustLog file tests cover persistence |
| Multi-node clustering | Not applicable | Single-node architecture |
| TLS/HTTPS validation | Not covered | Add nginx proxy tests in staging |
| Load/stress testing | Not covered | Consider k6/locust for performance validation |
| Kubernetes deployment | Not covered | Add Helm chart tests when K8s support added |

## What This Validation Adds

1. **65 production-like tests** exercising real subsystems (not just mocks)
2. **Fail-closed verification** — encryption key absence is explicitly tested
3. **Tamper detection** — TrustLog chain integrity and signed log tampering
4. **SSRF prevention** — web search security layer validated
5. **Docker topology** — compose file structure verified programmatically
6. **Governance E2E** — policy CRUD through HTTP API with persistence verification
7. **Replay integrity** — audit artifacts verified for serialisation fidelity
8. **Concurrent safety** — TrustLog thread-safety under load
9. **CI isolation** — production tests separated from fast CI to avoid flakiness
10. **Reproducible locally** — all tests run without external services by default
