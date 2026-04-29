# VERITAS OS — AI Coding Agent Instructions

## 1. Project Identity

- **Name**: VERITAS OS v2.0.0
- **Purpose**: Auditable Decision OS for LLM Agents (Proto-AGI Skeleton)
- **Repository**: https://github.com/veritasfuji-japan/veritas_os
- **Author**: Takeshi Fujishita
- **License**: Multi-license (Core = Proprietary EULA, Interface = MIT)
- **Status**: Beta (Pre-release) — Technical DD Score: 84/100 (A-)

## 2. Tech Stack

### Backend (Python)
- **Language**: Python 3.11+ (target: 3.12.12)
- **Framework**: FastAPI 0.121.0 + Uvicorn
- **Data Validation**: Pydantic v2 (2.8.2)
- **LLM Client**: OpenAI SDK (1.51.0), httpx (0.27.2)
- **Serialization**: orjson
- **Build**: setuptools + pyproject.toml
- **Linter**: Ruff (target py311, select: E/F/W/B)
- **Tests**: pytest 8.3.5 + pytest-asyncio + pytest-cov
- **CI Coverage Gate**: ≥ 85% (`--cov-fail-under=85`)
- **Task Runner**: Makefile with `uv` (astral)

### Frontend (TypeScript)
- **Framework**: Next.js 16 (App Router, React 18)
- **Language**: TypeScript 5.7
- **Styling**: Tailwind CSS 3.4 + CVA (class-variance-authority)
- **Package Manager**: pnpm (workspace)
- **Testing**: Vitest + Testing Library (unit), Playwright + axe-core (E2E)
- **i18n**: Custom React Context (ja default, en)
- **Design System**: `@veritas/design-system` (packages/design-system/)
- **Shared Types**: `@veritas/types` (packages/types/) with runtime type guards

### Infrastructure
- Docker + Docker Compose (backend:8000 + frontend:3000)
- GHCR: `ghcr.io/veritasfuji-japan/veritas_os:latest`
- GitHub Actions CI (Python 3.11/3.12 matrix, CodeQL, SBOM)

## 3. Repository Structure (Critical Paths)

```
veritas_os/                     ← Monorepo root
├── veritas_os/                 ← Python backend
│   ├── api/                    ← FastAPI server, routes, schemas, governance
│   │   ├── server.py           ← FastAPI app (37 endpoints)
│   │   ├── routes_decide.py    ← /v1/decide & replay
│   │   ├── routes_trust.py     ← TrustLog & audit
│   │   ├── routes_memory.py    ← Memory CRUD
│   │   ├── routes_governance.py← Governance & policy
│   │   ├── routes_system.py    ← Health, metrics, SSE, halt
│   │   ├── schemas.py          ← Pydantic v2 request/response
│   │   └── governance.py       ← Policy mgmt, 4-eyes approval, RBAC/ABAC
│   ├── core/                   ← Decision engine
│   │   ├── kernel.py           ← Decision computation
│   │   ├── pipeline/           ← 17-stage orchestrator (package)
│   │   ├── fuji/               ← FUJI safety gate (package)
│   │   ├── memory/             ← MemoryOS (package)
│   │   ├── continuation_runtime/ ← Phase-1 observe/shadow
│   │   ├── value_core.py       ← Value alignment + EMA
│   │   ├── world.py            ← WorldModel
│   │   ├── llm_client.py       ← Multi-provider LLM gateway
│   │   ├── debate.py           ← Multi-viewpoint debate
│   │   ├── critique.py         ← Self-critique
│   │   ├── planner.py          ← Action planning
│   │   └── sanitize.py         ← PII masking
│   ├── policy/                 ← Policy compiler, signing, runtime adapter
│   ├── logging/                ← TrustLog, encryption, rotation
│   ├── audit/                  ← Ed25519 signed audit
│   ├── compliance/             ← EU AI Act reports
│   ├── security/               ← SHA-256, Ed25519
│   ├── replay/                 ← Deterministic replay engine
│   ├── observability/          ← OpenTelemetry
│   ├── storage/                ← Pluggable backends (JSONL, PostgreSQL)
│   ├── tools/                  ← Web search, GitHub search
│   ├── prompts/                ← LLM prompt templates
│   └── tests/                  ← 5600+ Python tests
├── frontend/                   ← Next.js 16 Mission Control
│   ├── app/                    ← Pages (/, /console, /audit, /governance, /risk)
│   ├── components/             ← Shared React components
│   ├── features/console/       ← Decision Console feature
│   ├── lib/                    ← API client, validators, utilities
│   ├── locales/                ← i18n files
│   └── e2e/                    ← Playwright E2E tests
├── packages/
│   ├── types/                  ← Shared TS types + runtime validators
│   └── design-system/          ← Card, Button, AppShell
├── spec/                       ← OpenAPI spec (MIT)
├── sdk/                        ← SDK interface (MIT)
├── cli/                        ← CLI interface (MIT)
├── policies/                   ← Policy templates
├── scripts/                    ← Architecture/quality/security checks
├── openapi.yaml                ← OpenAPI 3.x
├── pyproject.toml              ← Python config
├── Makefile                    ← Dev/test commands
└── docker-compose.yml          ← Full-stack orchestration
```

