import type { TrustLogItem } from "../../lib/api-validators";
import type { AuditSummaryMetrics, ChainResult, VerificationStatus } from "./types";

function getReplayId(item: TrustLogItem): string {
  const replayId = item.replay_id;
  const linkedReplayId = item.linked_replay_id;
  if (typeof replayId === "string" && replayId.length > 0) {
    return replayId;
  }
  if (typeof linkedReplayId === "string" && linkedReplayId.length > 0) {
    return linkedReplayId;
  }
  return "";
}

function getPolicyVersion(item: TrustLogItem): string {
  return typeof item.policy_version === "string" && item.policy_version.length > 0
    ? item.policy_version
    : "unknown";
}

/**
 * Classifies a hash-chain relationship using the previous chronological entry.
 */
export function classifyChain(item: TrustLogItem, previous: TrustLogItem | null): ChainResult {
  if (!item.sha256) {
    return { status: "missing", reason: "Current entry is missing sha256." };
  }

  if (!item.sha256_prev) {
    return previous
      ? { status: "orphan", reason: "sha256_prev is missing while a previous entry exists." }
      : { status: "verified", reason: "Genesis entry with no parent hash." };
  }

  if (!previous?.sha256) {
    return { status: "missing", reason: "Previous entry is missing sha256." };
  }

  if (item.sha256_prev !== previous.sha256) {
    return {
      status: "broken",
      reason: "sha256_prev does not match previous entry sha256. Chain integrity is broken.",
    };
  }

  return { status: "verified", reason: "Hash chain is consistent." };
}

/**
 * Computes summary metrics needed for human-focused audit triage.
 */
export function buildAuditSummary(items: TrustLogItem[]): AuditSummaryMetrics {
  const statusCount: Record<VerificationStatus, number> = {
    verified: 0,
    broken: 0,
    missing: 0,
    orphan: 0,
  };
  const policyCounts = new Map<string, number>();
  let replayLinked = 0;

  for (let index = 0; index < items.length; index += 1) {
    const chain = classifyChain(items[index], items[index + 1] ?? null);
    statusCount[chain.status] += 1;

    const policyVersion = getPolicyVersion(items[index]);
    policyCounts.set(policyVersion, (policyCounts.get(policyVersion) ?? 0) + 1);

    if (getReplayId(items[index])) {
      replayLinked += 1;
    }
  }

  return {
    totalEntries: items.length,
    verified: statusCount.verified,
    broken: statusCount.broken,
    missing: statusCount.missing,
    orphan: statusCount.orphan,
    replayLinked,
    policyVersionDistribution: Array.from(policyCounts.entries())
      .map(([version, count]) => ({ version, count }))
      .sort((a, b) => b.count - a.count),
  };
}

/**
 * Matches cross-search query against request/decision/replay/policy identifiers.
 */
export function matchesCrossSearch(item: TrustLogItem, query: string): boolean {
  if (!query) {
    return true;
  }
  const queryLower = query.toLowerCase();
  const candidates = [
    String(item.request_id ?? ""),
    String(item.decision_id ?? ""),
    String(getReplayId(item)),
    String(item.policy_version ?? ""),
  ];
  return candidates.some((candidate) => candidate.toLowerCase().includes(queryLower));
}

export function resolveReplayId(item: TrustLogItem): string {
  return getReplayId(item) || "-";
}



/**
 * Counts entries that fall into an inclusive UTC day range.
 */
export function countEntriesInPeriod(
  items: TrustLogItem[],
  startDate: string,
  endDate: string,
): number {
  if (!startDate || !endDate) {
    return 0;
  }
  const start = new Date(`${startDate}T00:00:00.000Z`).getTime();
  const end = new Date(`${endDate}T23:59:59.999Z`).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end) || start > end) {
    return 0;
  }

  return items.filter((item) => {
    const stamp = new Date(String(item.created_at ?? "")).getTime();
    return Number.isFinite(stamp) && stamp >= start && stamp <= end;
  }).length;
}

export function buildHumanSummary(item: TrustLogItem, chain: ChainResult): string {
  const stage = typeof item.stage === "string" ? item.stage : "unknown stage";
  const status = typeof item.status === "string" ? item.status : "unknown status";
  const requestId = typeof item.request_id === "string" ? item.request_id : "unknown request";
  return `At stage ${stage}, request ${requestId} produced status ${status}. Chain is ${chain.status}.`;
}
