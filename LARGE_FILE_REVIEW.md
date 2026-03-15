# Large File Review: Technical Debt Candidates

**Date:** 2026-03-15
**Scope:** Source files exceeding 1,000 lines that should be split to prevent technical debt

---

## Executive Summary

| Priority | File | Lines | Recommended Splits |
|----------|------|------:|:------------------:|
| CRITICAL | `veritas_os/api/server.py` | 3,536 | 13 modules |
| CRITICAL | `veritas_os/core/memory.py` | 2,130 | 12 modules |
| HIGH | `veritas_os/core/eu_ai_act_compliance_module.py` | 2,036 | 6 modules |
| HIGH | `veritas_os/core/fuji.py` | 1,680 | 5 modules |
| HIGH | `veritas_os/core/planner.py` | 1,407 | 5 modules |
| HIGH | `frontend/app/audit/page.tsx` | 1,322 | 5 components |
| HIGH | `veritas_os/tools/web_search.py` | 1,306 | 5 modules |
| MEDIUM | `veritas_os/core/pipeline.py` | 1,223 | 4 modules |
| MEDIUM | `veritas_os/core/world.py` | 1,084 | TBD |
| MEDIUM | `veritas_os/core/kernel.py` | 1,076 | TBD |
| MEDIUM | `veritas_os/api/schemas.py` | 1,039 | TBD |

---

## 1. `veritas_os/api/server.py` (3,536 lines) — CRITICAL

### Current State

8 classes, 76 top-level functions, 43 API endpoints, 6 middleware components packed into a single file.

### Identified Responsibility Groups

| Group | Approx Lines | Description |
|-------|-------------:|-------------|
| Authentication & Authorization | 700+ | API key validation, HMAC verification, AuthSecurityStore (Protocol + InMemory + Redis), auth failure tracking |
| Middleware & Request Processing | 400+ | Trace ID, response time, rate limit headers, body size limiting, security headers, in-flight tracking |
| Trust Log & Auditing | 400+ | Trust log file I/O, verification, export, PROV document generation, statistics |
| Core Decision APIs | 500+ | `/v1/decide`, `/v1/replay`, `/v1/fuji/validate`, error handling, payload coercion |
| Governance & Policy | 350+ | Policy CRUD, value drift, alerts, RBAC/ABAC, four-eyes approval |
| Rate Limiting & Nonce | 300+ | Rate bucket tracking, nonce replay prevention, scheduled cleanup |
| Compliance & Reporting | 250+ | EU AI Act reports, deployment readiness, compliance config |
| Real-time Streaming | 200+ | SSE event hub, `/v1/events`, WebSocket `/v1/ws/trustlog` |
| Memory Store APIs | 200+ | `/v1/memory/put`, `/v1/memory/search`, `/v1/memory/get`, `/v1/memory/erase` |
| System Control | 150+ | Emergency halt/resume, LLM pool cleanup, graceful shutdown |
| Initialization & Lazy Loading | 150+ | LazyState, startup validation, config/pipeline/FUJI lazy imports |
| Utilities & Helpers | 250+ | Error formatting, redaction, ID generation, JSON operations |

### Recommended Split

```
api/
├── server.py              # (~200 lines) FastAPI app init, lifespan, health endpoints, route registration
├── auth.py                # (~700 lines) API key, HMAC, AuthSecurityStore, auth failure tracking
├── rate_limiting.py       # (~300 lines) Rate bucket, nonce replay prevention, scheduled cleanup
├── middleware.py           # (~400 lines) Trace ID, response time, security headers, body size
├── routes/
│   ├── decision.py        # (~500 lines) /v1/decide, /v1/replay, /v1/fuji/validate
│   ├── memory.py          # (~200 lines) /v1/memory/*
│   ├── trust.py           # (~400 lines) /v1/trust/*, /v1/trustlog/*
│   ├── governance.py      # (~350 lines) /v1/governance/*
│   ├── compliance.py      # (~250 lines) /v1/compliance/*, /v1/report/*
│   ├── system.py          # (~150 lines) /v1/system/*
│   └── streaming.py       # (~200 lines) /v1/events, /v1/ws/trustlog
├── config.py              # (~200 lines) CORS, lazy loading, startup validation
└── utils.py               # (~250 lines) Error formatting, redaction, ID generation, JSON ops
```

