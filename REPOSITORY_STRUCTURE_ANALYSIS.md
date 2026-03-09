# VERITAS OS - Repository Structure & API Contract Analysis

## 1. TOP-LEVEL DIRECTORY STRUCTURE (2 levels)

```
/home/runner/work/veritas_os/veritas_os/
├── frontend/                 # Next.js frontend application
├── packages/
│   ├── design-system/       # Shared UI components
│   └── types/               # Shared TypeScript types
├── veritas_os/              # Backend Python package
│   ├── api/                 # FastAPI application
│   │   ├── server.py        # API routes (120KB)
│   │   ├── schemas.py       # Pydantic models (32KB)
│   │   ├── constants.py
│   │   ├── dashboard_server.py
│   │   ├── evolver.py
│   │   ├── governance.py
│   │   └── pipeline_orchestrator.py
│   ├── audit/               # Audit/logging modules
│   ├── compliance/          # Compliance features
│   ├── prompts/             # AI prompts
│   ├── security/            # Security modules
│   ├── templates/           # Response templates
│   └── tests/               # Test suite
├── cli/                     # Command-line interface
├── config/                  # Configuration files
├── docs/                    # Documentation
├── policies/                # Policy examples
├── sdk/                     # SDKs
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── pnpm-workspace.yaml
├── package.json
└── README.md
```

---

## 2. BACKEND PYDANTIC MODELS (veritas_os/api/schemas.py)

### All Pydantic Classes (21 total):

1. **Context** - User query context and metadata
2. **Option** - Legacy option model (deprecated, use AltItem)
3. **ValuesOut** - Value scoring output
4. **EvidenceItem** - Evidence source and confidence
5. **CritiqueItem** - Critique with severity levels
6. **DebateView** - Debate stance and arguments
7. **FujiDecision** - Safety/trust gate decision
8. **TrustLog** - Audit trail entry
9. **AltItem** - Alternative option (preferred over Option)
10. **DecideRequest** - Main API request model
11. **Alt** - Alternative in response
12. **Gate** - Risk gate for decisions
13. **DecideResponse** - Main API response model
14. **EvoTips** - Evolution/persona tips
15. **PersonaState** - AI persona state
16. **ChatRequest** - Chat message request
17. **MemoryPutRequest** - Store memory entry
18. **MemoryGetRequest** - Retrieve memory entry
19. **MemorySearchRequest** - Search memory
20. **MemoryEraseRequest** - Delete memory entry
21. **TrustFeedbackRequest** - Feedback on decisions

### Enum Types (Literal) in Backend:

| Field | Values | Used In |
|-------|--------|---------|
| `time_horizon` | "short", "mid", "long" | Context |
| `response_style` | "logic", "emotional", "business", "expert", "casual" | Context |
| `severity` | "low", "med", "high" | CritiqueItem |
| `status` (FujiDecision) | "allow", "modify", "rejected", "block", "abstain" | FujiDecision |
| `decision_status` | "allow", "modify", "rejected", "block", "abstain" | Gate, DecideResponse |

---

## 3. FRONTEND TYPESCRIPT TYPES

### Main Type Definition Files:

#### `/packages/types/src/decision.ts`
**Exported Types:**
- `DecisionStatus` - "allow" \| "modify" \| "rejected" \| "block" \| "abstain"
- `DecideResponseMeta` - ok, error, request_id, version
- `DecisionAlternative` - id, title, description, score, score_raw, world, meta
- `ValuesOut` - scores, total, top_factors, rationale, ema
- `EvidenceItem` - source, uri, title, snippet, confidence
- `GateOut` - risk, telos_score, bias, decision_status, reason, modifications
- `TrustLog` - request_id, created_at, sources, critics, checks, approver, fuji, sha256_prev
- `DecideResponse` - Complete response type with all fields
- Functions: `isDecideResponse()`, `isDecisionStatus()`

#### `/packages/types/src/index.ts`
**Exported Types:**
- `HealthResponse` - ok, uptime, checks
- `ApiError` - code, message
- Re-exports from decision.ts