## 4. Architecture Principles (MUST Follow)

### 4.1 Responsibility Boundaries (Enforced in CI)

These boundaries are verified by `scripts/architecture/check_responsibility_boundaries.py`:

| Component    | Owns                                          | Must NOT absorb                                |
|-------------|-----------------------------------------------|-----------------------------------------------|
| **Planner** | Planning structure, action-plan generation    | Kernel orchestration, FUJI policy, Memory I/O |
| **Kernel**  | Decision computation, scoring, debate wiring  | API orchestration, persistence, governance    |
| **FUJI**    | Safety gating, rejection semantics, audit     | Memory mgmt, planner branching, persistence   |
| **MemoryOS**| Storage, retrieval, summarization, security   | Planner policy, kernel decisions, FUJI logic  |
| **Pipeline**| Stage orchestration for /v1/decide            | Decision logic (kernel), safety logic (FUJI)  |

### 4.2 Safety Design

- **FUJI Gate is fail-closed**: ALL exceptions → `status=rejected`, `risk=1.0`. Never silently pass.
- **TrustLog encryption is mandatory**: Missing `VERITAS_ENCRYPTION_KEY` → writes FAIL (by design).
- **PII/secret redaction is automatic**: Before any persistence. No manual `redact()` needed.
- **4-eyes approval**: Governance policy updates require 2 distinct approvers.
- **Legacy pickle is blocked**: RCE risk. Never introduce pickle/joblib deserialization.

### 4.3 Pipeline Architecture

The `/v1/decide` pipeline has 17 traced stages (FUJI/ValueCore/Replay-snapshot
substeps run inside their parent stages). Respect stage ordering:

```
input_norm → memory_retrieval → web_search → normalize_options
  → kernel_execute → absorb_raw_results → fallback_alternatives → model_boost
  → debate → critique → continuation_shadow → fuji_gate
  → value_learning_ema → compute_metrics → evidence_hardening → build_response
  → persist
```

### 4.4 LLM Client

ALL LLM calls MUST go through `veritas_os/core/llm_client.py`. Never call OpenAI SDK directly from other modules.

## 5. Coding Conventions

### Python
- Python 3.11+ syntax. Use `from __future__ import annotations` where needed.
- Type hints on ALL public functions. Use Pydantic v2 models for data classes.
- Ruff lint rules: E, F, W, B (ignore: E501, E402, F401, W291, W293, B007, B009).
- Docstrings: Google style.
- Imports: stdlib → third-party → local. Use absolute imports (`from veritas_os.core.xxx`).
- Error handling: specific exceptions. Never bare `except:`.
- Logging: use Python `logging` module, never `print()` in production code.
- Constants: UPPER_SNAKE_CASE.
- Environment variables: always accessed through config/settings, never scattered.

### TypeScript (Frontend)
- Strict TypeScript. No `any` without explicit justification.
- Runtime type guards (`isDecideResponse`, etc.) for ALL API responses.
- BFF pattern: browser NEVER sees API credentials.
- `sanitizeText()` on ALL API response rendering (XSS defense).
- Components: functional + hooks. No class components.
- Styling: Tailwind CSS + CVA. No inline styles.

### General
- File names: snake_case (Python), kebab-case (TypeScript).
- Commit messages: conventional commits format.
- DCO sign-off required: `Signed-off-by: Name <email>`.

## 6. Testing Rules

