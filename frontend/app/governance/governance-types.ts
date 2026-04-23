import type { GovernancePolicy } from "@veritas/types";

export type UserRole = "viewer" | "operator" | "admin";
export type PolicyActionMode = "apply" | "dry-run" | "shadow";
export type GovernanceMode = "standard" | "eu_ai_act";
export type ApprovalStatus = "approved" | "pending" | "rejected" | "draft";
export type WatIssuanceMode = "shadow_only" | "disabled";
export type PartialValidationDefault = "non_admissible";
export type RevocationMode = "bounded_eventual_consistency";
export type OperatorVerbosity = "minimal" | "expanded";

export interface WatConfigUI {
  enabled: boolean;
  issuance_mode: WatIssuanceMode;
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

export interface PsidConfigUI {
  enforcement_mode: "full_digest_only";
  display_length: number;
}

export interface ShadowValidationConfigUI {
  enabled: boolean;
  replay_binding_required: boolean;
  replay_binding_escalation_threshold: number;
  partial_validation_default: PartialValidationDefault;
  partial_validation_requires_confirmation: boolean;
  warning_only_until: string;
  timestamp_skew_tolerance_seconds: number;
}

export interface RevocationConfigUI {
  enabled: boolean;
  mode: RevocationMode;
  alert_target_seconds: number;
  convergence_target_p95_seconds: number;
  degrade_on_pending: boolean;
  revocation_confirmation_required: boolean;
  auto_escalate_confirmed_revocations: boolean;
}


export interface BindAdjudicationConfigUI {
  missing_signal_default: "block" | "escalate";
  drift_required: boolean;
  ttl_required: boolean;
  approval_freshness_required: boolean;
  rollback_on_apply_failure: boolean;
}

export interface DriftScoringConfigUI {
  policy_weight: number;
  signature_weight: number;
  observable_weight: number;
  temporal_weight: number;
  healthy_threshold: number;
  critical_threshold: number;
}

/** UI-specific extension of the API GovernancePolicy with local workflow fields. */
export interface GovernancePolicyUI extends GovernancePolicy {
  draft_version?: string;
  effective_at?: string;
  last_applied?: string;
  approval_status: ApprovalStatus;
  wat: WatConfigUI;
  psid: PsidConfigUI;
  shadow_validation: ShadowValidationConfigUI;
  revocation: RevocationConfigUI;
  drift_scoring: DriftScoringConfigUI;
  bind_adjudication: BindAdjudicationConfigUI;
  operator_verbosity: OperatorVerbosity;
}

export interface DiffChange {
  path: string;
  old: string;
  next: string;
  category: "rule" | "threshold" | "escalation" | "retention" | "rollout" | "approval" | "meta";
}

export interface HistoryEntry {
  id: string;
  action: string;
  actor: UserRole;
  at: string;
  summary: string;
}

export interface TrustLogEntry {
  id: string;
  at: string;
  message: string;
  severity: "info" | "warning" | "policy";
}