#### `/frontend/components/dashboard-types.ts`
**Types for Dashboard UI:**
- `HealthBand` - "healthy" \| "degraded" \| "critical"
- `CriticalRailMetric`
- `OpsPriorityItem`
- `GlobalHealthSummaryModel`

#### `/frontend/app/audit/audit-types.ts`
**Audit-specific Types:**
- `VerificationStatus` - "verified" \| "broken" \| "missing" \| "orphan"
- `ChainResult` - Hash chain verification result
- `ChainLink` - Previous/current/next trust logs
- `AuditSummary` - Total counts and policy versions
- `TimelineRow` - Display row for audit timeline
- `DetailTab` - "summary" \| "metadata" \| "hash" \| "related" \| "raw"
- `SearchField` - "all" \| "decision_id" \| "request_id" \| "replay_id" \| "policy_version"
- `ExportFormat` - "json" \| "pdf"
- `RedactionMode` - "full" \| "redacted" \| "metadata-only"

#### `/frontend/lib/api-validators.ts`
**Types for Governance & Validation:**
- `FujiRules` - Boolean flags for safety rules
- `RiskThresholds` - allow_upper, warn_upper, human_review_upper, deny_upper
- `AutoStop` - enabled, max_risk_score, max_consecutive_rejects, max_requests_per_minute
- `LogRetention` - retention_days, audit_level, include_fields, redact_before_log, max_log_size
- `GovernancePolicy` - version, fuji_rules, risk_thresholds, auto_stop, log_retention, updated_at, updated_by
- `GovernancePolicyResponse`
- `GovernanceValidationIssue` - category, path, message
- `TrustLogItem` - Trust log database record
- `TrustLogsResponse` - Paginated trust logs
- `RequestLogResponse` - Request-scoped logs

---

## 4. API ENDPOINT ROUTES (veritas_os/api/server.py)

### Health & Status Endpoints
| Method | Route | Handler | Auth | Notes |
|--------|-------|---------|------|-------|
| GET | `/` | root() | None | Root health check |
| GET | `/health`, `/v1/health` | health() | None | Health status |
| GET | `/status`, `/v1/status`, `/api/status` | status() | None | System status |

### Decision Endpoints
| Method | Route | Handler | Auth | Notes |
|--------|-------|---------|------|-------|
| POST | `/v1/decide` | decide() | API Key | Main decision endpoint |
| POST | `/v1/replay/{decision_id}` | replay() | API Key | Replay decision |
| POST | `/v1/decision/replay/{decision_id}` | decision_replay() | API Key | Alternative replay endpoint |
| POST | `/v1/fuji/validate` | fuji_validate() | API Key | Validate safety gates |

### Memory Endpoints
| Method | Route | Handler | Auth | Notes |
|--------|-------|---------|------|-------|
| POST | `/v1/memory/put` | memory_put() | API Key + Rate Limit | Store memory |
| POST | `/v1/memory/search` | memory_search() | API Key + Rate Limit | Search memory |
| POST | `/v1/memory/get` | memory_get() | API Key + Rate Limit | Retrieve memory |
| POST | `/v1/memory/erase` | memory_erase() | API Key + Rate Limit | Delete memory |

### Metrics & Events Endpoints
| Method | Route | Handler | Auth | Notes |
|--------|-------|---------|------|-------|
| GET | `/v1/metrics` | metrics() | API Key | Decision metrics |
| GET | `/v1/events` | events() | API Key or Query | Server-sent events (SSE) |

### Compliance Endpoints
| Method | Route | Handler | Auth | Notes |
|--------|-------|---------|------|-------|
| GET | `/v1/compliance/config` | get_compliance_config() | API Key | Get compliance config |
| PUT | `/v1/compliance/config` | put_compliance_config() | API Key | Update compliance config |
| GET | `/v1/compliance/deployment-readiness` | compliance_deployment_readiness() | API Key | Deployment readiness check |

