# Live PostgreSQL Validation Evidence (Public)

> Purpose: live PostgreSQL validation に関する公開証拠を 1 箇所に集約し、
> 「何が real PostgreSQL で検証され、何が mock か」を追跡しやすくする。
>
> **Role in documentation set**: live PG validation の公開証拠の正本
>
> Canonical companions:
> - Parity source of truth: `docs/en/validation/backend-parity-coverage.md`
> - Promotion/release gate source of truth: `docs/en/validation/production-validation.md`
> - Operations source of truth: `docs/en/operations/postgresql-production-guide.md`

## Scope

この文書は以下の実体を突き合わせて要約する（本書自体は証拠集約であり、
tier 定義・運用手順・parity 詳細の一次定義は companion docs 側）。

- Validation docs:
  - `docs/en/validation/backend-parity-coverage.md`
  - `docs/en/validation/production-validation.md`
  - `docs/en/operations/postgresql-production-guide.md`
- CI workflows:
  - `.github/workflows/main.yml`
  - `.github/workflows/release-gate.yml`
  - `.github/workflows/production-validation.yml`
- Test modules:
  - `veritas_os/tests/test_pg_trustlog_contention.py`
  - `veritas_os/tests/test_pg_metrics.py`
  - `veritas_os/tests/test_drill_postgres_recovery.py`
  - `veritas_os/tests/test_production_smoke.py`
- Runtime/config entry points:
  - `docker-compose.yml`
  - `Makefile`

## Canonical naming (workflow / job / make target)

この文書で使う canonical 名称は次で固定する。

| kind | canonical name | location |
|---|---|---|
| Workflow (Tier 1) | `CI` | `.github/workflows/main.yml` |
| Job (Tier 1 real PG) | `test-postgresql` | `.github/workflows/main.yml` |
| Workflow (Tier 3) | `Production Validation` | `.github/workflows/production-validation.yml` |
| Job (Tier 3 real PG) | `postgresql-smoke` | `.github/workflows/production-validation.yml` |
| Local reproduction target | `make validate-postgresql-live` | `Makefile` |
| Local alias target | `make validate-live-postgresql` | `Makefile` |

---

## 1) Real PostgreSQL validation modules (live DB evidence)

現時点で、**real PostgreSQL 16 の live service container** に対して
明示的に実行される pytest module は次。

1. `veritas_os/tests/test_pg_trustlog_contention.py`
   - `pytest -m "postgresql and contention"` で実行。
   - `main.yml` の `test-postgresql` job と、
     `production-validation.yml` の `postgresql-smoke` job の両方で稼働。
   - advisory lock (`pg_advisory_xact_lock`) を使う TrustLog 直列化の
     実DB検証（競合・整合性）を担う。

補足:

- `production-validation.yml` の `postgresql-smoke` job は、
  `test_storage_backend_contract.py` / `test_storage_backend_parity_matrix.py` /
  `test_storage_factory.py` も実行するが、
  これらは「real DB を使った end-to-end 書き込み証拠」というより
  「backend parity/contract の回帰検知」寄りであり、
  既存設計説明上は mock-pool 前提の比重が大きい。

---

## 2) Mock-only と real-PG の役割分担

- **Mock-heavy (高速・広範囲回帰)**
  - 目的: backend contract / parity / metrics / script coherence を
    安定かつ高速に担保。
  - 代表: `test_pg_metrics.py`, `test_drill_postgres_recovery.py`,
    `test_storage_*` 系の多く。

- **Real PostgreSQL (高忠実度・競合保証)**
  - 目的: PostgreSQL 固有の advisory lock 競合特性と、
    chain state 一貫性を live DB で検証。
  - 代表: `test_pg_trustlog_contention.py` の
    `@pytest.mark.postgresql` かつ `@pytest.mark.contention` のテスト群。

この分離により、日常CIの速度と、実DBでしか見えない破綻検出を両立する。

---

## 3) Consolidated evidence table

