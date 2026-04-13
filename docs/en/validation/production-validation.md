# VERITAS OS — Production Validation Strategy

## Overview

This document describes the **tiered CI/release validation** model for VERITAS OS.
It complements the existing unit/integration test suite (5800+ tests, 87% coverage)
with production-realistic verification that exercises external dependencies,
deployment topology, and fail-closed security controls.

## Tier Model

VERITAS OS uses three validation tiers with explicit blocking semantics:

| Tier | Workflow | Trigger | Blocking? | Purpose |
|------|----------|---------|-----------|---------|
| **Tier 1** | `main.yml` | Every PR + push to `main` | **Yes — blocks merge** | Fast governance-critical checks: lint, security scripts, smoke tests, full unit test suite |
| **Tier 2** | `release-gate.yml` | Every `v*` tag push | **Yes — blocks release** | Production-like validation: production pytest suite, Docker smoke, governance readiness report |
| **Tier 3** | `production-validation.yml` | Weekly schedule + manual | Advisory (weekly), opt-in blocking (release) | Long-running, secrets-required, external/live tests |

### TrustLog staged release gating (new)

`release-gate.yml` now includes a dedicated **TrustLog production matrix** with
`dev`, `secure`, and `prod` profiles.

| Profile | Default mode | Becomes required on |
|---------|--------------|---------------------|
| `dev` | Advisory | `release/*`, `rc/*`, and `v*` refs |
| `secure` | Required | All release-gate runs |
| `prod` | Required | All release-gate runs |

This matrix explicitly validates enterprise TrustLog promotion paths:

- Managed signing capability (current impl: AWS KMS signer)
- Immutable retention capability (current impl: S3 Object Lock mirror)
- Unified verification path
- Capability-aware startup posture validation
- Hard-fail semantics
- Legacy verification compatibility

Failures include actionable guidance and per-profile JUnit artifacts:
`trustlog-production-<profile>-report`.

### What runs where

#### On every PR / push to `main` (Tier 1, `main.yml`)

| Job | Purpose | Blocking |
|-----|---------|---------|
| `lint` | Ruff, Bandit, architecture checks, security scripts | ✅ Yes |
| `dependency-audit` | pip-audit CVE scan + pnpm audit | ✅ Yes |
| `governance-smoke` | `pytest -m smoke` — 16 fast smoke tests | ✅ Yes |
| `test (py3.11/3.12)` | Full unit suite + 85% coverage gate | ✅ Yes |
| `test-slow` | `pytest -m slow` | ✅ Yes |
| `frontend-quality-gate` | ESLint / Vitest / Playwright E2E | ✅ Yes |

#### On `v*` tag push (Tier 2, `release-gate.yml`)

| Job | Purpose | Blocking |
|-----|---------|---------|
| `governance-smoke` | Re-runs Tier 1 smoke at release time | ✅ Yes |
| `security-checks` | Re-runs all security scripts + Bandit | ✅ Yes |
| `trustlog-production-matrix` | TrustLog release profile matrix (`dev`/`secure`/`prod`) | ✅ Yes (`secure`/`prod` always, `dev` on release refs) |
| `production-tests` | `pytest -m "production or smoke"` + TLS + load | ✅ Yes |
| `docker-smoke` | Full-stack Docker Compose health check | ✅ Yes |
| `governance-report` | Generates governance readiness report artifact | ✅ Yes |
| `external-tests` | Live network tests (opt-in via `tier3_external`) | ⚠️ Advisory |
| `release-readiness` | Final summary gate (fails if any Tier 1/2 failed) | ✅ Yes |

#### Weekly / manual (`production-validation.yml`)

| Job | Purpose | Blocking |
|-----|---------|---------|
| `production-tests` | `pytest -m "production or smoke"` | Advisory |
| `tls-validation` | `pytest -m tls` | Advisory |
| `load-validation` | `pytest -m load` | Advisory |
| `docker-smoke` | Docker Compose full-stack smoke | Advisory (schedule/manual only) |
| `external-tests` | Live network tests | Advisory (opt-in) |

## Test Profiles