### Trust & Audit Endpoints
| Method | Route | Handler | Auth | Notes |
|--------|-------|---------|------|-------|
| GET | `/v1/trust/logs` | trust_logs() | API Key + Rate Limit | Get trust logs (paginated) |
| GET | `/v1/trust/{request_id}` | trust_log_by_request() | API Key + Rate Limit | Get logs for request |
| POST | `/v1/trust/feedback` | trust_feedback() | API Key + Rate Limit | Submit feedback |
| GET | `/v1/trust/stats` | trust_log_stats() | API Key | Trust statistics |
| GET | `/v1/trustlog/verify` | trustlog_verify() | API Key + Rate Limit | Verify hash chain |
| GET | `/v1/trustlog/export` | trustlog_export() | API Key + Rate Limit | Export trust logs |

### Governance Endpoints
| Method | Route | Handler | Auth | Notes |
|--------|-------|---------|------|-------|
| GET | `/v1/governance/value-drift` | governance_value_drift() | API Key | Monitor value drift |
| GET | `/v1/governance/policy` | governance_get() | API Key | Get current policy |
| PUT | `/v1/governance/policy` | governance_put() | API Key | Update policy |
| GET | `/v1/governance/policy/history` | governance_policy_history() | API Key | Policy change history |

### Reporting Endpoints
| Method | Route | Handler | Auth | Notes |
|--------|-------|---------|------|-------|
| GET | `/v1/report/eu_ai_act/{decision_id}` | report_eu_ai_act() | API Key | EU AI Act compliance report |
| GET | `/v1/report/governance` | report_governance() | API Key | Governance report (date range) |

### System Control Endpoints
| Method | Route | Handler | Auth | Notes |
|--------|-------|---------|------|-------|
| POST | `/v1/system/halt` | system_halt() | API Key | Halt system |
| POST | `/v1/system/resume` | system_resume() | API Key | Resume system |
| GET | `/v1/system/halt-status` | system_halt_status() | API Key | Check halt status |

---

## 5. FRONTEND API CLIENT CODE

### Main Client File: `/frontend/lib/api-client.ts`

**Function: `veritasFetch()`**
```typescript
export async function veritasFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS (20_000),
): Promise<Response>
```

**Key Features:**
- Automatic credential handling via httpOnly session cookie (`__veritas_bff`)
- AbortController-based timeout (default 20 seconds)
- Credentials set to "same-origin" for automatic cookie inclusion
- Used for all `/api/veritas/*` endpoints from browser

**Authentication Flow:**
1. Next.js middleware sets `__veritas_bff` httpOnly cookie on page load
2. Browser automatically includes cookie in same-origin requests
3. `veritasFetch()` wrapper ensures consistent timeout and credential handling
4. No client-side token management needed

---

## 6. ENUM VALUES COMPARISON - BACKEND VS FRONTEND

### DecisionStatus / decision_status
**Backend (schemas.py):**
```python
Literal["allow", "modify", "rejected", "block", "abstain"]
```
**Frontend (packages/types/src/decision.ts):**
```typescript
type DecisionStatus = "allow" | "modify" | "rejected" | "block" | "abstain"
```
✅ **MATCH** - Identical enum values

### Severity
**Backend (schemas.py):**
```python
Literal["low", "med", "high"]
```
**Frontend:**
- Not explicitly defined as a type in decision.ts
- Used in api-validators.ts for governance policy
⚠️ **POTENTIAL ISSUE** - Severity type not exported from decision.ts

### Health/Status
**Backend (server.py):**
- Returns dict with "ok", "uptime", "checks"
**Frontend (packages/types/src/index.ts):**
```typescript
interface HealthResponse {
  ok: boolean;
  uptime: number;
  checks: { pipeline: string; memory: string }
}
```
✅ **MATCH** - Structure aligned

### Time Horizon
**Backend (schemas.py):**
```python
Literal["short", "mid", "long"]
```
**Frontend:**
- Not explicitly defined as a type
⚠️ **MISSING** - Time horizon type not in frontend types

### Response Style
**Backend (schemas.py):**
```python
Literal["logic", "emotional", "business", "expert", "casual"]
```
**Frontend:**
- Not defined in type files
⚠️ **MISSING** - Response style type not in frontend

