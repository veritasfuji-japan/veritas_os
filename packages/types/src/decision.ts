/**
 * /v1/decide response types aligned to backend runtime payloads.
 *
 * Source of truth:
 * - veritas_os/api/schemas.py (DecideResponse, TrustLog, Gate)
 * - veritas_os/core/pipeline.py (response assembly)
 */

export type DecisionStatus = "allow" | "modify" | "rejected" | "block" | "abstain";

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
  plan: Record<string, unknown> | null;
  planner: Record<string, unknown> | null;
  persona: Record<string, unknown>;
  memory_citations: unknown[];
  memory_used_count: number;
  trust_log: TrustLog | Record<string, unknown> | null;

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
    (value.plan === null || isRecord(value.plan)) &&
    (value.planner === null || isRecord(value.planner)) &&
    isRecord(value.persona) &&
    Array.isArray(value.memory_citations) &&
    typeof value.memory_used_count === "number" &&
    (value.trust_log === null || isRecord(value.trust_log))
  );
}

function isDecisionStatus(value: unknown): value is DecisionStatus {
  return value === "allow" || value === "modify" || value === "rejected" || value === "block" || value === "abstain";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
