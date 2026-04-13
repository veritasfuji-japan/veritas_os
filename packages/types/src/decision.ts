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
  user_id: string;
  session_id?: string;
  query: string;
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
  /**
   * Chain verification status from audit verification endpoint.
   *
   * Source of truth: veritas_os/api/schemas.py — TrustLog.chain_verification
   */
  chain_verification?: "verified" | "degraded" | "broken" | "unknown" | null;
  /** Human-readable reason when verification is degraded/broken. */
  chain_verification_reason?: string | null;
  [key: string]: unknown;
}

/** @deprecated Use TrustLog from @veritas/types directly. */
export type TrustLogItem = TrustLog;

/**
 * Verification result for trust log hash-chain integrity.
 *
 * Source of truth: veritas_os/api/schemas.py — VerificationResultLiteral
 */
export type VerificationResult = "ok" | "broken" | "not_found";

/**
 * Paginated response envelope for GET /v1/trust/logs.
 *
 * Source of truth: veritas_os/api/schemas.py — TrustLogsResponse
 */
export interface TrustLogsResponse {
  items: TrustLog[];
  cursor: string | null;
  next_cursor: string | null;
  limit: number;
  has_more: boolean;
}

/**
 * Response envelope for GET /v1/trust/{request_id}.
 *
 * Source of truth: veritas_os/api/schemas.py — RequestLogResponse
 */
export interface RequestLogResponse {
  request_id: string;
  items: TrustLog[];
  count: number;
  chain_ok: boolean;
  verification_result: VerificationResult | string;
}

/**
 * Runtime type guard for TrustLog payloads.
 *
 * Validates the shared TrustLog type, used for both /v1/decide embedded
 * trust_log and /v1/trust/logs list items.
 *
 * Source of truth: veritas_os/api/schemas.py — TrustLog
 */
export function isTrustLog(value: unknown): value is TrustLog {
  if (!isRecord(value)) {
    return false;
  }

  if (typeof value.request_id !== "string") {
    return false;
  }

  if (typeof value.created_at !== "string") {
    return false;
  }

  if (!isStringArray(value.sources) || !isStringArray(value.critics) || !isStringArray(value.checks)) {
    return false;
  }

  if (typeof value.approver !== "string") {
    return false;
  }

  if (value.fuji !== undefined && value.fuji !== null && !isRecord(value.fuji)) {
    return false;
  }

  if (value.sha256 !== undefined && value.sha256 !== null && typeof value.sha256 !== "string") {
    return false;
  }

  if (value.sha256_prev !== undefined && value.sha256_prev !== null && typeof value.sha256_prev !== "string") {
    return false;
  }

  if (value.query !== undefined && value.query !== null && typeof value.query !== "string") {
    return false;
  }

  if (value.gate_status !== undefined && value.gate_status !== null && typeof value.gate_status !== "string") {
    return false;
  }

  if (value.gate_risk !== undefined && value.gate_risk !== null && typeof value.gate_risk !== "number") {
    return false;
  }

  const VALID_CHAIN_VERIFICATION: ReadonlySet<string> = new Set(["verified", "degraded", "broken", "unknown"]);
  if (
    value.chain_verification !== undefined
    && value.chain_verification !== null
    && (typeof value.chain_verification !== "string" || !VALID_CHAIN_VERIFICATION.has(value.chain_verification))
  ) {
    return false;
  }

  if (
    value.chain_verification_reason !== undefined
    && value.chain_verification_reason !== null
    && typeof value.chain_verification_reason !== "string"
  ) {
    return false;
  }

  return true;
}

/** @deprecated Use isTrustLog instead. */
export const isTrustLogItem = isTrustLog;

/**
 * Runtime type guard for TrustLogsResponse payloads.
 *
 * Source of truth: veritas_os/api/schemas.py — TrustLogsResponse
 */
export function isTrustLogsResponse(value: unknown): value is TrustLogsResponse {
  if (!isRecord(value)) {
    return false;
  }

  return (
    Array.isArray(value.items)
    && value.items.every((item: unknown) => isTrustLog(item))
    && (value.cursor === null || typeof value.cursor === "string")
    && (value.next_cursor === null || typeof value.next_cursor === "string")
    && typeof value.limit === "number" && Number.isFinite(value.limit)
    && typeof value.has_more === "boolean"
  );
}

/**
 * Runtime type guard for RequestLogResponse payloads.
 *
 * Source of truth: veritas_os/api/schemas.py — RequestLogResponse
 */
export function isRequestLogResponse(value: unknown): value is RequestLogResponse {
  if (!isRecord(value)) {
    return false;
  }

  const VALID_VERIFICATION_RESULTS: ReadonlySet<string> = new Set(["ok", "broken", "not_found"]);

  return (
    typeof value.request_id === "string"
    && Array.isArray(value.items)
    && value.items.every((item: unknown) => isTrustLog(item))
    && typeof value.count === "number" && Number.isFinite(value.count)
    && typeof value.chain_ok === "boolean"
    && typeof value.verification_result === "string"
    && VALID_VERIFICATION_RESULTS.has(value.verification_result)
  );
}