### Audit Types
**Backend:**
- No explicit audit type definitions in schemas.py
**Frontend (audit-types.ts):**
```typescript
type VerificationStatus = "verified" | "broken" | "missing" | "orphan"
type DetailTab = "summary" | "metadata" | "hash" | "related" | "raw"
type SearchField = "all" | "decision_id" | "request_id" | "replay_id" | "policy_version"
type ExportFormat = "json" | "pdf"
type RedactionMode = "full" | "redacted" | "metadata-only"
```
⚠️ **NO BACKEND COUNTERPART** - These are UI-specific types with no schema definition

### Governance Types
**Backend (api/governance.py, implicit):**
- fuji_rules, risk_thresholds, auto_stop, log_retention
**Frontend (lib/api-validators.ts):**
```typescript
interface FujiRules { pii_check, self_harm_block, illicit_block, ... }
interface RiskThresholds { allow_upper, warn_upper, human_review_upper, deny_upper }
interface AutoStop { enabled, max_risk_score, max_consecutive_rejects, max_requests_per_minute }
interface LogRetention { retention_days, audit_level, include_fields, redact_before_log, max_log_size }
```
⚠️ **INCONSISTENCY** - No Pydantic model for GovernancePolicy in schemas.py

---

## KEY FINDINGS & INCONSISTENCIES

### ✅ WELL-ALIGNED
1. **DecideResponse Structure** - Frontend types match backend Pydantic model closely
2. **DecisionStatus Enum** - Perfectly synchronized (5 values)
3. **Evidence/Critique/Debate** - Backend and frontend types compatible
4. **Trust Log Model** - TrustLog in schemas.py matches TrustLog interface in decision.ts

### ⚠️ ISSUES TO ADDRESS

1. **Missing Type Exports from Backend**
   - `Severity` ("low", "med", "high") - Only in CritiqueItem, not exported
   - `TimeHorizon` ("short", "mid", "long") - Only in Context, not exported
   - `ResponseStyle` - Only in Context, not exported

2. **No Pydantic Model for Governance Policy**
   - Frontend expects `GovernancePolicy` with sub-interfaces (FujiRules, RiskThresholds, etc.)
   - Backend has these defined but NOT as a Pydantic model in schemas.py
   - `/v1/governance/policy` endpoint accepts/returns `dict` instead of typed model

3. **Missing Audit Types in Backend**
   - VerificationStatus, DetailTab, SearchField, ExportFormat, RedactionMode
   - These are UI-only types (correct), but should be documented as such

4. **API Response Validation**
   - Frontend has runtime validators (e.g., `isDecideResponse()`, `isTrustLogsResponse()`)
   - Backend Pydantic models provide some validation, but not all response shapes are fully validated

5. **Memory API Types**
   - MemoryPutRequest, MemoryGetRequest, MemorySearchRequest in schemas.py
   - No corresponding TypeScript interfaces in frontend type files
   - Frontend would need to validate memory responses manually

### 🔧 RECOMMENDATIONS

1. **Extract Literal Types to Constants**
   - Create `veritas_os/api/enums.py` with exported Enum or Literal type aliases
   - Export from schemas.py for documentation
   - Add corresponding TypeScript types to `packages/types/src/enums.ts`

2. **Create GovernancePolicy Pydantic Model**
   - Move governance validation logic into a proper Pydantic model
   - Ensure `/v1/governance/policy` endpoint uses typed model
   - Generate matching TypeScript interface from model

3. **Standardize Memory API Types**
   - Add TypeScript interfaces for MemoryPutRequest, MemoryGetRequest, MemorySearchRequest
   - Add response validators in api-validators.ts

4. **Document Response Schemas**
   - Update OpenAPI spec to reflect all response models
   - Generate TypeScript types from OpenAPI schema (consider using openapi-generator-ts)

5. **Create Type Sync Test**
   - Add integration test comparing backend Pydantic fields with frontend TypeScript fields
   - Could use a custom pytest plugin + TypeScript type checker

___BEGIN___COMMAND_DONE_MARKER___0
