# Frontend-Backend Consistency Review Report

**Date:** 2026-03-08
**Reviewer:** Claude (automated)
**Scope:** OpenAPI spec, Backend (Python/FastAPI), Frontend (Next.js/TypeScript), Shared Types

---

## Summary

Overall the frontend and backend are **well-aligned**. The shared types package (`@veritas/types`) faithfully mirrors the backend Pydantic schemas, and the BFF proxy route correctly translates paths. However, several inconsistencies and gaps were identified across 3 severity levels.

---

## Critical Issues (要対応)

### 1. OpenAPI spec `rsi_note` type mismatch

| Layer | Type |
|-------|------|
| **openapi.yaml** (L196) | `type: string` |
| **Backend** `schemas.py` (L461) | `Optional[Dict[str, Any]]` |
| **Frontend** `decision.ts` (L87) | `Record<string, unknown> \| null` |

**Impact:** OpenAPI spec says `rsi_note` is a string, but backend actually returns a dict/object. Any client code-generated from the OpenAPI spec will break when receiving the actual response.

**Fix:** Update `openapi.yaml` to `type: object` (nullable).

### 2. OpenAPI spec `DecideResponse` missing many fields

The OpenAPI `DecideResponse` schema (L152-196) is missing the following fields that both the backend and frontend expect:

| Missing field | Backend type | Frontend type |
|---------------|-------------|---------------|
| `version` | `str` | `string` |
| `options` | `List[Alt]` | `DecisionAlternative[]` |
| `decision_status` | `Literal[...]` | `DecisionStatus` |
| `rejection_reason` | `Optional[str]` | `string \| null` |
| `values` | `Optional[ValuesOut]` | `ValuesOut \| null` |
| `gate` | `Gate` | `GateOut` |
| `extras` | `Dict[str, Any]` | `Record<string, unknown>` |
| `meta` | `Dict[str, Any]` | `Record<string, unknown>` |
| `persona` | `Dict[str, Any]` | `Record<string, unknown>` |
| `plan` | `Optional[Dict]` | `Record<string, unknown> \| null` |
| `planner` | `Optional[Dict]` | `Record<string, unknown> \| null` |
| `reason` | `Optional[Any]` | `unknown` |
| `evo` | `Optional[Dict]` | `Record<string, unknown> \| null` |
| `memory_citations` | `List[Any]` | `unknown[]` |
| `memory_used_count` | `int` | `number` |
| `ai_disclosure` | `str` | `string` (optional) |
| `regulation_notice` | `str` | `string` (optional) |
| `affected_parties_notice` | `Optional[Dict]` | `Record<string, unknown> \| null` |

**Impact:** OpenAPI spec is significantly behind the actual API contract. External consumers relying on openapi.yaml will not be aware of these fields.

**Fix:** Update `openapi.yaml` DecideResponse schema to include all fields.

### 3. OpenAPI `DecideRequest` schema inconsistency with actual backend

| Field | openapi.yaml | Backend (schemas.py) |
|-------|-------------|---------------------|
| `context` | **required**, `$ref: Context` | **optional** (default `{}`), accepts any dict |
| `query` | not listed | accepted (default `""`) |
| `min_evidence` | default `2` | default `1` |
| `stream` | listed as `boolean` | not in DecideRequest |
| `alternatives` | not listed | accepted |
| `memory_auto_put` | not listed | accepted (default `true`) |
| `persona_evolve` | not listed | accepted (default `true`) |

**Impact:** OpenAPI spec mandates `context` as required with a structured schema, but the backend accepts `query` + empty `context` (which is exactly what the frontend sends). The `stream` field in the spec doesn't exist in the backend. The default value of `min_evidence` differs.

**Fix:** Align openapi.yaml with actual DecideRequest schema.

---

## Medium Issues (推奨対応)

### 4. OpenAPI spec missing backend endpoints

The following endpoints exist in the backend but are absent from `openapi.yaml`:

| Endpoint | Purpose |
|----------|---------|
| `GET /v1/events` | SSE event stream |
| `GET /v1/trust/logs` | Paginated trust log listing |
| `POST /v1/trust/feedback` | Human feedback recording |
| `GET /v1/trustlog/verify` | Trust log chain verification |
| `GET /v1/trustlog/export` | Trust log export |
| `GET /v1/governance/value-drift` | Value drift metrics |
| `GET /v1/governance/policy` | Governance policy read |
| `PUT /v1/governance/policy` | Governance policy update |
| `GET /v1/compliance/config` | Compliance config read |
| `PUT /v1/compliance/config` | Compliance config update |
| `GET /v1/compliance/deployment-readiness` | Deployment readiness check |
| `POST /v1/system/halt` | Emergency system halt |
| `POST /v1/system/resume` | System resume |
| `GET /v1/system/halt-status` | Halt status check |
| `GET /v1/metrics` | System metrics |
| `GET /v1/report/eu_ai_act/{decision_id}` | EU AI Act report |
| `GET /v1/report/governance` | Governance report |
| `POST /v1/memory/search` | Memory search |
| `POST /v1/memory/erase` | Memory erasure |
| `POST /v1/decision/replay/{decision_id}` | Decision replay (v2) |
| `WS /v1/ws/trustlog` | WebSocket trust log stream |

**Impact:** External API consumers and tooling (Swagger UI, code generators) see an incomplete API surface.