| Profile | Marker | CI Tier | Description |
|---------|--------|---------|-------------|
| **Unit** | *(default)* | Tier 1 — every PR | Fast, isolated, mocked dependencies |
| **Slow** | `@pytest.mark.slow` | Tier 1 — every PR (parallel job) | Heavier computation, larger datasets |
| **Smoke** | `@pytest.mark.smoke` | Tier 1 + Tier 2 | Lightweight governance invariant verification |
| **Production** | `@pytest.mark.production` | Tier 2 (release) + Tier 3 (weekly) | Production-like flows with real subsystems |
| **External** | `@pytest.mark.external` | Tier 3 — opt-in + secrets | Tests requiring live network/API keys |
| **TLS** | `@pytest.mark.tls` | Tier 2 (release) + Tier 3 (weekly) | TLS/security-header posture verification |
| **Load** | `@pytest.mark.load` | Tier 2 (release) + Tier 3 (weekly) | Lightweight burst/concurrency validation |

## How to Tell If a Release Is Governance-Ready

A VERITAS OS release is **governance-ready** when all of the following hold:

1. The `release-gate.yml` workflow run for the target tag completed with **status=success**
2. The `release-readiness` final job shows **🟢 RELEASE IS GOVERNANCE-READY**
3. The `release-governance-readiness-report` artifact is attached to the workflow run
4. The `governance-readiness-report.json` inside that artifact has `"governance_ready": true`
5. All Tier 1 and Tier 2 blocking jobs passed (no ❌ in the readiness summary)

**Shortcut**: look at the `release-readiness` job in the `Release Gate` workflow run for the
target tag. If it shows a green ✅, the release passed all blocking checks.

### Governance readiness report format

The `governance-readiness-report.json` artifact has this structure:

```json
{
  "schema_version": "1.0",
  "report_type": "governance_readiness",
  "generated_at": "2026-04-10T08:00:00+00:00",
  "release_ref": "v2.1.0",
  "release_sha": "abc1234...",
  "summary": {
    "governance_ready": true,
    "total_checks": 13,
    "passed": 13,
    "blocking_failures": 0,
    "advisory_failures": 0
  },
  "checks": [...],
  "blocking_failures": [],
  "advisory_failures": []
}
```

## Running Production Validation

### Local Execution

```bash
# Run only smoke tests (Tier 1 equivalent)
pytest -m smoke veritas_os/tests/

# Run all production-like tests (Tier 2 equivalent)
make test-production

# Run production tests with verbose output
pytest -m production veritas_os/tests/ -v --tb=long

# Run external tests (requires API keys)
VERITAS_WEBSEARCH_KEY=<key> pytest -m external veritas_os/tests/

# Run staging TLS/load external checks
VERITAS_STAGING_BASE_URL=https://staging.example.com pytest -m "external and (tls or load)" veritas_os/tests/test_production_tls_load.py -v

# Generate a local governance readiness report
python scripts/generate_release_readiness_report.py \
  --ref local \
  --sha $(git rev-parse HEAD) \
  --output /tmp/governance-readiness.json \
  --text-output /tmp/governance-readiness.txt
```

### CI Execution

#### Tier 1 — Automatic on every PR

No action needed. `main.yml` runs automatically on every PR to `main`.
The `governance-smoke` job explicitly labels the fast smoke gate.

#### Tier 2 — Automatic on version tags

```bash
git tag v2.1.0
git push origin v2.1.0
# → release-gate.yml triggers automatically
# → release-readiness job shows pass/fail summary
# → governance-readiness-report artifact uploaded
```

Or trigger manually:
```bash
gh workflow run release-gate.yml --ref v2.1.0
```

#### Tier 3 — Weekly or manual

`production-validation.yml` runs weekly (Sunday 04:00 UTC) or on demand:

```bash
gh workflow run production-validation.yml
# With Docker and external tests:
gh workflow run production-validation.yml \
  -f include_docker=true \
  -f include_external=true
```

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

### 0. Runtime Security Guardrails (CI + Production Validation)

| What | How | Production Gap Closed |
|------|-----|----------------------|
| Legacy `.pkl` / `.joblib` artifact ban | `check_runtime_pickle_artifacts.py` in CI + production-validation workflow | Runtime RCE surface continuously monitored |
| Bare `except:` ban | `check_bare_except_usage.py` in CI + production-validation workflow | Silent error masking reduced in staged manner |

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

### 7. TLS Header Validation (`test_production_tls_load.py`)

| What | How | Production Gap Closed |
|------|-----|----------------------|
| HSTS header present | `/health` response header assertion | Browser HTTPS enforcement posture verified |
| Baseline security headers | `/health` response header assertion | CSP / anti-clickjacking / MIME hardening verified |
| X-Response-Time observability | `/health` header check | Monitoring header present |
| Security headers on errors | 404 response header check | Headers enforced on all responses |
| Staging TLS header validation (`@external`) | HTTPS `/health` against `VERITAS_STAGING_BASE_URL` | Reverse-proxy TLS hardening verified in staging |
| Staging TLS cert expiry (`@external`) | SSL socket cert check (> 30 day threshold) | Certificate validity window verified |

