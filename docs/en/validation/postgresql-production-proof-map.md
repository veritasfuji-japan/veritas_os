# PostgreSQL Production Path — Compact Proof Map

> Purpose: give external reviewers a single, fast proof surface for the claim
> that PostgreSQL is the formal production path in this repository.

## 1) Why PostgreSQL is the production path

| Production claim | Primary proof | What to verify quickly |
|---|---|---|
| PostgreSQL is the formal production backend posture | [README — PostgreSQL Production Path & Validation Status](../../../README.md#postgresql-production-path--validation-status) | The README explicitly positions PostgreSQL as the formal production path for MemoryOS + TrustLog. |
| Default full-stack runtime path is PostgreSQL | [`docker-compose.yml`](../../../docker-compose.yml) | Confirm `VERITAS_MEMORY_BACKEND=postgresql`, `VERITAS_TRUSTLOG_BACKEND=postgresql`, and PostgreSQL service wiring. |
| Runtime can prove active backend selection | `/health` contract + [`test_production_smoke.py`](../../../veritas_os/tests/test_production_smoke.py) | Verify `storage_backends.memory` and `storage_backends.trustlog` report `postgresql` in compose-backed runs. |
| Operational runbook and migration posture are defined | [PostgreSQL Production Guide](../operations/postgresql-production-guide.md) | Confirm migration, monitoring, and recovery expectations for production-like operation. |

## 2) Automated validation evidence (what runs automatically)

| Evidence category | Automated path | Canonical source |
|---|---|---|
| Tier model and blocking semantics | CI / release / scheduled validation tiers | [`production-validation.md`](production-validation.md) |
| Backend parity and PG implementation coverage | parity matrix + backend-specific tests + known differences | [`backend-parity-coverage.md`](backend-parity-coverage.md) |
| Live PostgreSQL contention evidence | real PG advisory-lock contention subset (`-m "postgresql and contention"`) | [`../../live-postgresql-validation.md`](../../live-postgresql-validation.md) |
| Local reproducibility entrypoints | `make validate-postgresql-live`, `make validate-live-postgresql` | [`../../../Makefile`](../../../Makefile) |

## 3) Parity / contention / release evidence map

- **Parity evidence (breadth):** `test_storage_backend_contract.py`,
  `test_storage_backend_parity_matrix.py`, and related backend unit tests are
  summarized in [`backend-parity-coverage.md`](backend-parity-coverage.md).
- **Contention evidence (depth):** real PostgreSQL advisory-lock contention tests
  are centered in `test_pg_trustlog_contention.py`, tracked in
  [`../../live-postgresql-validation.md`](../../live-postgresql-validation.md).
- **Release evidence (promotion posture):** blocking release posture and tier
  semantics are maintained in [`production-validation.md`](production-validation.md),
  with workflow definitions in `.github/workflows/main.yml`,
  `.github/workflows/release-gate.yml`, and
  `.github/workflows/production-validation.yml`.

## 4) Guarantee boundary (explicit)

### Guaranteed by repository evidence

- PostgreSQL is documented as the formal production path (not only an optional backend).
- Docker Compose default path is PostgreSQL for both MemoryOS and TrustLog.
- Backend parity expectations and known non-parity areas are explicitly documented.
- Real PostgreSQL contention evidence exists and is continuously exercised in CI/scheduled validation.

### Not guaranteed by repository evidence alone

- Environment-specific HA/DR correctness for managed PostgreSQL offerings
  (for example, cloud failover/PITR posture).
- Universal success of live `pg_dump` / `pg_restore` in every target environment.
- Performance/lock behavior under every production-grade saturation pattern.

## 5) Reviewer fast path (5–10 minutes)

1. Read this page once.
2. Open [`production-validation.md`](production-validation.md) and verify tier/blocking model.
3. Open [`backend-parity-coverage.md`](backend-parity-coverage.md) and verify parity/non-parity boundary.
4. Open [`../../live-postgresql-validation.md`](../../live-postgresql-validation.md) and verify real-PG contention evidence.
5. Confirm README entrypoint: [README PostgreSQL section](../../../README.md#postgresql-production-path--validation-status).
