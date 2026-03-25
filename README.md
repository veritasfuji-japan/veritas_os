# VERITAS OS v2.0 — Auditable Decision OS for LLM Agents (Proto-AGI Skeleton)

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.17838349.svg)](https://doi.org/10.5281/zenodo.17838349)
[![DOI (JP Paper)](https://zenodo.org/badge/DOI/10.5281/zenodo.17838456.svg)](https://doi.org/10.5281/zenodo.17838456)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Next.js](https://img.shields.io/badge/Next.js-15-black.svg)](https://nextjs.org/)
[![License](https://img.shields.io/badge/license-Multi--license%20(Core%20Proprietary%20%2B%20MIT)-purple.svg)](LICENSE)
[![CI](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/main.yml/badge.svg)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/main.yml)
[![CodeQL](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/codeql.yml)
[![Docker Publish](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/publish-ghcr.yml/badge.svg)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/publish-ghcr.yml)
[![Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen.svg)](docs/COVERAGE_REPORT.md) <!-- Snapshot value from docs/COVERAGE_REPORT.md; CI gate is configured in .github/workflows/main.yml -->
[![GHCR](https://img.shields.io/badge/GHCR-ghcr.io%2Fveritasfuji--japan%2Fveritas__os-2496ED?logo=docker&logoColor=white)](https://ghcr.io/veritasfuji-japan/veritas_os)
[![README JP](https://img.shields.io/badge/README-日本語-0f766e.svg)](README_JP.md)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Takeshi%20Fujishita-0A66C2?logo=linkedin&logoColor=white)](https://www.linkedin.com/in/takeshi-fujishita-279709392?utm_source=share&utm_campaign=share_via&utm_content=profile&utm_medium=ios_app)

**Version**: 2.0.0  
**Release Status**: Beta  
**Author**: Takeshi Fujishita

VERITAS OS wraps an LLM (e.g. OpenAI GPT-4.1-mini) with a **reproducible, fail-closed safety-gated, hash-chained decision pipeline** and provides a **Mission Control dashboard** (Next.js) for real-time operational visibility. The current public release should be read as a **beta-grade governance platform**: broad in capability, strong in auditability, and intentionally conservative in safety defaults.

> Mental model: **LLM = CPU**, **VERITAS OS = Decision / Agent OS on top**

### Independent Technical DD Score

| Category | Score |
|---|---|
| Architecture | 82 |
| Code Quality | 83 |
| Security | 80 |
| Testing | 88 |
| Production Readiness | 80 |
| Governance | 82 |
| **Overall** | **82 / 100** |
| **Verdict** | **A- (production-approaching governance infrastructure)** |

> Evaluated by independent technical due diligence review (2026-03-15). Full report: `docs/reviews/technical_dd_review_ja_20260315.md`

---

## Quick Links

- **GitHub**: https://github.com/veritasfuji-japan/veritas_os
- **Zenodo paper (EN)**: https://doi.org/10.5281/zenodo.17838349
- **Zenodo paper (JP)**: https://doi.org/10.5281/zenodo.17838456
- **Japanese README**: [`README_JP.md`](README_JP.md)
- **Code review document map**: `docs/notes/CODE_REVIEW_DOCUMENT_MAP.md`

## Contents

- [Beta at a Glance](#beta-at-a-glance)
- [Why VERITAS?](#why-veritas)
- [What It Does](#what-it-does)
- [Project Structure](#project-structure)
- [Frontend — Mission Control Dashboard](#frontend--mission-control-dashboard)
- [API Overview](#api-overview)
- [Quickstart](#quickstart)
- [Docker Compose (Full Stack)](#docker-compose-full-stack)
- [Docker (Backend Only)](#docker-backend-only)
- [Architecture (High-Level)](#architecture-high-level)
- [TrustLog (Hash-Chained Audit Log)](#trustlog-hash-chained-audit-log)
- [Tests](#tests)
- [Security Notes (Important)](#security-notes-important)
- [Roadmap (Near-Term)](#roadmap-near-term)
- [License](#license)
- [Citation (BibTeX)](#citation-bibtex)

---

## Beta at a Glance

| Area | Current beta posture |
|---|---|
| Core decision path | End-to-end `/v1/decide` pipeline is implemented with orchestration, gating, persistence, and replay hooks. |
| Governance | Policy updates, approval workflow, audit trail, and compliance export paths are already first-class. |
| Frontend | Mission Control is feature-rich enough for operator workflows, not just a demo shell. |
| Safety stance | Fail-closed behavior is preferred over permissive fallback across FUJI-, replay-, and TrustLog-adjacent flows. |
| Deployment expectation | Suitable for evaluation, staging, internal pilots, and guarded beta programs; production use still requires environment-specific hardening and operational review. |

**What "beta" means here**
- The architecture is broad and already integrated across backend, frontend, replay, governance, and compliance surfaces.
- The project is **not** positioned as an alpha prototype anymore; it already contains substantial operational and audit infrastructure.
- You should still expect active iteration in policy packs, deployment defaults, and environment-specific integrations.

## Why VERITAS?

Most "agent frameworks" optimize autonomy and tool use.
VERITAS optimizes for **governance**:

- **Fail-closed safety & compliance** enforced by a final gate (**FUJI Gate**) with PII detection, harmful content blocking, prompt injection defense, toxicity filtering for web search results, and policy-driven rules — all safety paths return `rejected` / `risk=1.0` on exception (fail-closed)
- **High-fidelity reproducible decision pipeline** (20+ stages, structured outputs, replay with divergence detection, retrieval snapshot checksum, model version verification)
- **Auditability** via a **hash-chained TrustLog** (tamper-evident, Ed25519-signed, WORM hard-fail mirror, **Transparency log anchor**, **W3C PROV export**)
- **Enterprise governance** — **4-eyes approval** for policy changes, **RBAC/ABAC** access control, **SSE real-time governance alerts**, external secret manager enforcement
- **Memory & world state** as first-class inputs (MemoryOS with vector search + WorldModel with causal transitions)
- **Operational visibility** via a full-stack **Mission Control dashboard** (Next.js) with real-time event streaming, risk analytics, and governance policy management
- **EU AI Act compliance** — built-in compliance reporting, audit export, and deployment readiness checks

**Target users**
- AI safety / agent researchers
- Teams operating LLMs in regulated or high-stakes environments
- Governance / compliance teams building "policy-driven" LLM systems

---

## What It Does

### `/v1/decide` — Full Decision Loop (Structured JSON)

`POST /v1/decide` returns a structured decision record.

Key fields (simplified):

| Field | Meaning |
|---|---|
| `chosen` | Selected action + rationale, uncertainty, utility, risk |
| `alternatives[]` | Other candidate actions |
| `evidence[]` | Evidence used (MemoryOS / WorldModel / web search) |
| `critique[]` | Self-critique & weaknesses |
| `debate[]` | Pro/con/third-party viewpoints |
| `telos_score` | Alignment score vs ValueCore |
| `fuji` | FUJI Gate result (allow / modify / rejected) |
| `gate.decision_status` | Normalized final status (`DecisionStatus`) |
| `trust_log` | Hash-chained TrustLog entry (`sha256_prev`) |
| `extras.metrics` | Per-stage latency, memory hits, web hits |

Pipeline stages:

```text
Input Normalize → Memory Retrieval → Web Search → Options Normalize
  → Core Execute → Absorb Results → Fallback Alternatives → Model Boost
  → Debate → Critique → FUJI Precheck → ValueCore → Gate Decision
  → Value Learning (EMA) → Compute Metrics → Evidence Hardening
  → Response Assembly → Persist (Audit + Memory + World) → Finalize Evidence
  → Build Replay Snapshot
```

Bundled subsystems:

### Responsibility boundaries that matter

These boundaries are enforced in code and tests, and they are important when extending the system:

| Component | Owns | Should not absorb | Recommended extension direction |
|---|---|---|---|
| **Planner** | Planning structure, action-plan generation, planner-oriented summaries | Kernel orchestration, FUJI policy logic, Memory persistence internals | Planner helpers / planner normalization layers |
| **Kernel** | Decision computation, scoring, debate wiring, rationale assembly | API orchestration, persistence, direct governance storage concerns | Kernel stages / QA helpers / contracts |
| **FUJI** | Final safety and policy gating, rejection semantics, audit-facing gate status | Memory management, planner branching, general persistence workflows | FUJI policy, safety-head, and helper modules |
| **MemoryOS** | Memory storage, retrieval, summarization, lifecycle, security controls | Planner policy, kernel decision policy, FUJI gate logic | Memory store / search / lifecycle / security helpers |

This separation is one of the reasons VERITAS is easier to audit and safer to evolve than a single-file "agent loop."

| Subsystem | Purpose |
|---|---|
| **MemoryOS** | Episodic/semantic/procedural/affective memory with vector search (sentence-transformers), retention classes, legal hold, and PII masking |
| **WorldModel** | World state snapshots, causal transitions, project scoping, hypothetical simulation |
| **ValueCore** | Value function with 14 weighted dimensions (9 core ethical + 5 policy-level), online learning via EMA, auto-rebalancing from TrustLog feedback. Context-aware domain profiles (medical/financial/legal/safety), policy-aware score floors (strict/balanced/permissive), per-factor contribution explainability, and auditable weight adjustment trail |
| **FUJI Gate** | Multi-layer safety gate — PII detection, harmful content blocking, sensitive domain filtering, prompt injection defense, confusable character detection, LLM safety head, and policy-driven YAML rules |
| **TrustLog** | Append-only hash-chained audit log (JSONL) with SHA-256 integrity, Ed25519 signatures, WORM hard-fail mirror, Transparency log anchor, and automatic PII data classification |
| **Debate** | Multi-viewpoint reasoning (pro/con/third-party) for transparent decision rationale |
| **Critique** | Self-critique generation with severity-ranked issues and fix suggestions |
| **Planner** | Action plan generation with step-by-step execution strategies |
| **Replay Engine** | High-fidelity reproducible replay of past decisions with diff reporting, retrieval snapshot checksum, model version verification, and dependency version tracking for audit verification |
| **Compliance** | EU AI Act compliance reports, internal governance reports, and deployment readiness checks |

---

## Project Structure

```text
veritas_os/                  ← Monorepo root
├── veritas_os/              ← Python backend (FastAPI)
│   ├── api/                 ← REST API server, schemas, governance
│   │   ├── server.py        ← FastAPI app with 30+ endpoints
│   │   ├── schemas.py       ← Pydantic v2 request/response models
│   │   └── governance.py    ← Policy management with audit trail
│   ├── core/                ← Decision engine
│   │   ├── kernel.py        ← Decision computation engine
│   │   ├── pipeline.py      ← 20+ stage orchestrator
│   │   ├── fuji.py          ← FUJI safety gate
│   │   ├── value_core.py    ← Value alignment & online learning
│   │   ├── memory.py        ← MemoryOS (vector search)
│   │   ├── world.py         ← WorldModel (state management)
│   │   ├── llm_client.py    ← Multi-provider LLM gateway
│   │   ├── debate.py        ← Debate mechanism
│   │   ├── critique.py      ← Critique generation
│   │   ├── planner.py       ← Action planning
│   │   └── sanitize.py      ← PII masking & content safety
│   ├── logging/             ← TrustLog, dataset writer, rotation
│   ├── audit/               ← Signed audit log (Ed25519)
│   ├── compliance/          ← EU AI Act report engine
│   ├── security/            ← SHA-256 hashing, Ed25519 signing
│   ├── tools/               ← Web search, GitHub search, LLM safety
│   ├── replay/              ← Deterministic replay engine
│   └── tests/               ← 3200+ Python tests
├── frontend/                ← Next.js 15 Mission Control dashboard
│   ├── app/                 ← Pages (Home, Console, Audit, Governance, Risk)
│   ├── components/          ← Shared React components
│   ├── features/console/    ← Decision Console feature module
│   ├── lib/                 ← API client, validators, utilities
│   ├── locales/             ← i18n (Japanese / English)
│   └── e2e/                 ← Playwright E2E tests
├── packages/
│   ├── types/               ← Shared TypeScript types & runtime validators
│   └── design-system/       ← Card, Button, AppShell components
├── spec/                    ← OpenAPI specification (MIT)
├── sdk/                     ← SDK interface layer (MIT)
├── cli/                     ← CLI interface layer (MIT)
├── policies/                ← Policy templates (examples are MIT)
├── openapi.yaml             ← OpenAPI 3.x specification
├── docker-compose.yml       ← Full-stack orchestration
├── Makefile                 ← Dev/test/deploy commands
└── pyproject.toml           ← Python project config
```

---

## Frontend — Mission Control Dashboard

The frontend is a **Next.js 15** (React 18, TypeScript) dashboard that provides operational visibility into the decision pipeline.

### Tech Stack

| Layer | Technology |
|---|---|
| Framework | Next.js 15.5 (App Router) |
| Language | TypeScript 5.7 |
| Styling | Tailwind CSS 3.4 + CVA (class-variance-authority) |
| Icons | Lucide React |
| Testing | Vitest + Testing Library (unit), Playwright + axe-core (E2E + accessibility) |
| i18n | Custom React Context (Japanese default, English) |
| Security | CSP with per-request nonce, httpOnly BFF cookies, HSTS, X-Frame-Options |
| Design System | `@veritas/design-system` (Card, Button, AppShell) |
| Shared Types | `@veritas/types` with runtime type guards |

### Pages

| Route | Page | Description |
|---|---|---|
| `/` | **Command Dashboard** | Live event stream (FUJI rejects, policy updates, chain breaks), global health summary, critical rail metrics, operational priorities |
| `/console` | **Decision Console** | Interactive decision pipeline — enter a query, watch 8-stage pipeline execute in real-time, view FUJI gate decision, chosen/alternatives/rejected, cost-benefit analysis, replay diff |
| `/audit` | **TrustLog Explorer** | Browse hash-chained audit trail, verify chain integrity (verified/broken/missing/orphan), stage filtering, regulatory report export (JSON/CSV with PII redaction) |
| `/governance` | **Governance Control** | Edit FUJI rules (8 safety gates), risk thresholds, auto-stop circuit breaker, log retention. Standard and EU AI Act modes. Draft → approval workflow with diff viewer and version history |
| `/risk` | **Risk Dashboard** | 24-hour streaming risk/uncertainty chart, severity clustering, flagged request drilldown, anomaly pattern analysis |

### Architecture

- **BFF (Backend-for-Frontend)** pattern: all API requests proxied through Next.js (`/api/veritas/*`), browser never sees API credentials
- **httpOnly session cookie** (`__veritas_bff`) for authentication, scoped to `/api/veritas/*`
- **Runtime type guards** validate every API response before rendering (`isDecideResponse`, `isTrustLogsResponse`, `validateGovernancePolicyResponse`, etc.)
- **SSE + WebSocket** for real-time event streaming (live FUJI rejects, trust log updates, risk bursts)
- **XSS defense** via `sanitizeText()` on all API response rendering

---

## API Overview

All protected endpoints require `X-API-Key`. The full list of endpoints:

### Decision

| Method | Path | Description |
|---|---|---|
| POST | `/v1/decide` | Full decision pipeline |
| POST | `/v1/fuji/validate` | Validate a single action via FUJI Gate |
| POST | `/v1/replay/{decision_id}` | Deterministic replay with diff report |
| POST | `/v1/decision/replay/{decision_id}` | Alternative replay with mock support |

### Memory

| Method | Path | Description |
|---|---|---|
| POST | `/v1/memory/put` | Store memory (episodic/semantic/procedural/affective) |
| POST | `/v1/memory/get` | Retrieve memory by key |
| POST | `/v1/memory/search` | Vector search with user_id filtering |
| POST | `/v1/memory/erase` | Erase user memories (legal hold protected) |

### Trust & Audit

| Method | Path | Description |
|---|---|---|
| GET | `/v1/trust/logs` | List trust log entries |
| GET | `/v1/trust/{request_id}` | Get single trust log entry |
| POST | `/v1/trust/feedback` | User satisfaction feedback on decisions |
| GET | `/v1/trust/stats` | Trust log statistics |
| GET | `/v1/trustlog/verify` | Verify hash chain integrity |
| GET | `/v1/trustlog/export` | Export signed trustlog |
| GET | `/v1/trust/{request_id}/prov` | W3C PROV-JSON export for audit interoperability |

### Governance

| Method | Path | Description |
|---|---|---|
| GET | `/v1/governance/policy` | Retrieve current governance policy |
| PUT | `/v1/governance/policy` | Update governance policy (hot-reload, **4-eyes approval required**) |
| GET | `/v1/governance/policy/history` | Policy change audit trail |
| GET | `/v1/governance/value-drift` | Monitor value weight EMA drift |

### Compliance & Reporting

| Method | Path | Description |
|---|---|---|
| GET | `/v1/report/eu_ai_act/{decision_id}` | EU AI Act compliance report |
| GET | `/v1/report/governance` | Internal governance report |
| GET | `/v1/compliance/deployment-readiness` | Pre-deployment compliance check |

### System

| Method | Path | Description |
|---|---|---|
| GET | `/health`, `/v1/health` | Health check |
| GET | `/status`, `/v1/status` | Extended status with pipeline/config health |
| GET | `/v1/metrics` | Operational metrics |
| GET | `/v1/events` | SSE stream for real-time UI updates |
| WS | `/v1/ws/trustlog` | WebSocket for live trust log streaming |
| POST | `/v1/system/halt` | Emergency halt (persists halt state) |
| POST | `/v1/system/resume` | Resume after halt |
| GET | `/v1/system/halt-status` | Current halt state |

### Replay

`POST /v1/replay/{decision_id}` re-executes a stored decision using the original recorded inputs and writes a replay artifact to `REPLAY_REPORT_DIR` (`audit/replay_reports` by default) as `replay_{decision_id}_{YYYYMMDD_HHMMSS}.json`.

Replay snapshots include `retrieval_snapshot_checksum` (SHA-256 deterministic hash), `external_dependency_versions`, and `model_version` for reproducibility verification. Model version mismatch is checked by default; snapshots without `model_version` are rejected by default (`VERITAS_REPLAY_REQUIRE_MODEL_VERSION=1`).

> **Note**: LLM responses are inherently non-deterministic even at `temperature=0`. VERITAS Replay is designed as **high-fidelity reproducible re-execution with divergence detection**, not strict deterministic replay.

When `VERITAS_REPLAY_STRICT=1`, replay enforces deterministic settings (`temperature=0`, fixed seed, and mocked external retrieval side effects).

```bash
BODY='{"strict":true}'
TS=$(date +%s)
NONCE="replay-$(uuidgen | tr '[:upper:]' '[:lower:]')"
SIG=$(python - <<'PY'
import hashlib
import hmac
import os

secret=os.environ["VERITAS_API_SECRET"].encode("utf-8")
ts=os.environ["TS"]
nonce=os.environ["NONCE"]
body=os.environ["BODY"]
payload=f"{ts}\n{nonce}\n{body}"
print(hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest())
PY
)

curl -X POST "http://127.0.0.1:8000/v1/replay/DECISION_ID" \
  -H "X-API-Key: ${VERITAS_API_KEY}" \
  -H "X-VERITAS-TIMESTAMP: ${TS}" \
  -H "X-VERITAS-NONCE: ${NONCE}" \
  -H "X-VERITAS-SIGNATURE: ${SIG}" \
  -H "Content-Type: application/json" \
  -d "${BODY}"
```

EU AI Act report generation already reads `replay_{decision_id}_*.json`, so invoking the Replay API updates replay verification data consumed by compliance reporting automatically.

---

## Quickstart

### Option A: Docker Compose (Recommended)

Start both backend and frontend with a single command:

```bash
git clone https://github.com/veritasfuji-japan/veritas_os.git
cd veritas_os

# Copy and edit environment variables
cp .env.example .env
# Edit .env — set OPENAI_API_KEY, VERITAS_API_KEY, VERITAS_API_SECRET

docker compose up --build
```

- Backend: `http://localhost:8000` (Swagger UI at `/docs`)
- Frontend: `http://localhost:3000` (Mission Control dashboard)

### Option B: Local Development

#### Backend

```bash
git clone https://github.com/veritasfuji-japan/veritas_os.git
cd veritas_os

python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
```

> [!WARNING]
> Avoid placing secrets directly in shell history. Prefer a `.env` file (git-ignored) or a
> secrets manager for production environments.

Set environment variables (or use a `.env` file):

```bash
export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
export VERITAS_API_KEY="your-secret-api-key"
export VERITAS_API_SECRET="your-long-random-secret"
export LLM_PROVIDER="openai"
export LLM_MODEL="gpt-4.1-mini"
```

Start the backend:

```bash
python -m uvicorn veritas_os.api.server:app --reload --port 8000
```

#### Frontend

```bash
# From the repository root (requires Node.js 20+ and pnpm)
corepack enable
pnpm install --frozen-lockfile
pnpm ui:dev
```

The frontend starts at `http://localhost:3000`.

Set `VERITAS_API_BASE_URL` if the frontend BFF should reach a backend other than `http://localhost:8000`. Do not set `NEXT_PUBLIC_*` API base URL variables in production because they can expose internal routing details and now trigger BFF fail-closed behavior.

#### Makefile shortcuts

```bash
make setup         # Initialize environment
make dev           # Start backend (port 8000)
make dev-frontend  # Start frontend (port 3000)
make dev-all       # Start both
```

### Try the API

Open Swagger UI at `http://127.0.0.1:8000/docs`, authorize with `X-API-Key`, and run `POST /v1/decide`:

```json
{
  "query": "Should I check tomorrow's weather before going out?",
  "context": {
    "user_id": "test_user",
    "goals": ["health", "efficiency"],
    "constraints": ["time limit"],
    "affect_hint": "focused"
  }
}
```

---

## Docker Compose (Full Stack)

`docker-compose.yml` orchestrates both services:

| Service | Port | Description |
|---|---|---|
| `backend` | 8000 | FastAPI server (built from `Dockerfile`) with health check |
| `frontend` | 3000 | Next.js dev server (Node.js 20), waits for backend to be healthy |

```bash
docker compose up --build   # Start
docker compose down         # Stop
docker compose logs -f      # Follow logs
```

Environment variables (set in `.env` or shell):

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | OpenAI API key (required) |
| `VERITAS_API_KEY` | — | Backend API authentication key |
| `VERITAS_API_SECRET` | `change-me` | HMAC signing secret (32+ chars recommended) |
| `VERITAS_CORS_ALLOW_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | CORS allow-list |
| `VERITAS_API_BASE_URL` | `http://backend:8000` | Frontend BFF (server-only) → backend URL |
| `LLM_PROVIDER` | `openai` | LLM provider |
| `LLM_MODEL` | `gpt-4.1-mini` | LLM model name |

---

## Docker (Backend Only)

Pull the latest image:

```bash
docker pull ghcr.io/veritasfuji-japan/veritas_os:latest
```

Run the API server:

```bash
docker run --rm -p 8000:8000 \
  -e OPENAI_API_KEY="YOUR_OPENAI_API_KEY" \
  -e VERITAS_API_KEY="your-secret-api-key" \
  -e LLM_PROVIDER="openai" \
  -e LLM_MODEL="gpt-4.1-mini" \
  ghcr.io/veritasfuji-japan/veritas_os:latest
```

If your FastAPI entrypoint differs from `veritas_os.api.server:app`, update the
Dockerfile `CMD` accordingly before building the image.

---

## Architecture (High-Level)

```text
┌──────────────────────────────────────────────────────┐
│  Frontend (Next.js 15 / React 18 / TypeScript)       │
│  ┌────────┬──────────┬───────────┬──────────┬──────┐ │
│  │  Home  │ Console  │   Audit   │Governance│ Risk │ │
│  └────┬───┴────┬─────┴─────┬─────┴────┬─────┴──┬───┘ │
│       │ BFF Proxy (httpOnly cookie, CSP nonce)  │     │
│       └─────────────────┬───────────────────────┘     │
└─────────────────────────┼─────────────────────────────┘
                          │ /api/veritas/*
┌─────────────────────────┼─────────────────────────────┐
│  Backend (FastAPI / Python 3.11+)                      │
│       ┌─────────────────┴─────────────────────┐       │
│       │           API Server (server.py)       │       │
│       │   Auth · Rate Limit · CORS · PII mask  │       │
│       └────┬──────┬──────┬──────┬──────┬──────┘       │
│            │      │      │      │      │              │
│  ┌─────────┴┐ ┌───┴───┐ ┌┴─────┐ ┌────┴──┐ ┌────────┴┐│
│  │ Pipeline ││Govern- ││Memory││Trust  ││Compli-  ││
│  │Orchestr. ││ ance   ││ API  ││ API   ││ ance    ││
│  └────┬─────┘└────────┘└──┬───┘└───┬───┘└─────────┘│
│       │                    │       │               │
│  ┌────┴────────────────────┴───────┴────────────┐  │
│  │            Core Decision Engine               │  │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ │  │
│  │  │ Kernel │ │ Debate │ │Critique│ │Planner │ │  │
│  │  └────┬───┘ └────────┘ └────────┘ └────────┘ │  │
│  │       │                                       │  │
│  │  ┌────┴───┐ ┌────────┐ ┌────────┐ ┌────────┐ │  │
│  │  │  FUJI  │ │Value   │ │MemoryOS│ │ World  │ │  │
│  │  │  Gate  │ │ Core   │ │(Vector)│ │ Model  │ │  │
│  │  └────────┘ └────────┘ └────────┘ └────────┘ │  │
│  └──────────────────┬───────────────────────────┘  │
│                     │                              │
│  ┌──────────────────┴───────────────────────────┐  │
│  │  Infrastructure                               │  │
│  │  LLM Client · TrustLog · Replay · Sanitize   │  │
│  │  Atomic I/O · Signing · Tools (Web/GitHub)    │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### Core execution path

| Module | Responsibility |
|---|---|
| `veritas_os/core/kernel.py` | Decision computation — intent detection, option generation, alternative scoring |
| `veritas_os/core/pipeline.py` | 20+ stage orchestrator for `/v1/decide` — validation through audit persistence |
| `veritas_os/core/llm_client.py` | Multi-provider LLM gateway with connection pooling, circuit breaker, retry with backoff |

### Safety & governance

| Module | Responsibility |
|---|---|
| `veritas_os/core/fuji.py` | Multi-layer **fail-closed** safety gate — PII, harmful content, sensitive domains, prompt injection, confusable chars, LLM safety head, policy rules. All exceptions return `rejected` / `risk=1.0` |
| `veritas_os/core/value_core.py` | Value function with 14 weighted dimensions (9 core ethical + 5 policy-level), online learning via EMA, auto-rebalance from TrustLog. Supports context-aware domain profiles, policy-aware score floors, per-factor contribution explainability, and auditable weight adjustment trail |
| `veritas_os/api/governance.py` | Policy CRUD with hot-reload, **4-eyes approval** (2 approvers, no duplicates), change callbacks, audit trail, value drift monitoring, **RBAC/ABAC** access control |
| `veritas_os/logging/trust_log.py` | Hash-chain TrustLog `h_t = SHA256(h_{t-1} ∥ r_t)` with thread-safe append |
| `veritas_os/audit/trustlog_signed.py` | Ed25519-signed TrustLog with **WORM hard-fail** mirror, **Transparency log anchor**, automatic **PII data classification** |

### Memory & world state

| Module | Responsibility |
|---|---|
| `veritas_os/core/memory.py` | Unified episodic/semantic/procedural/affective memory with vector search (sentence-transformers, 384-dim), retention classes, legal hold, PII masking |
| `veritas_os/core/world.py` | World state snapshots, causal transitions, project scoping, hypothetical simulation |

### Reasoning

| Module | Responsibility |
|---|---|
| `veritas_os/core/debate.py` | Multi-viewpoint debate (pro/con/third-party) |
| `veritas_os/core/critique.py` | Self-critique with severity-ranked issues and fix suggestions |
| `veritas_os/core/planner.py` | Action plan generation |

### LLM Client

Supports multiple providers via `LLM_PROVIDER` environment variable:

| Provider | Model | Status |
|---|---|---|
| `openai` | GPT-4.1-mini (default) | Production |
| `anthropic` | Claude | Planned |
| `google` | Gemini | Planned |
| `ollama` | Local models | Planned |
| `openrouter` | Aggregator | Planned |

Features: shared `httpx.Client` with connection pooling (`LLM_POOL_MAX_CONNECTIONS=20`), retry with configurable backoff (`LLM_MAX_RETRIES=3`), response size guard (16 MB), monkeypatchable for testing.

---

## TrustLog (Hash-Chained Audit Log)

TrustLog is a **secure-by-default**, encrypted, hash-chained audit log.

### Security pipeline (per entry)

```text
entry → redact(PII + secrets) → canonicalize(RFC 8785) → chain hash → encrypt → append
```

1. **Redact** — PII (email, phone, address) and secrets (API keys, bearer tokens) are
   automatically masked before any persistence.
2. **Canonicalize** — RFC 8785 canonical JSON ensures deterministic hashing.
3. **Chain hash** — `h_t = SHA256(h_{t-1} || r_t)` provides tamper-evident linking.
4. **Encrypt** — Mandatory at-rest encryption (AES-256-GCM or HMAC-SHA256 CTR-mode).
   Plaintext storage is **not possible** without explicitly opting out.
5. **Append** — Encrypted line written to JSONL with fsync for durability.

### Setup

```bash
# Generate an encryption key (required)
python -c "from veritas_os.logging.encryption import generate_key; print(generate_key())"

# Set the key (required for TrustLog to function)
export VERITAS_ENCRYPTION_KEY="<generated-key>"
```

> **Warning**: Without `VERITAS_ENCRYPTION_KEY`, TrustLog writes will fail with
> `EncryptionKeyMissing`. This is by design — plaintext audit logs are prohibited.

### Verification

```bash
# Verify hash chain integrity (requires decryption key)
python -m veritas_os.scripts.verify_trust_log
```

Key features:

- **Cryptographic chain** — RFC 8785 canonical JSON, deterministic SHA-256
- **Thread-safe** — RLock protection with atomic file writes
- **Dual persistence** — in-memory cache (max 2000 items) + persistent JSONL ledger
- **Signed export** — Ed25519 digital signatures for tamper-proof distribution
- **Chain verification** — `GET /v1/trustlog/verify` validates the full chain
- **Transparency log anchor** — external log integration for independent audit verification (`VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED=1` for fail-closed operation)
- **WORM hard-fail** — write failures to WORM mirror raise `SignedTrustLogWriteError` (`VERITAS_TRUSTLOG_WORM_HARD_FAIL=1`)
- **W3C PROV export** — `GET /v1/trust/{request_id}/prov` returns PROV-JSON for audit tool interoperability
- **PII masking & classification** — automatic PII/secret redaction with data classification tagging (18 PII patterns including email, credit card, phone, address, IP, passport)
- **Frontend visualization** — TrustLog Explorer at `/audit` with chain integrity status (verified/broken/missing/orphan)

---

## Tests

### Backend (Python)

Recommended (reproducible via `uv`):

```bash
make test
make test-cov
```

These targets use `uv` with `PYTHON_VERSION=3.12.12` and automatically download the
interpreter if it is not already installed.

Fast smoke check:

```bash
make test TEST_ARGS="-q veritas_os/tests/test_api_constants.py"
```

Optional overrides:

```bash
make test TEST_ARGS="-q veritas_os/tests/test_time_utils.py"
make test PYTHON_VERSION=3.11
```

### Frontend (TypeScript)

```bash
# Unit tests (Vitest + Testing Library)
pnpm ui:test

# Type checking
pnpm ui:typecheck

# E2E tests (Playwright + axe-core accessibility)
pnpm --filter frontend e2e:install
pnpm --filter frontend e2e
```

### CI / Quality Gate

- GitHub Actions runs **pytest + coverage** on a Python 3.11/3.12 matrix
- CI enforces a minimum coverage gate (`--cov-fail-under`) currently set to **85%**
- **CodeQL** scans for security vulnerabilities
- **SBOM** generated nightly
- **Security gates** workflow for additional security checks
- Coverage artifacts are stored as **XML/HTML** outputs
- The coverage badge is a documentation snapshot value from `docs/COVERAGE_REPORT.md` (planned: automatic update from CI artifacts)

---

## Security Notes (Important)

> [!WARNING]
> VERITAS is designed to fail closed, but **safe-by-default does not mean safe-without-configuration**. Before any beta deployment, verify secrets handling, encryption keys, WORM/transparency settings, and network exposure in your own environment.

**Key beta-era security warnings**
- Do **not** expose the backend with placeholder secrets such as `VERITAS_API_SECRET=change-me`.
- TrustLog encryption is mandatory in secure mode; missing `VERITAS_ENCRYPTION_KEY` will break writes by design rather than silently downgrading security.
- Treat legacy pickle migration in MemoryOS as a temporary migration-only path because deserialization pathways are high risk.
- Review BFF/server routing carefully; leaking internal API topology via public `NEXT_PUBLIC_*` variables weakens the intended boundary.

### Credential and key management

- **API keys**: Avoid exporting secrets directly in shell history where possible. Prefer
  `.env` files (git-ignored) or secret managers and inject them at runtime. Rotate keys
  regularly and limit scope/permissions.
- **Never use placeholder or short secrets**: `VERITAS_API_SECRET` should be a long,
  random value (32+ chars recommended). Placeholder or short secrets can effectively
  disable or weaken HMAC protection.

### API and browser-facing protections

- **CORS safety**: avoid wildcard origins (`*`) when `allow_credentials` is enabled.
  Configure explicit trusted origins only via `VERITAS_CORS_ALLOW_ORIGINS`.
- **Content Security Policy (CSP)**: the frontend middleware injects per-request nonce-based CSP headers. `connect-src 'self'` restricts XHR/fetch to same origin.
- **BFF session cookie**: `__veritas_bff` is httpOnly, Secure, SameSite=strict in production. Browser never sees API credentials.
- **Security headers**: HSTS (1-year, preload), X-Frame-Options DENY, X-Content-Type-Options nosniff, Permissions-Policy (camera/mic/geo disabled).
- **Rate limiting & auth failure tracking**: per-key rate limits with exponential backoff on repeated auth failures.
- **Nonce replay protection**: critical operations protected by HMAC-signed nonces with TTL cleanup.
- **Request body size limit**: configurable via `VERITAS_MAX_REQUEST_BODY_SIZE` (default 10 MB).

### Data safety and persistence

- **TrustLog data**: TrustLog is **encrypted by default** (secure-by-default). All
  entries are automatically redacted for PII/secrets and encrypted before persistence.
  `VERITAS_ENCRYPTION_KEY` must be set; without it, writes fail.
- **Automatic PII/secret redaction**: Email, phone, address, API keys, bearer tokens,
  and secret-like strings are masked before storage — no manual `redact()` call required.
- **Encryption at rest (mandatory)**: Set `VERITAS_ENCRYPTION_KEY` (base64-encoded
  32-byte key). Use `generate_key()` to create one. Store keys in a vault/KMS, never in
  source control.
- **Operational logs are excluded from Git**: runtime logs (for example,
  `veritas_os/memory/*.jsonl`) are ignored via `.gitignore`; anonymized samples live
  under `veritas_os/sample_data/memory/`.

### Fail-closed safety pipeline

- **FUJI Gate fail-closed**: all safety judgment exceptions return `status=rejected`, `risk=1.0`. No silent pass-through on error.
- **Governance boundary guard**: `/v1/fuji/validate` returns 403 by default — explicit opt-in required (`VERITAS_ENABLE_DIRECT_FUJI_API=1`).
- **4-eyes approval**: governance policy updates require 2 distinct approvers (no duplicates, enabled by default).
- **RBAC/ABAC**: `require_governance_access` guard on governance management endpoints with role + tenant verification.
- **External secret manager enforcement**: `VERITAS_ENFORCE_EXTERNAL_SECRET_MANAGER=1` blocks startup without Vault/KMS integration.
- **Web search toxicity filter**: retrieval poisoning / prompt injection heuristics with NFKC normalization, URL decode, base64 decode, and leet-speak detection. Enabled by default (fail-closed); disable with `VERITAS_WEBSEARCH_ENABLE_TOXICITY_FILTER=0`.

### Migration safety

- **Legacy pickle migration is risky**: if you enable legacy pickle migration for
  MemoryOS, treat it as a short-lived migration path and disable it afterward.
  Legacy pickle/joblib loading is blocked at runtime to prevent RCE.

---

## Roadmap (Near-Term)

- CI (GitHub Actions): pytest + coverage + artifact reports
- Security hardening: input validation & secret/log hygiene
- Policy-as-Code: **Policy → ValueCore/FUJI rules → generated tests** (compiler layer)
- Multi-provider LLM support (Anthropic, Google, Ollama, OpenRouter)
- Automatic coverage badge update from CI artifacts

---

## License

This repository is a **multi-license repository** with clear directory scope.

> 日本語補助: このリポジトリは「Coreはプロプライエタリ」「Interfaceはオープン」の二層ライセンスです。

### License matrix (scope by directory)

| Scope | License | Commercial use | Redistribution | Notes |
|---|---|---|---|---|
| Default (entire repo unless overridden) | VERITAS Core Proprietary EULA (`/LICENSE`) | Contract required | Not permitted without written permission | Includes Core decision logic and pipeline |
| `spec/` | MIT (`/spec/LICENSE`) | Permitted | Permitted | Open interface artifacts |
| `sdk/` | MIT (`/sdk/LICENSE`) | Permitted | Permitted | SDK interface layer |
| `cli/` | MIT (`/cli/LICENSE`) | Permitted | Permitted | CLI interface layer |
| `policies/examples/` | MIT (`/policies/examples/LICENSE`) | Permitted | Permitted | Policy templates/examples |

### Core abuse-prevention restrictions (high level)

Under the Core Proprietary EULA, you may not:

- provide Core (or substantially similar functionality) as a competing managed service;
- bypass license keys, metering, or other technical protection controls;
- remove copyright, attribution, proprietary notice, or trademark markings;
- redistribute Core or use Core for commercial production use without a commercial agreement.

See [`LICENSE`](LICENSE), [`TRADEMARKS`](TRADEMARKS), and [`NOTICE`](NOTICE).

### Transition note for existing users

This PR formalizes existing intent into a clearer two-tier structure:

- Core remains proprietary by default.
- Interface assets are explicitly open-licensed by directory.
- No Core logic (Planner/Kernel/FUJI/TrustLog pipeline internals) is open-sourced by this change.

### Roadmap: phased move from mono-repo licensing (Plan B) to multi-repo split (Plan A)

Phase 1 (this PR):
- Directory-scoped licensing in this mono-repo (Core proprietary + interface MIT)

Phase 2 (next PRs):
- `veritas-spec` (OpenAPI/schema)
- `veritas-sdk-python`, `veritas-sdk-js`
- `veritas-cli`
- `veritas-policy-templates`
- Keep `veritas_os` focused on proprietary Core only

For academic use, please cite the Zenodo DOI.

---

## Citation (BibTeX)

```bibtex
@software{veritas_os_2025,
  author = {Fujishita, Takeshi},
  title  = {VERITAS OS: Auditable Decision OS for LLM Agents},
  year   = {2025},
  doi    = {10.5281/zenodo.17838349},
  url    = {https://github.com/veritasfuji-japan/veritas_os}
}
```

---

## Contact

* Issues: [https://github.com/veritasfuji-japan/veritas_os/issues](https://github.com/veritasfuji-japan/veritas_os/issues)
* Email: [veritas.fuji@gmail.com](mailto:veritas.fuji@gmail.com)
