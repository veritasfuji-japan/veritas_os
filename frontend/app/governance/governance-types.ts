import type { GovernancePolicy } from "@veritas/types";

export type UserRole = "viewer" | "operator" | "admin";
export type PolicyActionMode = "apply" | "dry-run" | "shadow";
export type GovernanceMode = "standard" | "eu_ai_act";
export type ApprovalStatus = "approved" | "pending" | "rejected" | "draft";
export type WatIssuanceMode = "strict" | "shadow" | "hybrid";
export type WatRevocationMode = "soft" | "hard";

export interface WatDriftWeights {
  policy: number;
  signature: number;
  observable: number;
  temporal: number;
}

export interface WatSettingsUI {
  enabled: boolean;
  issuance_mode: WatIssuanceMode;
  require_observable_digest: boolean;
  default_ttl_seconds: number;
  psid_display_length: number;
  replay_binding_required: boolean;
  partial_validation_default: boolean;
  warning_only_until: string;
  timestamp_skew_tolerance_seconds: number;
  revocation_mode: WatRevocationMode;
  drift_weights: WatDriftWeights;
}

/** UI-specific extension of the API GovernancePolicy with local workflow fields. */
export interface GovernancePolicyUI extends GovernancePolicy {
  draft_version?: string;
  effective_at?: string;
  last_applied?: string;
  approval_status: ApprovalStatus;
  wat_settings?: WatSettingsUI;
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