### 8. Load Burst Validation (`test_production_tls_load.py`)

| What | How | Production Gap Closed |
|------|-----|----------------------|
| Concurrent health burst (32 req / 8 workers) | ThreadPool + latency percentile summary | Latency budget enforcement with p50/p90/p95/p99 |
| Governance policy burst (16 req / 4 workers) | ThreadPool + latency summary | Governance endpoint load regression signal |
| Staging burst p95 check (`@external`) | 32 HTTPS requests + p95 ≤ 800ms | Staging-level performance regression signal |

### 9. Compose Governance Smoke (`test_production_compose_governance.py`)

| What | How | Production Gap Closed |
|------|-----|----------------------|
| Governance policy contract | GET + field assertions | fuji_rules, risk_thresholds, auto_stop, log_retention |
| Governance history reachable | GET 200 check | Audit trail API accessible |
| Decide auth enforcement | POST without key → 401/403 | Auth middleware verified |
| Health subsystem reporting | Checks in health response | pipeline, memory, trust_log subsystems |
| Security headers on health | Response header assertions | Hardening present on health endpoint |
| OpenAPI governance paths | Schema path check | Governance + decide in API schema |
| Governance policy latency | 10 sequential calls, p95 < 500ms | Governance read performance budget |
| Health endpoint latency | 20 sequential calls, p95 < 200ms | Health endpoint performance budget |

### 10. PostgreSQL Contention (`test_pg_trustlog_contention.py`)

| What | How | Production Gap Closed |
|------|-----|----------------------|
| 2-worker simultaneous append | Mock advisory lock + asyncio.gather | Chain intact under basic concurrency |
| N-worker burst (5/10/20) | N concurrent appends + chain verify | Burst write safety |
| Statement timeout → fail-closed | Simulated INSERT/lock/UPDATE timeout | No silent pass on timeout |
| Pool starvation → fail-closed | Broken pool factory | Fail-closed on resource exhaustion |
| Rollback recovery | Success → failure → success cycle | Chain unaffected by mid-append crash |
| Advisory lock release | Check lock availability after commit/rollback | No leaked locks |
| Chain verification (hash formula) | SHA-256 recompute across all entries | End-to-end chain integrity |
| Threaded contention | OS threads × asyncio.run per thread | Multi-worker deployment approximation |

### 11. PostgreSQL Metrics (`test_pg_metrics.py`)

| What | How | Production Gap Closed |
|------|-----|----------------------|
| Pool gauge definitions | Attribute existence check | All required metrics exist |
| Recording helpers | Monkeypatched metric probes | Labels and values correct |
| Pool-stats collection | Mock pool → `collect_pool_stats()` | in_use/available/waiting derived correctly |
| pg_stat_activity collection | Mock cursor → `collect_pg_activity()` | long_running/idle_in_tx/advisory_lock_wait parsed |
| Health-check gauge | Healthy + unhealthy mock pool | Gauge reflects true DB state |
| `/v1/metrics` integration | TestClient GET + field assertions | Endpoint includes db_pool, db_health, db_activity |
| File-backend stub | Null pool → safe defaults | Graceful degradation without PG |
| Metric name stability | Key presence check | No metric name regression |

### 12. Recovery Drill Scripts (`test_drill_postgres_recovery.py`)

| What | How | Production Gap Closed |
|------|-----|----------------------|
| Script existence | Path.exists() for 3 scripts | Deployment package complete |
| Script executable | `os.access(X_OK)` | Scripts runnable without `bash` prefix |
| Bash syntax valid | `bash -n` for 3 scripts | No syntax errors in drill scripts |
| `--help` flag | Subprocess exit code + output | Self-documenting scripts |
| Content coherence (pg_dump, etc.) | String assertions on script body | Correct tools referenced |
| Runbook coherence | Assertions on `postgresql-drill-runbook.md` | Docs ↔ scripts consistency |

## Architecture: CI Role Separation

