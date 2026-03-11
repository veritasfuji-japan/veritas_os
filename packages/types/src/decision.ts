/**
 * /v1/decide response types aligned to backend runtime payloads.
 *
 * Source of truth:
 * - veritas_os/api/schemas.py (DecideResponse, TrustLog, Gate, CritiqueItem, DebateView,
 *   FujiDecision, PersonaState, EvoTips, ChatRequest)
 * - veritas_os/core/pipeline.py (response assembly)
 */

export type DecisionStatus = "allow" | "modify" | "rejected" | "block" | "abstain";

/** Severity level used in CritiqueItem. */
export type CritiqueSeverity = "low" | "med" | "high";

/**
 * Valid memory kinds for /v1/memory/put.
 *
 * Source of truth: veritas_os/api/constants.py — VALID_MEMORY_KINDS
 */
export type MemoryKind = "semantic" | "episodic" | "skills" | "doc" | "plan";

/**
 * Time horizon for context / decision scope.
 *
 * Source of truth: veritas_os/api/schemas.py — Context.time_horizon
 */
export type TimeHorizon = "short" | "mid" | "long";

/**
 * Response style hint for persona / tone selection.
 *
 * Source of truth: veritas_os/api/schemas.py — Context.response_style
 */
export type ResponseStyle = "logic" | "emotional" | "business" | "expert" | "casual";

/**
 * Retention class for memory lifecycle management.
 *
 * Source of truth: veritas_os/api/schemas.py — ALLOWED_RETENTION_CLASSES
 */
export type RetentionClass = "short" | "standard" | "long" | "regulated";

/**
 * Stage health status consumed by the pipeline visualizer.
 *
 * Source of truth: veritas_os/api/schemas.py — StageMetrics.health
 */
export type StageHealth = "ok" | "warning" | "failed" | "unknown";

/**
 * User context information passed alongside a decision request.
 *
 * Source of truth: veritas_os/api/schemas.py — Context
 */
export interface Context {
  user_id?: string;
  session_id?: string;
  query?: string;
  goals?: string[];
  constraints?: string[];
  tools_allowed?: string[];
  time_horizon?: TimeHorizon;
  preferences?: string[];
  response_style?: ResponseStyle;
  telos_weights?: Record<string, number>;
  affect_hint?: Record<string, string>;
  [key: string]: unknown;
}

/**
 * Input candidate option for /v1/decide requests.
 *
 * Source of truth: veritas_os/api/schemas.py — Option
 */
export interface Option {
  id?: string;
  title?: string;
  /** @deprecated Alias for title (backward-compatible). */
  text?: string;
  description?: string;
  score?: number;
  score_raw?: number | null;
  [key: string]: unknown;
}

/**
 * A single critique entry from the critique pipeline stage.
 *
 * Source of truth: veritas_os/api/schemas.py — CritiqueItem
 */
export interface CritiqueItem {
  issue: string;
  severity: CritiqueSeverity;
  fix?: string | null;
  [key: string]: unknown;
}

/**
 * A single stance from the debate pipeline stage.
 *
 * Source of truth: veritas_os/api/schemas.py — DebateView
 */
export interface DebateView {
  stance: string;
  argument: string;
  score: number;
  [key: string]: unknown;
}

/**
 * FUJI safety-gate decision result.
 *
 * Source of truth: veritas_os/api/schemas.py — FujiDecision
 */
export interface FujiDecision {
  status: DecisionStatus;
  reasons: string[];
  violations: string[];
  /** Policy rule or keyword that triggered the FUJI gate. */
  rule_hit?: string | null;
  /** Qualitative risk severity level ("low" | "medium" | "high" | "critical"). */
  severity?: string | null;
  /** Suggested remediation action for operators when gate fires. */
  remediation_hint?: string | null;
  /** Short excerpt from the input that triggered the policy rule. */
  risky_text_fragment?: string | null;
  [key: string]: unknown;
}

export interface DecideResponseMeta {
  ok: boolean;
  error: string | null;
  request_id: string;
  version: string;
}

