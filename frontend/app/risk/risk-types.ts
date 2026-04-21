export type ClusterKind = "critical" | "risky" | "uncertain" | "stable";
export type Severity = "critical" | "high" | "medium" | "low";
export type RequestStatus = "active" | "mitigated" | "investigating" | "new";
export type DecisionPhaseOutcome = "allow" | "modify" | "deny" | "hold";
export type BindPhaseOutcome =
  | "COMMITTED"
  | "BLOCKED"
  | "ESCALATED"
  | "ROLLED_BACK"
  | "APPLY_FAILED"
  | "SNAPSHOT_FAILED"
  | "PRECONDITION_FAILED";

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

export interface BindBreakdown {
  authority: "PASS" | "FAIL";
  constraints: "PASS" | "FAIL";
  drift: "PASS" | "FAIL";
  risk: "PASS" | "FAIL";
}

export interface FlaggedEntry {
  point: RiskPoint;
  cluster: ClusterKind;
  severity: Severity;
  status: RequestStatus;
  decisionOutcome: DecisionPhaseOutcome;
  bindOutcome: BindPhaseOutcome;
  bindFailureReason: string;
  bindReceiptId: string;
  bindLineageHref: string;
  bindBreakdown: BindBreakdown;
  reason: FlagReason;
  relatedPolicyHits: string[];
  stageAnomalies: string[];
}
