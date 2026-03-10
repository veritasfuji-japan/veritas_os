/**
 * Governance policy types aligned to backend API endpoints.
 *
 * Source of truth:
 * - veritas_os/api/server.py — GET/PUT /v1/governance/policy
 * - veritas_os/logging/governance.py — persistence layer
 */

/* ------------------------------------------------------------------ */
/*  FUJI safety-gate rule toggles                                      */
/* ------------------------------------------------------------------ */

export interface FujiRules {
  pii_check: boolean;
  self_harm_block: boolean;
  illicit_block: boolean;
  violence_review: boolean;
  minors_review: boolean;
  keyword_hard_block: boolean;
  keyword_soft_flag: boolean;
  llm_safety_head: boolean;
}

/* ------------------------------------------------------------------ */
/*  Risk threshold boundaries                                          */
/* ------------------------------------------------------------------ */

export interface RiskThresholds {
  /** Upper boundary for "allow" band (0–1). */
  allow_upper: number;
  /** Upper boundary for "warn" band (0–1). */
  warn_upper: number;
  /** Upper boundary for "human review" band (0–1). */
  human_review_upper: number;
  /** Upper boundary for "deny" band (0–1). */
  deny_upper: number;
}

/* ------------------------------------------------------------------ */
/*  Auto-stop circuit breaker                                          */
/* ------------------------------------------------------------------ */

export interface AutoStop {
  enabled: boolean;
  max_risk_score: number;
  max_consecutive_rejects: number;
  max_requests_per_minute: number;
}

/* ------------------------------------------------------------------ */
/*  Log retention configuration                                        */
/* ------------------------------------------------------------------ */

export type AuditLevel = "none" | "minimal" | "standard" | "full" | "strict";

export interface LogRetention {
  retention_days: number;
  audit_level: AuditLevel;
  include_fields: string[];
  redact_before_log: boolean;
  max_log_size: number;
}

/* ------------------------------------------------------------------ */
/*  Governance policy (backend canonical shape)                        */
/* ------------------------------------------------------------------ */

export interface GovernancePolicy {
  version: string;
  fuji_rules: FujiRules;
  risk_thresholds: RiskThresholds;
  auto_stop: AutoStop;
  log_retention: LogRetention;
  updated_at: string;
  updated_by: string;
  [key: string]: unknown;
}

/* ------------------------------------------------------------------ */
/*  API response wrapper                                               */
/* ------------------------------------------------------------------ */

export interface GovernancePolicyResponse {
  ok: boolean;
  policy: GovernancePolicy;
}

/* ------------------------------------------------------------------ */
/*  Trust feedback (POST /v1/trust/feedback)                           */
/* ------------------------------------------------------------------ */

export interface TrustFeedbackResponse {
  ok: boolean;
  error: string | null;
  user_id?: string;
}

/* ------------------------------------------------------------------ */
/*  SSE event payload (GET /v1/events)                                 */
/* ------------------------------------------------------------------ */

export interface SSEEventPayload {
  type: string;
  ts: string;
  payload: Record<string, unknown>;
  id?: number;
}
