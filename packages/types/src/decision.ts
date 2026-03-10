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
  fuji?: Record<string, unknown> | null;
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
  evo: Record<string, unknown> | null;
  meta: Record<string, unknown>;
  plan: Record<string, unknown> | null;
  planner: Record<string, unknown> | null;
  persona: Record<string, unknown>;
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
