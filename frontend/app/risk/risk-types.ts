export type ClusterKind = "critical" | "risky" | "uncertain" | "stable";
export type Severity = "critical" | "high" | "medium" | "low";
export type RequestStatus = "active" | "mitigated" | "investigating" | "new";

export interface RiskPoint {
  id: string;
  uncertainty: number;
  risk: number;
  timestamp: number;
}

export interface TrendBucket {
  label: string;
  total: number;
  highRisk: number;
}

export interface FlagReason {
  policyConfidence: number;
  unstableOutputSignal: boolean;
  retrievalAnomaly: boolean;
  summary: string;
  suggestedAction: string;
}

export interface FlaggedEntry {
  point: RiskPoint;
  cluster: ClusterKind;
  severity: Severity;
  status: RequestStatus;
  reason: FlagReason;
  relatedPolicyHits: string[];
  stageAnomalies: string[];
}
