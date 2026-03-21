import type { GovernancePolicy } from "@veritas/types";

export type UserRole = "viewer" | "operator" | "admin";
export type PolicyActionMode = "apply" | "dry-run" | "shadow";
export type GovernanceMode = "standard" | "eu_ai_act";
export type ApprovalStatus = "approved" | "pending" | "rejected" | "draft";

/** UI-specific extension of the API GovernancePolicy with local workflow fields. */
export interface GovernancePolicyUI extends GovernancePolicy {
  draft_version?: string;
  effective_at?: string;
  last_applied?: string;
  approval_status: ApprovalStatus;
}

export interface DiffChange {
  path: string;
  old: string;
  next: string;
  category: "rule" | "threshold" | "escalation" | "retention" | "meta";
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