export interface DecisionAlternative {
  id: string;
  title: string;
  description: string;
  score: number;
  score_raw?: number | null;
  world?: Record<string, unknown> | null;
  meta?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export interface ValuesOut {
  scores: Record<string, number>;
  total: number;
  top_factors: string[];
  rationale: string;
  ema?: number | null;
  [key: string]: unknown;
}

export interface EvidenceItem {
  source: string;
  uri?: string | null;
  title?: string | null;
  snippet: string;
  confidence: number;
  [key: string]: unknown;
}

export interface GateOut {
  risk: number;
  telos_score: number;
  bias?: number | null;
  decision_status: DecisionStatus;
  reason?: string | null;
  modifications: Array<string | Record<string, unknown>>;
  /** Policy rule or keyword that triggered the gate. */
  rule_hit?: string | null;
  /** Qualitative risk severity level ("low" | "medium" | "high" | "critical"). */
  severity?: string | null;
  /** Suggested remediation action for operators when gate fires. */
  remediation_hint?: string | null;
  /** Short excerpt from the input that triggered the policy rule. */
  risky_text_fragment?: string | null;
  [key: string]: unknown;
}

export interface TrustLog {
  request_id: string;
  created_at: string;
  sources: string[];
  critics: string[];
  checks: string[];
  approver: string;
  fuji?: FujiDecision | Record<string, unknown> | null;
  /** Hash-chain: SHA-256 of this entry, computed by trust_log.py append_trust_log. */
  sha256?: string | null;
  sha256_prev?: string | null;
  /** Pipeline-provided fields (optional — present in audit entries from pipeline.py) */
  query?: string | null;
  gate_status?: string | null;
  gate_risk?: number | null;
  [key: string]: unknown;
}

/**
 * Persona state maintained by the PersonaOS module.
 *
 * Source of truth: veritas_os/api/schemas.py — PersonaState
 */
export interface PersonaState {
  name: string;
  style: string;
  tone: string;
  principles: string[];
  last_updated?: string | null;
  [key: string]: unknown;
}

/**
 * Evolution tips returned by the EvoOS module.
 *
 * Source of truth: veritas_os/api/schemas.py — EvoTips
 */
export interface EvoTips {
  insights: Record<string, unknown>;
  actions: string[];
  next_prompts: string[];
  notes: string[];
  [key: string]: unknown;
}

/**
 * Chat request body for the SSE streaming endpoint.
 *
 * Source of truth: veritas_os/api/schemas.py — ChatRequest
 */
export interface ChatRequest {
  message: string;
  session_id?: string | null;
  memory_auto_put?: boolean;
  persona_evolve?: boolean;
  [key: string]: unknown;
}

/**
 * Per-stage execution metrics written into DecideResponse.extras["stage_metrics"].
 *
 * Each pipeline stage (Input, Evidence, Critique, Debate, Plan, Value, FUJI,
 * TrustLog) may publish a StageMetrics entry keyed by its lowercase name.
 *
 * Source of truth: veritas_os/api/schemas.py — StageMetrics
 */
export interface StageMetrics {
  /** Stage wall-clock execution time in milliseconds. */
  latency_ms?: number | null;
  /** Stage health status consumed by the pipeline visualizer. */
  health: StageHealth;
  /** One-line human-readable description of stage outcome. */
  summary?: string | null;
  /** Extended diagnostic text for the stage (shown in expanded UI view). */
  detail?: string | null;
  /** Fallback for detail when detail is absent (e.g. gate rejection reason). */
  reason?: string | null;
  [key: string]: unknown;
}

export interface DecideResponse extends DecideResponseMeta {
  chosen: Record<string, unknown>;
  alternatives: DecisionAlternative[];
  options: DecisionAlternative[];
  decision_status: DecisionStatus;
  rejection_reason: string | null;

  values: ValuesOut | null;
  telos_score: number;
  fuji: Record<string, unknown>;
  gate: GateOut;

  evidence: EvidenceItem[];
  /**
   * Backend declares List[Any] for resilience; items are CritiqueItem when
   * the critique stage succeeds, but may be arbitrary records on error paths.
   * Use isCritiqueItem() to narrow before accessing typed fields.
   */
  critique: Array<CritiqueItem | Record<string, unknown>>;
  /**
   * Backend declares List[Any] for resilience; items are DebateView when
   * the debate stage succeeds, but may be arbitrary records on error paths.
   * Use isDebateView() to narrow before accessing typed fields.
   */
  debate: Array<DebateView | Record<string, unknown>>;

