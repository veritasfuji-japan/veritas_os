/**
 * /v1/decide response types aligned to backend runtime payloads.
 *
 * Source of truth:
 * - veritas_os/api/schemas.py (DecideResponse, TrustLog, Gate, CritiqueItem, DebateView, FujiDecision)
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
  critique: unknown[];
  debate: unknown[];

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
    (value.plan === null || isRecord(value.plan)) &&
    (value.planner === null || isRecord(value.planner)) &&
    isRecord(value.persona) &&
    Array.isArray(value.memory_citations) &&
    typeof value.memory_used_count === "number" &&
    (value.trust_log === null || isRecord(value.trust_log)) &&
    typeof value.ai_disclosure === "string" &&
    typeof value.regulation_notice === "string"
  );
}

function isDecisionStatus(value: unknown): value is DecisionStatus {
  return value === "allow" || value === "modify" || value === "rejected" || value === "block" || value === "abstain";
}

/**
 * Normalize legacy "rejected" status to the canonical "block".
 *
 * The backend keeps "rejected" for backward compatibility
 * (see veritas_os/api/constants.py — DecisionStatus.REJECTED).
 * Frontend code should use this helper to avoid treating "rejected"
 * and "block" as distinct states.
 */
export function normalizeDecisionStatus(status: DecisionStatus): DecisionStatus {
  return status === "rejected" ? "block" : status;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
