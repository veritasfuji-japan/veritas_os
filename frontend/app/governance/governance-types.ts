import type { GovernancePolicy } from "@veritas/types";

export type UserRole = "viewer" | "operator" | "admin";
export type PolicyActionMode = "apply" | "dry-run" | "shadow";
export type GovernanceMode = "standard" | "eu_ai_act";
export type ApprovalStatus = "approved" | "pending" | "rejected" | "draft";
export type WatIssuanceMode = "shadow_only" | "disabled";
export type PartialValidationDefault = "non_admissible";
export type RevocationMode = "bounded_eventual_consistency";

export interface WatConfigUI {
  enabled: boolean;
  issuance_mode: WatIssuanceMode;
  require_observable_digest: boolean;
  default_ttl_seconds: number;
}

export interface PsidConfigUI {
  display_length: number;
}

export interface ShadowValidationConfigUI {
  replay_binding_required: boolean;
  partial_validation_default: PartialValidationDefault;
  warning_only_until: string;
  timestamp_skew_tolerance_seconds: number;
}

export interface RevocationConfigUI {
  mode: RevocationMode;
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