  extras: Record<string, unknown>;
  reason: unknown;
  rsi_note: Record<string, unknown> | null;
  evo: EvoTips | Record<string, unknown> | null;
  meta: Record<string, unknown>;
  plan: Record<string, unknown> | null;
  planner: Record<string, unknown> | null;
  persona: PersonaState | Record<string, unknown>;
  memory_citations: unknown[];
  memory_used_count: number;
  trust_log: TrustLog | Record<string, unknown> | null;

  /** Art. 50(1) — mandatory AI-generated content disclosure. Always present. */
  ai_disclosure: string;
  /** Art. 50 — regulation reference notice. Always present. */
  regulation_notice: string;
  /** Art. 13 — notification record for individuals affected by high-risk decisions. */
  affected_parties_notice?: Record<string, unknown> | null;

  /** Original user query text, attached by pipeline for audit and replay. */
  query?: string | null;
  /** Dynamic pipeline steps resolved by the orchestrator (EU AI Act compliance). */
  pipeline_steps?: string[] | null;
  /** Snapshot for deterministic replay of this decision. */
  deterministic_replay?: Record<string, unknown> | null;

  [key: string]: unknown;
}

/**
 * Runtime check for `/v1/decide` payloads.
 *
 * This is intentionally lightweight and verifies only required top-level fields
 * needed by clients before reading nested data.
 */
export function isDecideResponse(value: unknown): value is DecideResponse {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.ok === "boolean" &&
    (typeof value.error === "string" || value.error === null) &&
    typeof value.request_id === "string" &&
    typeof value.version === "string" &&
    isRecord(value.chosen) &&
    Array.isArray(value.alternatives) &&
    Array.isArray(value.options) &&
    isDecisionStatus(value.decision_status) &&
    (typeof value.rejection_reason === "string" || value.rejection_reason === null) &&
    (value.values === null || isRecord(value.values)) &&
    typeof value.telos_score === "number" &&
    isRecord(value.fuji) &&
    isRecord(value.gate) &&
    Array.isArray(value.evidence) &&
    Array.isArray(value.critique) &&
    Array.isArray(value.debate) &&
    isRecord(value.extras) &&
    isRecord(value.meta) &&
    (value.rsi_note === null || value.rsi_note === undefined || isRecord(value.rsi_note)) &&
    (value.evo === null || value.evo === undefined || isRecord(value.evo)) &&
    (value.plan === null || value.plan === undefined || isRecord(value.plan)) &&
    (value.planner === null || value.planner === undefined || isRecord(value.planner)) &&
    isRecord(value.persona) &&
    Array.isArray(value.memory_citations) &&
    typeof value.memory_used_count === "number" &&
    (value.trust_log === null || isRecord(value.trust_log)) &&
    typeof value.ai_disclosure === "string" &&
    typeof value.regulation_notice === "string" &&
    (value.affected_parties_notice === null || value.affected_parties_notice === undefined || isRecord(value.affected_parties_notice)) &&
    (value.query === null || value.query === undefined || typeof value.query === "string") &&
    (value.pipeline_steps === null || value.pipeline_steps === undefined || Array.isArray(value.pipeline_steps)) &&
    (value.deterministic_replay === null || value.deterministic_replay === undefined || isRecord(value.deterministic_replay))
  );
}

function isDecisionStatus(value: unknown): value is DecisionStatus {
  return value === "allow" || value === "modify" || value === "rejected" || value === "block" || value === "abstain";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/**
 * Runtime type guard for PersonaState payloads.
 *
 * Checks required fields: name, style, tone, principles.
 */
export function isPersonaState(value: unknown): value is PersonaState {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.name === "string" &&
    typeof value.style === "string" &&
    typeof value.tone === "string" &&
    Array.isArray(value.principles) &&
    value.principles.every((p: unknown) => typeof p === "string") &&
    (value.last_updated === undefined || value.last_updated === null || typeof value.last_updated === "string")
  );
}

/**
 * Runtime type guard for CritiqueItem payloads.
 *
 * Checks required fields: issue, severity (must be "low" | "med" | "high").
 * Optional: fix (string | null).
 */
