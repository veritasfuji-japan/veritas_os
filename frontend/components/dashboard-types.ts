export type HealthBand = "healthy" | "degraded" | "critical";

export interface CriticalRailMetric {
  key: string;
  label: string;
  severity: HealthBand;
  currentValue: string;
  baselineDelta: string;
  owner: string;
  lastUpdated: string;
  openIncidents: number;
  href: string;
}

export interface OpsPriorityItem {
  key: string;
  titleJa: string;
  titleEn: string;
  owner: string;
  whyNowJa: string;
  whyNowEn: string;
  impactWindowJa: string;
  impactWindowEn: string;
  ctaJa: string;
  ctaEn: string;
  href: string;
}

export interface GlobalHealthSummaryModel {
  band: HealthBand;
  todayChanges: string[];
  incidents24h: string;
  policyDrift: string;
  trustDegradation: string;
  decisionAnomalies: string;
}

export interface TrustChainIntegrityModel {
  verificationStatus: "verified" | "degraded" | "broken";
  continuityRatio: number;
  brokenSegments: number;
  lastVerifiedAt: string;
  verifier: string;
  blockedReports: number;
}

export interface ReplayDiffInsightModel {
  status: "stable" | "warning" | "critical";
  changedFields: string[];
  safetySensitiveFields: string[];
  operatorActionJa: string;
  operatorActionEn: string;
}

export interface GovernanceApprovalModel {
  pendingVersion: string;
  status: "ready" | "awaiting_approval" | "blocked";
  requiredApprovers: string[];
  missingApprovers: string[];
  policyRiskDelta: string;
}

export interface DecisionEvidenceRouteModel {
  riskSignal: string;
  decisionTarget: string;
  evidenceAnchor: string;
  reportingTarget: string;
}

export type MissionUiState = "loading" | "empty" | "degraded" | "operational";

export type PolicyMode = "enforce" | "observe" | "off";

export interface GovernanceObservation {
  policy_mode: PolicyMode;
  environment: "development" | "test" | "staging" | "production" | string;
  would_have_blocked: boolean;
  would_have_blocked_reason?: string | null;
  effective_outcome: string;
  observed_outcome?: string | null;
  operator_warning?: boolean;
  audit_required?: boolean;
}

export interface PreBindGovernanceSnapshot {
  participation_state?: string;
  preservation_state?: string;
  intervention_viability?: string;
  concise_rationale?: string;
  bind_outcome?: string;
  pre_bind_source?: string;
  pre_bind_detection_summary?: unknown | null;
  pre_bind_preservation_summary?: unknown | null;
  pre_bind_detection_detail?: unknown | null;
  pre_bind_preservation_detail?: unknown | null;
  bind_summary?: unknown | null;
  bind_receipt_id?: string | null;
  execution_intent_id?: string | null;
  decision_id?: string | null;
  bind_reason_code?: string | null;
  bind_failure_reason?: string | null;
  failure_category?: string | null;
  rollback_status?: string | null;
  retry_safety?: string | null;
  target_label?: string | null;
  target_path?: string | null;
  target_type?: string | null;
  target_path_type?: string | null;
  operator_surface?: string | null;
  relevant_ui_href?: string | null;
  authority_check_result?: unknown | null;
  constraint_check_result?: unknown | null;
  drift_check_result?: unknown | null;
  risk_check_result?: unknown | null;
  governance_observation?: GovernanceObservation | null;
}

export const PRE_BIND_GOVERNANCE_VOCABULARY_LABELS = {
  participation_state: "participation_state",
  preservation_state: "preservation_state",
  intervention_viability: "intervention_viability",
  concise_rationale: "concise_rationale",
  bind_outcome: "bind_outcome",
  heading: "Governance layer timeline (pre-bind → bind)",
  unavailable: "n/a",
} as const;