### Key Risks If Not Split

- Merge conflicts: 43 endpoints in one file makes parallel development difficult
- Test isolation: Cannot unit-test auth logic without importing all routes
- Cognitive load: 3,500+ lines exceeds reasonable comprehension limits
- Deployment: Any change to any endpoint requires reviewing the entire file

---

## 2. `veritas_os/core/memory.py` (2,130 lines) — CRITICAL

### Current State

3 classes (`VectorMemory`, `MemoryStore`, `_LazyMemoryStore`) plus 30+ module-level functions mixing vector search, KVS persistence, file locking, GDPR compliance, LLM-based distillation, and global state management.

### Identified Responsibility Groups

| Group | Approx Lines | Description |
|-------|-------------:|-------------|
| VectorMemory (embeddings) | 415 | Sentence-transformer embeddings, cosine similarity, JSON persistence with Base64 numpy |
| MemoryStore (KVS core) | 683 | JSON-based key-value store, file locking, in-memory TTL cache, lifecycle metadata |
| GDPR / Compliance | 100+ | User erasure with audit trail, cascade deletion for semantic lineage, legal hold |
| Memory Distillation | 200 | Episodic-to-semantic summarization via LLM, prompt engineering |
| Search Orchestration | 150 | Dual-mode search (vector -> KVS fallback), deduplication, user filtering |
| Evidence Formatting | 80 | Evidence conversion for `/v1/decide` |
| Model Loading | 80 | ONNX model loading, external model compatibility |
| Global State / Lazy Init | 100 | `_LazyMemoryStore`, global `MEM`, `MEM_VEC`, once-only guards |
| File I/O & Locking | 70 | `locked_memory()` context manager, POSIX fcntl / Windows fallback |
| Module-level API Wrappers | 140 | `add()`, `put()`, `get()`, `search()`, `recent()`, etc. |

### Recommended Split

```
memory/
├── __init__.py            # (~100 lines) Public API exports, module-level wrappers
├── vector.py              # (~250 lines) VectorMemory class (embeddings, search)
├── store.py               # (~300 lines) MemoryStore KVS core
├── lifecycle.py           # (~100 lines) Retention, expiration, legal hold
├── compliance.py          # (~100 lines) User erasure, cascade delete, audit trail
├── distillation.py        # (~150 lines) Episodic-to-semantic LLM summarization
├── search.py              # (~150 lines) Search orchestration (vector -> KVS fallback)
├── evidence.py            # (~50 lines)  Evidence formatting for /v1/decide
├── storage.py             # (~150 lines) File I/O, locking, JSON serialization
├── models.py              # (~80 lines)  Model loading, external compatibility
└── config.py              # (~40 lines)  Environment variable configuration
```

### Key Risks If Not Split

- Thread-safety: 5 independent locks scattered across file make reasoning about concurrency difficult
- Compliance coupling: GDPR logic embedded in KVS makes compliance auditing harder
- Two storage backends (vector + KVS) with no clear boundary

---

## 3. `veritas_os/core/eu_ai_act_compliance_module.py` (2,036 lines) — HIGH

### Current State

5 classes and 21 top-level functions implementing EU AI Act compliance across Articles 5, 9, 10, 12, 13, 14, 15, and 50.

### Identified Responsibility Groups

| Group | Article(s) | Approx Lines | Description |
|-------|-----------|-------------:|-------------|
| Prohibited Practices Detection | Art. 5 | 360 | Pattern normalization, n-gram similarity, multi-language matching |
| Risk Classification | Art. 9 | 30 | Annex III high-risk domain classification |
| Human Oversight | Art. 14 | 210 | `HumanReviewQueue` (SLA tracking, webhook), `SystemHaltController` |
| Documentation & Transparency | Art. 12, 13 | 300 | Tamper-evident trust logs, third-party notifications, log retention |
| Content Watermarking | Art. 50 | 80 | C2PA-compatible watermark metadata |
| Compliance Pipeline | Multiple | 140 | `eu_compliance_pipeline()` decorator for `/v1/decide` |
| Deployment Validation | Art. 6, 10, 15 | 500+ | PII safety, synthetic data, audit readiness, legal approval, CE marking, data quality |
| Degraded Mode | Art. 15 | 50 | Safe response when LLM unavailable |