export function isCritiqueItem(value: unknown): value is CritiqueItem {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.issue === "string" &&
    (value.severity === "low" || value.severity === "med" || value.severity === "high") &&
    (value.fix === undefined || value.fix === null || typeof value.fix === "string")
  );
}

/**
 * Runtime type guard for DebateView payloads.
 *
 * Checks required fields: stance, argument, score.
 */
export function isDebateView(value: unknown): value is DebateView {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.stance === "string" &&
    typeof value.argument === "string" &&
    typeof value.score === "number"
  );
}

/**
 * Runtime type guard for EvidenceItem payloads.
 *
 * Checks required fields: source, snippet, confidence.
 * Optional: uri (string | null), title (string | null).
 */
export function isEvidenceItem(value: unknown): value is EvidenceItem {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.source === "string" &&
    typeof value.snippet === "string" &&
    typeof value.confidence === "number" &&
    (value.uri === undefined || value.uri === null || typeof value.uri === "string") &&
    (value.title === undefined || value.title === null || typeof value.title === "string")
  );
}

/**
 * Runtime type guard for FujiDecision payloads.
 *
 * Checks required field: status (must be a valid DecisionStatus).
 * Checks required arrays: reasons, violations.
 */
export function isFujiDecision(value: unknown): value is FujiDecision {
  if (!isRecord(value)) {
    return false;
  }

  return (
    isDecisionStatus(value.status) &&
    Array.isArray(value.reasons) &&
    value.reasons.every((r: unknown) => typeof r === "string") &&
    Array.isArray(value.violations) &&
    value.violations.every((v: unknown) => typeof v === "string")
  );
}

/**
 * Runtime type guard for DecisionAlternative (Alt) payloads.
 *
 * Checks required fields: id, title, description, score.
 * Optional: score_raw (number | null), world (object | null), meta (object | null).
 */
export function isDecisionAlternative(value: unknown): value is DecisionAlternative {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.id === "string" &&
    typeof value.title === "string" &&
    typeof value.description === "string" &&
    typeof value.score === "number" &&
    (value.score_raw === undefined || value.score_raw === null || typeof value.score_raw === "number") &&
    (value.world === undefined || value.world === null || isRecord(value.world)) &&
    (value.meta === undefined || value.meta === null || isRecord(value.meta))
  );
}

/**
 * Runtime type guard for GateOut payloads.
 *
 * Checks required fields: risk, telos_score, decision_status, modifications.
 * Optional: bias (number | null), reason (string | null).
 */
export function isGateOut(value: unknown): value is GateOut {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.risk === "number" &&
    typeof value.telos_score === "number" &&
    (value.bias === undefined || value.bias === null || typeof value.bias === "number") &&
    isDecisionStatus(value.decision_status) &&
    (value.reason === undefined || value.reason === null || typeof value.reason === "string") &&
    Array.isArray(value.modifications) &&
    value.modifications.every((m: unknown) => typeof m === "string" || (typeof m === "object" && m !== null))
  );
}

/**
 * Runtime type guard for ValuesOut payloads.
 *
 * Checks required fields: scores, total, top_factors, rationale.
 * Optional: ema (number | null).
 */
export function isValuesOut(value: unknown): value is ValuesOut {
  if (!isRecord(value)) {
    return false;
  }

  return (
    isRecord(value.scores) &&
    typeof value.total === "number" &&
    Array.isArray(value.top_factors) &&
    value.top_factors.every((f: unknown) => typeof f === "string") &&
    typeof value.rationale === "string" &&
    (value.ema === undefined || value.ema === null || typeof value.ema === "number")
  );
}

/**
 * Runtime type guard for ChatRequest payloads.
 *
 * Checks required field: message.
 * Optional: session_id (string | null), memory_auto_put (boolean), persona_evolve (boolean).
 */
export function isChatRequest(value: unknown): value is ChatRequest {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.message === "string" &&
    (value.session_id === undefined || value.session_id === null || typeof value.session_id === "string") &&
    (value.memory_auto_put === undefined || typeof value.memory_auto_put === "boolean") &&
    (value.persona_evolve === undefined || typeof value.persona_evolve === "boolean")
  );
}

/**
 * Runtime type guard for EvoTips payloads.
 *
 * Checks required fields: insights, actions, next_prompts, notes.
 */
