/**
 * Governance policy types aligned to backend runtime models.
 *
 * Source of truth:
 * - veritas_os/api/governance.py (FujiRules, RiskThresholds, AutoStop,
 *   LogRetention, GovernancePolicy)
 * - openapi.yaml (GovernancePolicy, GovernancePolicyResponse)
 */

/** FUJI safety-gate rule toggles. */
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

/** Risk-score band thresholds (all values 0.0–1.0). */
export interface RiskThresholds {
  allow_upper: number;
  warn_upper: number;
  human_review_upper: number;
  deny_upper: number;
}

/** Automated circuit-breaker / rate-limit settings. */
export interface AutoStop {
  enabled: boolean;
  max_risk_score: number;
  max_consecutive_rejects: number;
  max_requests_per_minute: number;
}

/** Audit-log retention and redaction settings. */
export interface LogRetention {
  retention_days: number;
  audit_level: string;
  include_fields: string[];
  redact_before_log: boolean;
  max_log_size: number;
}

/**
 * Full governance policy object returned by the backend.
 *
 * Source of truth: veritas_os/api/governance.py — GovernancePolicy
 */
export interface GovernancePolicy {
  version: string;
  fuji_rules: FujiRules;
  risk_thresholds: RiskThresholds;
  auto_stop: AutoStop;
  log_retention: LogRetention;
  updated_at: string;
  updated_by: string;
}

/** Envelope returned by GET /v1/governance/policy. */
export interface GovernancePolicyResponse {
  ok: boolean;
  policy: GovernancePolicy;
}