### Recommended Split

```
compliance/
├── __init__.py                # Re-exports, backward compatibility
├── prohibited_practices.py    # (~360 lines) Art. 5: pattern detection, n-gram, normalization
├── human_oversight.py         # (~210 lines) Art. 14: HumanReviewQueue, SystemHaltController
├── transparency.py            # (~300 lines) Art. 12/13: trust logs, notifications, watermarking
├── deployment_validation.py   # (~500 lines) Art. 6/10/15: PII, data quality, CE marking, legal
├── pipeline.py                # (~140 lines) Compliance pipeline decorator
└── config.py                  # (~50 lines)  EUComplianceConfig, retention config
```

---

## 4. `veritas_os/core/fuji.py` (1,680 lines) — HIGH

### Current State

1 dataclass (`SafetyHeadResult`) and 30+ functions implementing the FUJI safety gate: policy engine, LLM safety evaluation, prompt injection detection, and multi-stage decision logic.

### Identified Responsibility Groups

| Group | Approx Lines | Description |
|-------|-------------:|-------------|
| Policy Engine | 430 | YAML loading, hot-reload, runtime pattern compilation, policy application |
| Safety Head Evaluation | 200 | LLM-based safety scoring, fallback heuristics, penalty application |
| Prompt Injection Detection | 100 | Injection detection, text normalization, scoring |
| Core Decision Logic | 350 | `fuji_core_decide()` — multi-stage safety, evidence checks, risk aggregation |
| Output Interfaces | 300 | `fuji_gate()`, `validate_action()`, `posthoc_check()`, `evaluate()` |
| Utilities & Trust Log | 200 | Text normalization, redaction, FUJI code selection, trust events |

### Recommended Split

```
fuji/
├── __init__.py          # Re-exports
├── policy.py            # (~430 lines) Policy loading, hot-reload, pattern compilation
├── safety_head.py       # (~200 lines) LLM safety evaluation, fallback heuristics
├── injection.py         # (~100 lines) Prompt injection detection & scoring
├── core.py              # (~350 lines) fuji_core_decide(), risk aggregation
└── gate.py              # (~300 lines) fuji_gate(), validate_action(), evaluate()
```

### Key Risk

- `fuji_core_decide()` concentrates safety head + policy + injection + deterministic rules in deeply nested logic — highest single-function complexity in the codebase

---

## 5. `veritas_os/core/planner.py` (1,407 lines) — HIGH

### Identified Responsibility Groups

| Group | Approx Lines | Description |
|-------|-------------:|-------------|
| JSON Parsing & Extraction | 680+ | Input sanitization, safe JSON rescue with retry, multi-strategy extraction |
| Planning Decision Logic | 190 | Simple Q&A detection, step1 detection, immediate planning |
| LLM Prompt Engineering | 130 | System/user prompt construction |
| Fallback & Recovery | 80 | Ultra-safe fallback plans, VERITAS stage inference |
| Hybrid Planning | 180 | World Model + LLM integration, memory snippet retrieval |
| Code Task Generation | 140 | Benchmark-based code task generation |

### Recommended Split

```
planner/
├── __init__.py          # Re-exports, generate_plan() backward compat
├── json_parsing.py      # (~680 lines) JSON extraction, rescue, retry
├── detection.py         # (~190 lines) Simple QA detection, step1 detection
├── prompts.py           # (~130 lines) System/user prompt construction
├── fallback.py          # (~80 lines)  Fallback plans, VERITAS stage inference
└── hybrid.py            # (~320 lines) World+LLM planning, code task generation
```

### Notable Concern

- JSON parsing accounts for ~48% of the file — a clear candidate for extraction

---

## 6. `frontend/app/audit/page.tsx` (1,322 lines) — HIGH

### Current State

Single React component (`TrustLogExplorerPage`) containing all state, hooks, handlers, and JSX for the entire audit page.

### Recommended Split