export function isEvoTips(value: unknown): value is EvoTips {
  if (!isRecord(value)) {
    return false;
  }

  return (
    isRecord(value.insights) &&
    Array.isArray(value.actions) &&
    value.actions.every((a: unknown) => typeof a === "string") &&
    Array.isArray(value.next_prompts) &&
    value.next_prompts.every((p: unknown) => typeof p === "string") &&
    Array.isArray(value.notes) &&
    value.notes.every((n: unknown) => typeof n === "string")
  );
}

// =========================
// Request types aligned to backend schemas.py
// =========================

/**
 * Trust feedback request body for POST /v1/trust/feedback.
 *
 * Source of truth: veritas_os/api/schemas.py — TrustFeedbackRequest
 */
export interface TrustFeedbackRequest {
  user_id?: string | null;
  score?: number;
  note?: string;
  source?: string;
  [key: string]: unknown;
}

/**
 * Runtime type guard for TrustFeedbackRequest payloads.
 *
 * All fields have defaults in the backend, so only type checks are enforced.
 */
export function isTrustFeedbackRequest(value: unknown): value is TrustFeedbackRequest {
  if (!isRecord(value)) {
    return false;
  }

  return (
    (value.user_id === undefined || value.user_id === null || typeof value.user_id === "string") &&
    (value.score === undefined || typeof value.score === "number") &&
    (value.note === undefined || typeof value.note === "string") &&
    (value.source === undefined || typeof value.source === "string")
  );
}

/**
 * Decision request body for POST /v1/decide.
 *
 * Source of truth: veritas_os/api/schemas.py — DecideRequest
 *
 * Both `alternatives` (canonical) and `options` (deprecated, backward-compatible)
 * are accepted. The backend normalizes them: `alternatives` takes precedence when
 * both are provided; `options` is synced to match `alternatives` after coercion.
 */
export interface DecideRequest {
  query?: string;
  context?: Context | Record<string, unknown>;
  /** Canonical candidate list. */
  alternatives?: Array<Option | Record<string, unknown>>;
  /** @deprecated Use `alternatives`. Kept for backward compatibility; backend syncs to `alternatives`. */
  options?: Array<Option | Record<string, unknown>>;
  min_evidence?: number;
  memory_auto_put?: boolean;
  persona_evolve?: boolean;
  [key: string]: unknown;
}

/**
 * Runtime type guard for DecideRequest payloads.
 *
 * Checks field types when present; all fields have defaults in the backend.
 */
export function isDecideRequest(value: unknown): value is DecideRequest {
  if (!isRecord(value)) {
    return false;
  }

  return (
    (value.query === undefined || typeof value.query === "string") &&
    (value.context === undefined || isRecord(value.context)) &&
    (value.alternatives === undefined || Array.isArray(value.alternatives)) &&
    (value.options === undefined || Array.isArray(value.options)) &&
    (value.min_evidence === undefined || typeof value.min_evidence === "number") &&
    (value.memory_auto_put === undefined || typeof value.memory_auto_put === "boolean") &&
    (value.persona_evolve === undefined || typeof value.persona_evolve === "boolean")
  );
}

/**
 * Memory put request body for POST /v1/memory/put.
 *
 * Source of truth: veritas_os/api/schemas.py — MemoryPutRequest
 */
export interface MemoryPutRequest {
  user_id?: string | null;
  key?: string | null;
  text?: string;
  tags?: string[];
  value?: unknown;
  kind?: string;
  retention_class?: RetentionClass | null;
  meta?: Record<string, unknown>;
  expires_at?: number | null;
  legal_hold?: boolean;
  [key: string]: unknown;
}

/**
 * Runtime type guard for MemoryPutRequest payloads.
 */
export function isMemoryPutRequest(value: unknown): value is MemoryPutRequest {
  if (!isRecord(value)) {
    return false;
  }

  return (
    (value.user_id === undefined || value.user_id === null || typeof value.user_id === "string") &&
    (value.key === undefined || value.key === null || typeof value.key === "string") &&
    (value.text === undefined || typeof value.text === "string") &&
    (value.tags === undefined || (Array.isArray(value.tags) && value.tags.every((t: unknown) => typeof t === "string"))) &&
    (value.kind === undefined || typeof value.kind === "string") &&
    (value.retention_class === undefined || value.retention_class === null || typeof value.retention_class === "string") &&
    (value.meta === undefined || isRecord(value.meta)) &&
    (value.expires_at === undefined || value.expires_at === null || typeof value.expires_at === "number") &&
    (value.legal_hold === undefined || typeof value.legal_hold === "boolean")
  );
}