| test file | mock or real PG | workflow / job | purpose | tier | notes |
|---|---|---|---|---|---|
| `veritas_os/tests/test_pg_trustlog_contention.py` (`-m "postgresql and contention"`) | **real PG** | `main.yml` / `test-postgresql` (step: `Run real PostgreSQL contention tests`) | TrustLog advisory lock 直列化、競合時の chain 整合性を live PG で検証 | Tier 1 (PR/main) | 公開証拠として最重要。`postgres:16` service container を使用。 |
| `veritas_os/tests/test_pg_trustlog_contention.py` (`-m "postgresql and contention"`) | **real PG** | `production-validation.yml` / `postgresql-smoke` (step: `Run real PostgreSQL contention tests`) | 上記と同系統の継続監視（weekly/manual） | Tier 3 (scheduled/manual) | 長期ドリフト検知。blocking ではなく advisory。 |
| `veritas_os/tests/test_storage_backend_contract.py` | mock-heavy | `main.yml` / `test-postgresql` (step: `Run backend parity tests (mock-pool)`), `production-validation.yml` / `postgresql-smoke` | JSON/PG contract 互換性回帰検知 | Tier 1 / Tier 3 | job は PG service を持つが、テストの主眼は contract/parity。 |
| `veritas_os/tests/test_storage_backend_parity_matrix.py` | mock-heavy | `main.yml` / `test-postgresql`; `production-validation.yml` / `postgresql-smoke` | JSON vs PG の side-by-side parity | Tier 1 / Tier 3 | 実運用競合保証ではなく、意味論差分の検知が主。 |
| `veritas_os/tests/test_storage_factory.py` | mock-heavy | `main.yml` / `test-postgresql`; `production-validation.yml` / `postgresql-smoke` | backend dispatch / startup fail-fast | Tier 1 / Tier 3 | backend 切替ミス検知。 |
| `veritas_os/tests/test_pg_metrics.py` | mock-only | `main.yml` / `test (py3.11/3.12)` (full suite) | observability metrics helper / collector の回帰検知 | Tier 1 | live PG 接続不要。`/v1/metrics` integration も mock 前提。 |
| `veritas_os/tests/test_drill_postgres_recovery.py` | mock-only | `main.yml` / `governance-smoke` (`-m smoke`), `release-gate.yml` / `governance-smoke`, `production-validation.yml` / `production-tests` (`-m "production or smoke"`) | backup/restore/drill script の存在・文法・runbook整合性検証 | Tier 1 / Tier 2 / Tier 3 | **実 `pg_dump` は実行しない**（script 内容検証中心）。 |
| `veritas_os/tests/test_production_smoke.py` | mixed (主に app-level smoke; live PG は job 依存) | `main.yml` / `governance-smoke`, `release-gate.yml` / `governance-smoke`, `production-validation.yml` / `production-tests`, `release-gate.yml` / `docker-smoke` (curl health checks) | `/health` 契約・compose整合・backend報告の検証 | Tier 1 / 2 / 3 | docker-smoke では real PG backend 起動を外形監視。 |

---

## 4) Tier / 実行タイミング

- **Tier 1 (blocking, every PR + main push)**
  - `main.yml`:
    - `test-postgresql`（PG service + parity + real contention subset）
    - `governance-smoke`（`-m smoke`）
    - `test`（フル unit/metrics 回帰）

- **Tier 2 (blocking, release refs/tags)**
  - `release-gate.yml`:
    - `governance-smoke`
    - `production-tests`（`-m "production or smoke"`）
    - `docker-smoke`（compose 起動 + `/health` backend確認）

- **Tier 3 (advisory, weekly/manual)**
  - `production-validation.yml`:
    - `postgresql-smoke`（PG service + real contention subset）
    - `production-tests`, `docker-smoke`（条件付き）

---

## 5) 何を保証するか（current guarantees）

1. TrustLog append 競合での **advisory-lock 直列化**は、
   real PostgreSQL 16 service container 上で継続的に検証される。
2. backend 選択（memory/trustlog が postgresql か）は、
   workflow と `/health` 検証で回帰検知できる。
3. backend contract/parity の大部分は、
   Tier 1 の高頻度 CI で継続的に担保される。
4. backup/restore/drill については、
   script/runbook の構文・参照整合性が smoke で監視される。

---

## 6) 何をまだ保証しないか（explicit non-guarantees）

1. **pg_dump / pg_restore の live 実行成功**を CI で常時保証しない
   （`test_drill_postgres_recovery.py` は script coherence が中心）。
2. 高負荷・高遅延・本番同等ネットワーク条件下での
   advisory lock 振る舞い（CI は比較的アイドル条件）。
3. managed PostgreSQL (RDS/Cloud SQL など) 固有の
   HA/failover/PITR 成功を repo 内CIだけで保証しない。
4. 全ての PG 関連テストが live DB を使っているわけではない
   （多くは mock-heavy 設計）。

---

## 7) ローカル再現手順

### A. Tier 1 相当（fast check）

```bash
# smoke
make test-smoke

# full suite (includes mock-heavy PG tests)
make test-cov
```

### B. Real PostgreSQL contention tests を単体再現

```bash
# 1) PostgreSQL 起動（compose の postgres service）
docker compose up -d postgres

# 2) backend env
export VERITAS_DATABASE_URL="postgresql+psycopg://veritas:veritas@localhost:5432/veritas"
export VERITAS_MEMORY_BACKEND="postgresql"
export VERITAS_TRUSTLOG_BACKEND="postgresql"

# 3) schema
make db-upgrade

# 4) live contention subset (CIの real-PG step 相当)
make validate-postgresql-live
```

### C. Docker full-stack 外形確認（release-gate の docker-smoke に近い）

```bash
docker compose up -d --build
curl -sf http://localhost:8000/health | python3 -m json.tool
```

`storage_backends.memory == "postgresql"` かつ
`storage_backends.trustlog == "postgresql"` を確認する。

---

## 8) Drift check notes (docs vs implementation)

- 旧パス表記（`docs/BACKEND_PARITY_COVERAGE.md` など）は実体がなく、
  canonical は `docs/en/...` 側。
- 「test-postgresql job で parity を real PG で検証」という表現は、
  実態としては **mock-heavy parity + real contention subset** の混在。
  読み手は「real PG エビデンスは contention subset が中核」と解釈するのが正確。

---

## 9) Link suggestions from existing docs

公開証拠への導線を強化するため、以下から本書へのリンクを推奨。

- `README.md` の PostgreSQL validation section
- `docs/en/validation/backend-parity-coverage.md` 冒頭
- `docs/en/validation/production-validation.md` 冒頭
- `docs/en/operations/postgresql-production-guide.md` 冒頭

推奨アンカー文言:

- **"Live PostgreSQL validation evidence (single entrypoint)"**
