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