/**
 * Memory get request body for POST /v1/memory/get.
 *
 * Source of truth: veritas_os/api/schemas.py — MemoryGetRequest
 */
export interface MemoryGetRequest {
  user_id?: string | null;
  key: string;
  [key: string]: unknown;
}

/**
 * Runtime type guard for MemoryGetRequest payloads.
 */
export function isMemoryGetRequest(value: unknown): value is MemoryGetRequest {
  if (!isRecord(value)) {
    return false;
  }

  return (
    (value.user_id === undefined || value.user_id === null || typeof value.user_id === "string") &&
    typeof value.key === "string"
  );
}

/**
 * Memory search request body for POST /v1/memory/search.
 *
 * Source of truth: veritas_os/api/schemas.py — MemorySearchRequest
 */
export interface MemorySearchRequest {
  user_id?: string | null;
  query?: string;
  k?: number;
  min_sim?: number;
  kinds?: string | string[] | null;
  [key: string]: unknown;
}

/**
 * Runtime type guard for MemorySearchRequest payloads.
 */
export function isMemorySearchRequest(value: unknown): value is MemorySearchRequest {
  if (!isRecord(value)) {
    return false;
  }

  return (
    (value.user_id === undefined || value.user_id === null || typeof value.user_id === "string") &&
    (value.query === undefined || typeof value.query === "string") &&
    (value.k === undefined || typeof value.k === "number") &&
    (value.min_sim === undefined || typeof value.min_sim === "number") &&
    (value.kinds === undefined || value.kinds === null || typeof value.kinds === "string" || (Array.isArray(value.kinds) && value.kinds.every((k: unknown) => typeof k === "string")))
  );
}

/**
 * Memory erase request body for POST /v1/memory/erase.
 *
 * Source of truth: veritas_os/api/schemas.py — MemoryEraseRequest
 */
export interface MemoryEraseRequest {
  user_id?: string | null;
  reason?: string;
  actor?: string;
  [key: string]: unknown;
}

/**
 * Runtime type guard for MemoryEraseRequest payloads.
 */
export function isMemoryEraseRequest(value: unknown): value is MemoryEraseRequest {
  if (!isRecord(value)) {
    return false;
  }

  return (
    (value.user_id === undefined || value.user_id === null || typeof value.user_id === "string") &&
    (value.reason === undefined || typeof value.reason === "string") &&
    (value.actor === undefined || typeof value.actor === "string")
  );
}

// =========================
// Response types aligned to openapi.yaml
// =========================

/**
 * Response from POST /v1/memory/put.
 *
 * Source of truth: openapi.yaml — /v1/memory/put 200 response
 */
export interface MemoryPutResponse {
  ok: boolean;
  legacy: {
    saved: boolean;
    key: string | null;
  };
  vector: {
    saved: boolean;
    id: string;
    kind: string;
    tags: string[];
  };
  size: number;
  lifecycle: {
    retention_class: string;
    expires_at: number | null;
    legal_hold: boolean;
  };
  [key: string]: unknown;
}

/**
 * Response from POST /v1/memory/get.
 *
 * Source of truth: openapi.yaml — /v1/memory/get 200 response
 */
export interface MemoryGetResponse {
  ok: boolean;
  error?: string | null;
  /** Retrieved value (arbitrary JSON). */
  value?: unknown;
  [key: string]: unknown;
}

/**
 * Response from POST /v1/replay/{decision_id}.
 *
 * Source of truth: openapi.yaml — /v1/replay/{decision_id} 200 response
 */
export interface ReplayResponse {
  ok: boolean;
  decision_id: string;
  replay_path: string;
  match: boolean;
  diff_summary: string;
  replay_time_ms: number;
  [key: string]: unknown;
}

/**
 * Response from POST /v1/trust/feedback.
 *
 * Source of truth: openapi.yaml — /v1/trust/feedback 200 response
 */
