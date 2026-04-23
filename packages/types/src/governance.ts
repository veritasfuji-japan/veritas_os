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

/** Permitted audit verbosity levels. Source of truth: veritas_os/api/governance.py — LogRetention.audit_level */
export type AuditLevel = "none" | "minimal" | "summary" | "standard" | "full" | "strict";

/** Audit-log retention and redaction settings. */
export interface LogRetention {
  retention_days: number;
  audit_level: AuditLevel;
  include_fields: string[];
  redact_before_log: boolean;
  max_log_size: number;
}

/** Progressive rollout controls for canary/staged policy enforcement. */
export interface RolloutControls {
  strategy: "disabled" | "canary" | "staged" | "full";
  canary_percent: number;
  stage: number;
  staged_enforcement: boolean;
}

/** Human-review and approver identity-binding workflow settings. */
export interface ApprovalWorkflowConfig {
  human_review_ticket: string;
  human_review_required: boolean;
  approver_identity_binding: boolean;
  approver_identities: string[];
}

/** WAT issuance + retention boundary controls. */
export interface WatConfig {
  enabled: boolean;
  issuance_mode: "shadow_only" | "disabled";
  require_observable_digest: boolean;
  default_ttl_seconds: number;
  signer_backend: string;
  wat_metadata_retention_ttl_seconds: number;
  wat_event_pointer_retention_ttl_seconds: number;
  observable_digest_retention_ttl_seconds: number;
  observable_digest_access_class: "restricted" | "privileged";
  observable_digest_ref: string;
  retention_policy_version: string;
  retention_enforced_at_write: boolean;
}

/** Policy-scoped identifier display and enforcement settings. */
export interface PsidConfig {
  enforcement_mode: "full_digest_only";
  display_length: number;
}

/** Shadow validation rollout guardrails. */
export interface ShadowValidationConfig {
  enabled: boolean;
  partial_validation_default: "non_admissible";
  warning_only_until: string;
  timestamp_skew_tolerance_seconds: number;
  replay_binding_required: boolean;
  replay_binding_escalation_threshold: number;
  partial_validation_requires_confirmation: boolean;
}

/** Revocation propagation consistency controls. */
export interface RevocationConfig {
  enabled: boolean;
  mode: "bounded_eventual_consistency";
  alert_target_seconds: number;
  convergence_target_p95_seconds: number;
  degrade_on_pending: boolean;
  revocation_confirmation_required: boolean;
  auto_escalate_confirmed_revocations: boolean;
}

/** Drift-score vector weights and threshold boundaries. */
export interface DriftScoringConfig {
  policy_weight: number;
  signature_weight: number;
  observable_weight: number;
  temporal_weight: number;
  healthy_threshold: number;
  critical_threshold: number;
}

/** Runtime bind adjudication safety controls. */
export interface BindAdjudicationPolicyConfig {
  missing_signal_default: "block" | "escalate";
  drift_required: boolean;
  ttl_required: boolean;
  approval_freshness_required: boolean;
  rollback_on_apply_failure: boolean;
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
  rollout_controls: RolloutControls;
  approval_workflow: ApprovalWorkflowConfig;
  wat: WatConfig;
  psid: PsidConfig;
  shadow_validation: ShadowValidationConfig;
  revocation: RevocationConfig;
  drift_scoring: DriftScoringConfig;
  bind_adjudication: BindAdjudicationPolicyConfig;
  operator_verbosity: "minimal" | "expanded";
  updated_at: string;
  updated_by: string;
}

/** Envelope returned by GET /v1/governance/policy. */
export interface GovernancePolicyResponse {
  ok: boolean;
  policy: GovernancePolicy;
}