function isStringArray(value: unknown): boolean {
  return Array.isArray(value) && value.every((s: unknown) => typeof s === "string");
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

/* ------------------------------------------------------------------ */
/*  Continuation runtime (shadow/observe — phase-1)                    */
/* ------------------------------------------------------------------ */

/** Claim status values from ContinuationClaimLineage. */
export type ContinuationClaimStatus =
  | "live"
  | "narrowed"
  | "degraded"
  | "escalated"
  | "halted"
  | "revoked";

/** Revalidation status values from ContinuationReceipt. */
export type ContinuationRevalidationStatus =
  | "renewed"
  | "narrowed"
  | "degraded"
  | "escalated"
  | "halted"
  | "revoked"
  | "failed";

/**
 * Snapshot-side (state) of continuation runtime output.
 *
 * Source of truth: veritas_os/core/continuation_runtime/snapshot.py
 */
/**
 * State-side (durable standing) of continuation runtime output.
 *
 * Contains only durable standing facts.  Boundary adjudication
 * vocabulary (halted, narrowed, etc.) appears here only when a
 * DurableConsequence has been recorded.
 *
 * Source of truth: veritas_os/core/continuation_runtime/snapshot.py
 */
export interface ContinuationStateSummary {
  claim_lineage_id: string;
  snapshot_id: string;
  claim_status: ContinuationClaimStatus;
  law_version: string;
  support_basis?: Record<string, string> | null;
  burden_state?: Record<string, unknown> | null;
  headroom_state?: Record<string, unknown> | null;
  scope?: Record<string, unknown> | null;
  durable_consequence?: {
    has_durable_halt?: boolean;
    has_durable_scope_reduction?: boolean;
    has_durable_class_change?: boolean;
    has_irreversible_revocation?: boolean;
    promotion_reason?: string;
  } | null;
  [key: string]: unknown;
}

/**
 * Receipt-side (proof-bearing audit witness) of continuation runtime output.
 *
 * The receipt is the primary record of boundary adjudication.  It carries
 * the full adjudication vocabulary, durable-promotion assessment, and
 * reopening eligibility.
 *
 * Source of truth: veritas_os/core/continuation_runtime/receipt.py
 */
export interface ContinuationReceiptSummary {
  receipt_id: string;
  revalidation_status: ContinuationRevalidationStatus;
  revalidation_outcome: ContinuationRevalidationStatus;
  should_refuse_before_effect: boolean;
  divergence_flag: boolean;
  local_step_result?: string | null;
  reason_codes?: string[];
  support_basis_digest?: string | null;
  burden_headroom_digest?: string | null;
  prior_decision_continuity_ref?: string | null;
  parent_receipt_ref?: string | null;
  receipt_hash_or_attestation?: string | null;
  /** Primary boundary adjudication outcome (receipt-first). */
  boundary_outcome?: string | null;
  /** Whether boundary outcome was promoted into durable state. */
  is_durable_promotion?: boolean;
  /** "provisional" or "durable_promotable". */
  provisional_vs_durable?: string | null;
  /** For narrowed: is the prior scope width restorable? */
  reopening_eligible?: boolean;
  [key: string]: unknown;
}

/**
 * Top-level continuation block in DecideResponse.
 * Present only when the continuation runtime feature flag is on.
 */
export interface ContinuationOutput {
  state: ContinuationStateSummary;
  receipt: ContinuationReceiptSummary;
}

export interface DecideResponse extends DecideResponseMeta {
  /* ------------------------------------------------------------------ */
  /* Core decision contract fields                                      */
  /* ------------------------------------------------------------------ */
  chosen: Record<string, unknown>;
  alternatives: DecisionAlternative[];
  /** Backward-compatible alias of alternatives for legacy clients. */
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

  /* ------------------------------------------------------------------ */
  /* Audit / debug / internal fields                                   */
  /* ------------------------------------------------------------------ */
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

  /**
   * Continuation runtime output (shadow/observe — phase-1).
   * Present only when VERITAS_CAP_CONTINUATION_RUNTIME is enabled.
   */
  continuation?: ContinuationOutput | null;

  /**
   * Polished natural-language answer for user-facing display.
   * Present in simple_qa and knowledge_qa modes. Frontends should
   * prefer this over raw chosen/meta fields when available.
   */
  user_summary?: string | null;

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
  kind?: MemoryKind;
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
  kinds?: MemoryKind | MemoryKind[] | null;
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
  /** Replay artifact schema version (e.g. "1.0.0"). */
  schema_version?: string;
  /** Highest severity among changed fields: "critical" | "warning" | "info". */
  severity?: string;
  /** Overall divergence classification: "no_divergence" | "acceptable_divergence" | "critical_divergence". */
  divergence_level?: string;
  /** Human-readable audit summary of the replay result. */
  audit_summary?: string;
  [key: string]: unknown;
}

/**
 * Response from POST /v1/trust/feedback.
 *
 * Source of truth: veritas_os/api/schemas.py — TrustFeedbackResponse
 */
export interface TrustFeedbackResponse {
  ok: boolean;
  user_id?: string | null;
  error?: string | null;
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
 * Source of truth: veritas_os/api/schemas.py — GovernancePolicyHistoryResponse
 */
export interface GovernancePolicyHistoryResponse {
  ok: boolean;
  count?: number;
  history: PolicyHistoryEntry[];
  error?: string | null;
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