export interface TrustFeedbackResponse {
  ok: boolean;
  [key: string]: unknown;
}

/**
 * Response from GET /v1/trustlog/verify.
 *
 * Source of truth: openapi.yaml — /v1/trustlog/verify 200 response
 */
export interface TrustVerifyResponse {
  ok: boolean;
  valid: boolean;
  detail: string;
  [key: string]: unknown;
}

/**
 * Response from GET /v1/compliance/config.
 *
 * Source of truth: openapi.yaml — /v1/compliance/config 200 response
 */
export interface ComplianceConfigResponse {
  ok: boolean;
  config: Record<string, unknown>;
  [key: string]: unknown;
}

/**
 * Response from POST /v1/compliance/deployment-readiness.
 *
 * Source of truth: openapi.yaml — /v1/compliance/deployment-readiness 200 response
 */
export interface DeploymentReadinessResponse {
  ok: boolean;
  ready: boolean;
  checks: Record<string, unknown>;
  [key: string]: unknown;
}

/**
 * Response from POST /v1/system/halt.
 *
 * Source of truth: openapi.yaml — /v1/system/halt 200 response
 */
export interface SystemHaltResponse {
  ok: boolean;
  halted: boolean;
  [key: string]: unknown;
}

/**
 * Response from POST /v1/system/resume.
 *
 * Source of truth: openapi.yaml — /v1/system/resume 200 response
 */
export interface SystemResumeResponse {
  ok: boolean;
  halted: boolean;
  [key: string]: unknown;
}

/**
 * Response from GET /v1/system/halt-status.
 *
 * Source of truth: openapi.yaml — /v1/system/halt-status 200 response
 */
export interface SystemHaltStatusResponse {
  ok: boolean;
  halted: boolean;
  reason: string | null;
  [key: string]: unknown;
}

/**
 * Single entry in governance policy history.
 *
 * Source of truth: openapi.yaml — /v1/governance/policy/history 200 response
 */
export interface PolicyHistoryEntry {
  timestamp: string;
  actor: string;
  previous: Record<string, unknown>;
  new: Record<string, unknown>;
  [key: string]: unknown;
}

/**
 * Response from GET /v1/governance/policy/history.
 *
 * Source of truth: openapi.yaml — /v1/governance/policy/history 200 response
 */
export interface GovernancePolicyHistoryResponse {
  ok: boolean;
  history: PolicyHistoryEntry[];
  [key: string]: unknown;
}

// =========================
// Request types aligned to server.py
// =========================

/**
 * Runtime compliance config payload for PUT /v1/compliance/config.
 *
 * Source of truth: veritas_os/api/server.py — ComplianceConfigBody
 */
export interface ComplianceConfigBody {
  eu_ai_act_mode?: boolean;
  safety_threshold?: number;
  [key: string]: unknown;
}

/**
 * Request body for POST /v1/system/halt.
 *
 * Source of truth: veritas_os/api/server.py — SystemHaltRequest
 */
export interface SystemHaltRequest {
  reason: string;
  operator: string;
  [key: string]: unknown;
}

/**
 * Request body for POST /v1/system/resume.
 *
 * Source of truth: veritas_os/api/server.py — SystemResumeRequest
 */
export interface SystemResumeRequest {
  operator: string;
  comment?: string;
  [key: string]: unknown;
}

// =========================
// Additional type guards
// =========================

function isStageHealth(value: unknown): value is StageHealth {
  return value === "ok" || value === "warning" || value === "failed" || value === "unknown";
}

/**
 * Runtime type guard for StageMetrics payloads.
 *
 * Checks required field: health (must be a valid StageHealth).
 * Optional: latency_ms, summary, detail, reason.
 */
export function isStageMetrics(value: unknown): value is StageMetrics {
  if (!isRecord(value)) {
    return false;
  }

  return (
    isStageHealth(value.health) &&
    (value.latency_ms === undefined || value.latency_ms === null || typeof value.latency_ms === "number") &&
    (value.summary === undefined || value.summary === null || typeof value.summary === "string") &&
    (value.detail === undefined || value.detail === null || typeof value.detail === "string") &&
    (value.reason === undefined || value.reason === null || typeof value.reason === "string")
  );
}
