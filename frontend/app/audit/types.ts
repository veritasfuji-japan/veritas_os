import type { TrustLogItem } from "../../lib/api-validators";

export type VerificationStatus = "verified" | "broken" | "missing" | "orphan";

export interface ChainResult {
  status: VerificationStatus;
  reason: string;
}

export interface PolicyVersionCount {
  version: string;
  count: number;
}

export interface AuditSummaryMetrics {
  totalEntries: number;
  verified: number;
  broken: number;
  missing: number;
  orphan: number;
  replayLinked: number;
  policyVersionDistribution: PolicyVersionCount[];
}

export interface TimelineAuditItem {
  item: TrustLogItem;
  chain: ChainResult;
  replayLinked: boolean;
}

export interface RegulatoryReport {
  generatedAt: string;
  totalEntries: number;
  mismatchLinks: number;
  brokenCount: number;
  redactionMode: string;
}