### 5. OpenAPI `EvidenceItem` has `hash` field not in backend

`openapi.yaml` (L83) defines a `hash` field on `EvidenceItem` that does not exist in the backend `EvidenceItem` schema or the frontend `EvidenceItem` interface. The backend has `title` instead, which is missing from the OpenAPI spec.

| Field | openapi.yaml | Backend | Frontend |
|-------|-------------|---------|----------|
| `hash` | present | absent | absent |
| `title` | absent | `Optional[str]` | `string \| null` |

### 6. OpenAPI `TrustLog.fuji` required vs optional mismatch

| Layer | Constraint |
|-------|-----------|
| **openapi.yaml** (L125) | `fuji` is listed in `required` |
| **Backend** `schemas.py` (L228) | `fuji: Optional[Dict[str, Any]] = None` |
| **Frontend** `decision.ts` (L64) | `fuji?: Record<string, unknown> \| null` |

The backend and frontend both treat `fuji` as optional, but the OpenAPI spec marks it as required. This could cause validation failures for clients using strict OpenAPI validation.

### 7. BFF route policy missing some backend endpoints

The BFF proxy (`route-auth.ts`) only defines policies for 9 routes. Backend endpoints like `/v1/metrics`, `/v1/system/halt`, `/v1/report/*`, `/v1/memory/*`, `/v1/fuji/validate` have no route policies, meaning the BFF proxy will return 401/403 for requests to these paths even though they exist on the backend.

This may be intentional (these endpoints might be intended for direct backend access only), but it should be documented.

---

## Low Issues (参考)

### 8. Frontend `ai_disclosure` and `regulation_notice` marked optional

In `decision.ts` (L98-100), `ai_disclosure` and `regulation_notice` are marked with `?` (optional), but the backend always includes them with default values. The `isDecideResponse` validator does not check these fields. Not a runtime issue, but the TypeScript types could be more precise.

### 9. Risk page uses synthetic data only

The risk page (`app/risk/page.tsx`) generates all data client-side with synthetic random values. It does not call any backend API. This is fine for a demo/visualization, but should be noted - if real risk data is expected, an API integration is needed.

### 10. Frontend `DecideResponse.coercion_events` not in TypeScript types

The backend includes `coercion_events` in `DecideResponse` (excluded from JSON via `exclude=True`), so it's correctly invisible to the frontend. The `[key: string]: unknown` index signature on the frontend type would catch it if it ever leaked through. No action needed but worth noting.

### 11. `Gate` vs `GateOut` naming

The backend Pydantic model is called `Gate` (schemas.py L419) while the frontend TypeScript interface is called `GateOut` (decision.ts L47). Both have identical fields. Minor naming inconsistency but not a functional issue.

### 12. `Option` schema in openapi.yaml lacks `score` and `score_raw`

The OpenAPI `Option` schema (L61-69) only has `id`, `title`, `description`. The backend `Option`/`Alt` models include `score`, `score_raw`, `world`, `meta`. The frontend `DecisionAlternative` also expects `score`, `score_raw`, `world`, `meta`.

---

## Consistency Matrix

| Area | Backend ↔ Frontend | Backend ↔ OpenAPI | Frontend ↔ OpenAPI |
|------|:------------------:|:-----------------:|:------------------:|
| `/v1/decide` URL path | OK | OK | OK |
| DecideRequest fields | OK | MISMATCH | MISMATCH |
| DecideResponse fields | OK | MISMATCH | MISMATCH |
| DecisionStatus enum values | OK | OK | OK |
| EvidenceItem fields | OK | MISMATCH | MISMATCH |
| TrustLog fields | OK | MISMATCH (required) | MISMATCH |
| Gate/GateOut fields | OK | N/A (missing) | N/A |
| Auth mechanism | OK (BFF proxy) | OK | N/A |
| Error handling | OK | N/A | N/A |
| SSE events | OK | N/A (missing) | N/A |

---

## Recommendations

1. **Priority 1:** Update `openapi.yaml` to match the actual backend schemas - this is the primary source of inconsistency. The frontend and backend are well-synchronized with each other; the OpenAPI spec has fallen behind.

2. **Priority 2:** Document which backend endpoints are intentionally excluded from the BFF proxy and why.

3. **Priority 3:** Consider generating TypeScript types from the OpenAPI spec (or vice versa) to prevent future drift.

---

## Files Reviewed

| File | Role |
|------|------|
| `openapi.yaml` | API contract specification |
| `veritas_os/api/schemas.py` | Backend Pydantic models |
| `veritas_os/api/constants.py` | Backend constants |
| `veritas_os/api/server.py` | Backend FastAPI endpoints |
| `packages/types/src/decision.ts` | Shared TypeScript types |
| `packages/types/src/index.ts` | Shared type validators |
| `frontend/app/api/veritas/[...path]/route.ts` | BFF proxy |
| `frontend/app/api/veritas/[...path]/route-auth.ts` | BFF auth policies |
| `frontend/features/console/api/useDecide.ts` | Frontend API client |
| `frontend/app/governance/page.tsx` | Governance page |
| `frontend/app/audit/page.tsx` | Audit page |
| `frontend/app/risk/page.tsx` | Risk page |
| `frontend/components/live-event-stream.tsx` | SSE client |
| `frontend/middleware.ts` | Next.js middleware |