```
┌──────────────────────────────────────────────────────────────┐
│            main.yml  (Tier 1 — Every PR + push to main)      │
├──────────────────────────────────────────────────────────────┤
│  lint → dependency-audit → governance-smoke                  │
│    → test (py3.11/3.12, 85% coverage gate)                   │
│    → test-slow → frontend (lint/test/e2e)                    │
│  governance-smoke: pytest -m smoke  [BLOCKING]               │
└──────────────────────────────────────────────────────────────┘
                          │ does NOT run production tests
                          │
┌──────────────────────────────────────────────────────────────┐
│        release-gate.yml  (Tier 2 — on v* tag push)           │
├──────────────────────────────────────────────────────────────┤
│  governance-smoke → security-checks [Tier 1 repeat, BLOCKING]│
│    → production-tests: pytest -m "production or smoke"       │
│    → docker-smoke: full-stack Docker Compose health check    │
│    → governance-report: generates readiness report artifact  │
│    → release-readiness: final ✅/❌ gate  [BLOCKING]         │
│  external-tests: live tests  [Tier 3, advisory]              │
└──────────────────────────────────────────────────────────────┘
                          │ advisory only
                          │
┌──────────────────────────────────────────────────────────────┐
│   production-validation.yml  (Tier 3 — Weekly/Manual)        │
├──────────────────────────────────────────────────────────────┤
│  production-tests: pytest -m "production or smoke"           │
│  tls-validation: pytest -m tls                               │
│  load-validation: pytest -m load                             │
│  docker-smoke: docker compose up + health check              │
│  external-tests: pytest -m external (if secrets set)         │
└──────────────────────────────────────────────────────────────┘
```

## Remaining Production Risks

| Risk | Status | Mitigation |
|------|--------|------------|
| Live LLM API validation | **Gated** — `scripts/live_provider_validation.sh` | Requires OPENAI_API_KEY; runs in Tier 3 / manual |
| Full Docker compose E2E | **Validated** — `scripts/compose_validation.sh` | Governance endpoints, security headers, auth enforcement |
| Database persistence (PostgreSQL) | **Covered** — mock pool in unit tests, real PG in `test-postgresql` + `docker-smoke` + `postgresql-smoke` CI jobs | See `docs/en/validation/backend-parity-coverage.md` for 279+ parity + hardening tests |
| Database persistence (JSONL) | **Covered** — TrustLog file tests | File-based persistence fully tested |
| PostgreSQL schema migrations | **Covered** — Alembic migrations tested in `test-postgresql` CI job | Forward + rollback paths tested |
| JSONL → PostgreSQL import | **Covered** — `veritas-migrate` CLI with unit tests | Idempotent import with dry-run, resume, and post-import chain verification |
| PostgreSQL advisory lock contention | **Covered** — 25 contention tests in `test_pg_trustlog_contention.py` | Mock advisory lock via `threading.Lock`; real PG in CI `test-postgresql` job |
| PostgreSQL pool/activity metrics | **Covered** — 28 metrics tests in `test_pg_metrics.py` | Pool gauges, health, pg_stat_activity, `/v1/metrics` integration |
| PostgreSQL backup/restore/drill | **Covered** — 31 drill tests + scripts + runbook | Script syntax, coherence, and runbook consistency validated |
| Multi-node clustering | Not applicable | Single-node architecture; PgBouncer recommended for high-concurrency |
| TLS certificate chain/e2e HTTPS handshake | **Gated** — staging cert expiry checked | `@external` staging HTTPS tests + cert expiry validation |
| Load/stress at scale (p95/p99 latency SLO) | **Partially covered** — latency budgets enforced | p95 budgets on health (200ms), governance (500ms), burst (1000ms) |
| Kubernetes deployment | Not covered | Add Helm chart tests when K8s support added |

## Additional Validation Paths

### Compose Governance Validation (`scripts/compose_validation.sh`)

Full-stack Docker Compose validation that exercises:
- Backend health with subsystem checks (pipeline, memory, trust_log)
- Frontend reachability
- OpenAPI schema with critical path verification (/v1/decide, /v1/governance, /v1/trust)
- Governance policy read + history endpoints
- Auth enforcement (401/403 without API key)
- Security header presence (HSTS, CSP, X-Frame, X-Content-Type)

```bash
# Basic run
scripts/compose_validation.sh

# With JSON report
scripts/compose_validation.sh --json-report /tmp/compose-report.json

# Reuse running services
scripts/compose_validation.sh --skip-build
```

### Live Provider Validation (`scripts/live_provider_validation.sh`)

Gated validation against real external services (all checks skip when secrets absent):
- OpenAI API connectivity (cheapest call: /v1/models list)
- LLM client end-to-end smoke (minimal completion)
- Staging deployment health, TLS cert expiry, security headers
- Web search provider integration