```
frontend/app/audit/
├── page.tsx                  # (~100 lines) Main page, composition of sub-components
├── constants.ts              # (~60 lines)  Status colors, page limits
├── hooks/
│   └── useAuditData.ts       # (~200 lines) Data fetching, filtering, sorting, memos
├── handlers/
│   └── useAuditActions.ts    # (~250 lines) Verify, export, report, search handlers
└── components/
    ├── SearchPanel.tsx        # (~150 lines) Request ID search, cross-search
    ├── TimelineList.tsx       # (~250 lines) Trust log explorer list
    ├── DetailPanel.tsx        # (~200 lines) Summary, Metadata, Hash tabs
    └── ExportPanel.tsx        # (~150 lines) Date range, format, download
```

---

## 7. `veritas_os/tools/web_search.py` (1,306 lines) — HIGH

### Identified Responsibility Groups

| Group | Approx Lines | Description |
|-------|-------------:|-------------|
| SSRF & DNS Rebinding Defense | 160 | Hostname canonicalization, private host detection, DNS resolution, rebinding guard |
| Config & Credentials | 100 | Environment vars, API key resolution, allowlist parsing |
| Query Enhancement & Filtering | 100 | AGI detection, VERITAS anchor, query boosting, result blocking |
| Toxicity & Content Safety | 60 | Toxic result detection, Base64 payload inspection |
| HTTP & Retry Logic | 80 | Exponential backoff, retry status detection |
| Main Orchestrator | 400+ | `web_search()` entry point, result normalization |
| Safe Parameter Parsing | 90 | `_safe_int()`, `_safe_float()`, bounds validation |

### Recommended Split

```
tools/
├── web_search.py              # (~400 lines) Main orchestrator, result normalization
├── web_search_security.py     # (~160 lines) SSRF/DNS rebinding defense
├── web_search_config.py       # (~100 lines) Credentials, allowlist, safe parsing
├── web_search_filtering.py    # (~100 lines) AGI detection, query boosting, blocking
└── web_search_safety.py       # (~60 lines)  Toxicity detection, Base64 inspection
```

---

## 8. `veritas_os/core/pipeline.py` (1,223 lines) — MEDIUM

### Identified Responsibility Groups

| Group | Approx Lines | Description |
|-------|-------------:|-------------|
| Initialization & Imports | 100 | Module checks, persona loading, warning setup |
| Utilities & Helpers | 120 | Type conversions, value clipping, request param extraction |
| Persistence & Storage | 180 | Path resolution, decision loading, dataset/trust log fallbacks |
| Policy & Gate Logic | 100 | Gate prediction, value stats, alternative deduplication |
| Main Orchestration | 200+ | `run_decide_pipeline()` — delegates to stage modules |

### Recommended Split

```
pipeline/
├── __init__.py           # Re-exports
├── pipeline.py           # (~200 lines) Main run_decide_pipeline() orchestrator
├── persistence.py        # (~180 lines) Path resolution, decision loading, fallbacks
├── helpers.py            # (~120 lines) Type conversions, clipping, params
└── gate.py               # (~100 lines) Gate prediction, value stats, dedup
```

---

## Test Files Requiring Attention

Several test files also exceed reasonable size and should be organized:

| File | Lines | Note |
|------|------:|------|
| `tests/test_api_server_extra.py` | 1,886 | Should mirror server.py split |
| `tests/test_coverage_boost.py` | 1,380 | Consider splitting by feature |
| `tests/test_kernel_core_extra.py` | 1,217 | Split by kernel responsibility |
| `tests/test_api_pipeline.py` | 1,128 | Split by pipeline stage |
| `packages/types/src/index.test.ts` | 1,590 | Split by type domain |

---

## Recommended Execution Order

1. **`api/server.py`** — Highest line count, most diverse responsibilities, blocking parallel development
2. **`core/memory.py`** — Critical infrastructure with scattered concurrency concerns
3. **`core/fuji.py`** — Safety-critical code benefits most from isolated testing
4. **`core/eu_ai_act_compliance_module.py`** — Regulatory code should be clearly separated
5. **`frontend/app/audit/page.tsx`** — Standard React componentization
6. **`tools/web_search.py`** — Security-critical SSRF logic should be isolated
7. **`core/planner.py`** — JSON parsing dominates; straightforward extraction
8. **`core/pipeline.py`** — Already partially delegating to sub-modules