### Python Tests
- Location: `veritas_os/tests/` (5600+ tests exist)
- Framework: pytest + pytest-asyncio
- Coverage gate: ≥ 85% (CI-enforced)
- Markers: `@pytest.mark.slow`, `@pytest.mark.production`, `@pytest.mark.smoke`, `@pytest.mark.external`, `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.scenario`, `@pytest.mark.eu_ai_act`
- NEW CODE MUST include tests. Aim for ≥ 90% coverage on new modules.
- Use mocks for LLM calls (never hit real APIs in unit tests).
- Test file naming: `test_<module_name>.py`

### Run commands
```bash
make test                    # All tests (uv + pytest)
make test-cov                # With coverage (≥85% gate)
make test-production         # Production-like validation
make test-smoke              # Smoke tests only
make quality-checks          # Architecture + security checks
```

### Frontend Tests
```bash
pnpm ui:test                 # Vitest unit tests
pnpm ui:typecheck            # Type checking
pnpm --filter frontend e2e   # Playwright E2E
```

## 7. Security Checklist (For Every PR)

- [ ] No secrets/API keys in code or logs
- [ ] PII is redacted before persistence
- [ ] FUJI Gate remains fail-closed (exceptions → rejected)
- [ ] No pickle/joblib deserialization
- [ ] No `NEXT_PUBLIC_*` API base URL variables (leaks internal topology)
- [ ] No wildcard CORS origins with credentials
- [ ] TrustLog entries go through encrypt pipeline
- [ ] New endpoints have `X-API-Key` authentication
- [ ] Governance endpoints have RBAC guard
- [ ] Web search results pass toxicity filter

## 8. Key Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | OpenAI API key |
| `VERITAS_API_KEY` | Yes | Backend auth key |
| `VERITAS_API_SECRET` | Yes | HMAC secret (32+ chars) |
| `VERITAS_ENCRYPTION_KEY` | Yes | TrustLog encryption (base64 32-byte) |
| `LLM_PROVIDER` | No | Default: `openai` |
| `LLM_MODEL` | No | Default: `gpt-4.1-mini` |

## 9. Quality Gates (CI-Enforced)

These checks run in CI and must pass:

1. `pytest` with `--cov-fail-under=85` (Python 3.11/3.12 matrix)
2. CodeQL security scan
3. `scripts/architecture/check_responsibility_boundaries.py`
4. `scripts/architecture/check_core_complexity_budget.py`
5. `scripts/security/check_memory_dir_allowlist.py`
6. `scripts/security/check_httpx_raw_upload_usage.py`
7. `scripts/security/check_subprocess_shell_usage.py`
8. `scripts/security/check_runtime_pickle_artifacts.py`
9. `scripts/quality/check_replay_pipeline_version_unknown_rate.py --max-unknown-rate 0.0`
10. `scripts/quality/check_deployment_env_defaults.py`

## 10. What NOT To Do

- **DO NOT** bypass FUJI Gate or add silent pass-through on safety errors.
- **DO NOT** add direct LLM calls outside `llm_client.py`.
- **DO NOT** store plaintext TrustLog entries.
- **DO NOT** merge Planner logic into Kernel or vice versa (boundary violation).
- **DO NOT** use `pickle`, `joblib`, or `eval()` for deserialization.
- **DO NOT** add `print()` statements. Use `logging` module.
- **DO NOT** skip tests for new code.
- **DO NOT** add `NEXT_PUBLIC_*` API variables in the frontend.
- **DO NOT** modify pipeline stage ordering without updating replay engine.
- **DO NOT** use bare `except:` clauses.

## 11. Bilingual Notes

- README and docs are maintained in **English + Japanese (日本語)**.
- Code comments and docstrings are in **English**.
- Test markers include Japanese descriptions: `unit: 単体テスト`, `integration: 統合テスト`.
- When adding docs, provide both EN and JP versions when possible.

## 12. Useful Commands Cheatsheet

```bash
# Development
make setup                   # Initial environment setup
make dev                     # Backend (port 8000)
make dev-frontend            # Frontend (port 3000)
make dev-all                 # Both
make up                      # Docker Compose full stack

# Testing
make test                    # Unit tests
make test-cov                # Coverage (≥85%)
make quality-checks          # Architecture + security

# Cleanup
make clean-venv              # Remove virtualenv
python scripts/reset_repo_runtime.py --dry-run  # Preview cleanup
```
# User-provided custom instructions

• すべてのコード変更は PEP8 に準拠させる
• 変更部分のみ差分(diffs)で生成する
• 重大な変更は必ず docstring とテストを作る
• Planner / Kernel / Fuji / MemoryOS の責務を越える変更は禁止
• セキュリティリスクは必ず警告する