```bash
# All checks skip unless secrets are set
OPENAI_API_KEY=sk-... scripts/live_provider_validation.sh
VERITAS_STAGING_BASE_URL=https://staging.example.com scripts/live_provider_validation.sh

# With JSON report
scripts/live_provider_validation.sh --json-report=/tmp/live-report.json
```

### Staged Readiness Report (`scripts/generate_staged_readiness_report.py`)

Combines governance checks, compose validation, and live provider results into
a single v2.0 operational readiness report (JSON + text):

```bash
python scripts/generate_staged_readiness_report.py \
  --ref $(git describe --tags --always) \
  --sha $(git rev-parse HEAD) \
  --compose-report /tmp/compose-report.json \
  --live-report /tmp/live-report.json \
  --output /tmp/staged-report.json \
  --text-output /tmp/staged-report.txt
```

See [`operational-readiness-runbook.md`](../operations/operational-readiness-runbook.md) for full usage and troubleshooting.

## Capability-Aware Startup Validation

### Design

Starting with v2.0, the secure/prod startup validator uses a **capability-aware**
model rather than hard-coded vendor names. Each TrustLog backend declares a set
of security capabilities, and the validator checks that the configured backends
satisfy the posture's requirements.

This design means that **adding a new backend** (e.g. Azure Key Vault, GCP Cloud
KMS, or an on-prem HSM) requires only:

1. Implementing the backend class (conforming to existing protocols).
2. Registering the backend's proven capabilities in the capability registry
   (`_SIGNER_CAPABILITIES`, `_MIRROR_CAPABILITIES`, or `_ANCHOR_CAPABILITIES`
   in `veritas_os/core/posture.py`).

The core validation logic (`validate_posture_startup`) does **not** need to change.

### Capabilities

| Capability | Required for | Meaning |
|------------|-------------|---------|
| `managed_signing` | secure/prod signer | Key material held in managed HSM/KMS; never on application host |
| `immutable_retention` | secure/prod mirror | Tamper-proof, append-only object retention enforced by storage service |
| `transparency_anchoring` | when `VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED=1` | Backend produces verifiable proof-of-existence anchor |
| `fail_closed` | secure/prod (all backends) | Errors result in hard refusal, never silent pass |

### Current Implementations

| Component | Backend | Capabilities |
|-----------|---------|-------------|
| Signer | `aws_kms` | `managed_signing`, `fail_closed` |
| Signer | `file` | *(none — dev/staging only)* |
| Mirror | `s3_object_lock` | `immutable_retention`, `fail_closed` |
| Mirror | `local` | *(none — dev/staging only)* |
| Anchor | `local` | `transparency_anchoring`, `fail_closed` |
| Anchor | `tsa` | `transparency_anchoring`, `fail_closed` |
| Anchor | `noop` | *(none — dev/staging only)* |

> **Note:** The current production-supported implementation uses **AWS KMS** for
> signing and **S3 Object Lock** for mirroring. No new backend implementations
> were added in this release — only the validation framework was restructured
> to be capability-aware.

### Future Work

When adding Azure, GCP, or on-prem backends:

- Implement the backend class conforming to the `Signer` / `StorageMirror` /
  `AnchorBackend` protocol.
- Register capabilities in the posture module's registry dictionaries.
- No changes to `validate_posture_startup` should be necessary.

## What This Validation Adds

1. **75+ production-like tests** exercising real subsystems (not just mocks)
2. **Fail-closed verification** — encryption key absence is explicitly tested
3. **Tamper detection** — TrustLog chain integrity and signed log tampering
4. **SSRF prevention** — web search security layer validated
5. **Docker topology** — compose file structure verified programmatically
6. **Governance E2E** — policy CRUD through HTTP API with persistence verification
7. **Replay integrity** — audit artifacts verified for serialisation fidelity
8. **Concurrent safety** — TrustLog thread-safety under load
9. **CI isolation** — production tests separated from fast CI to avoid flakiness
10. **Reproducible locally** — all tests run without external services by default
11. **Compose governance smoke** — governance endpoint reachability in full-stack deploy
12. **Latency budgets** — p95 enforcement on health (200ms), governance (500ms), burst (1000ms)
13. **TLS cert validation** — staging certificate expiry check (> 30 day threshold)
14. **Live provider gating** — OpenAI / staging / web search validation with secret gating
15. **Staged readiness reports** — machine-readable JSON + human-readable text certification
16. **Coverage matrix** — explicit proof/simulation/environment documentation
