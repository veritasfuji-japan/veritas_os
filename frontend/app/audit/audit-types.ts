/**
 * Audit-specific type definitions for the TrustLog Explorer.
 *
 * Separates audit / UI concerns from the raw API shapes defined in
 * `lib/api-validators.ts` and `@veritas/types`.
 *
 * Future API integration points are marked with `@api-hook` comments.
 */

import type { TrustLogItem } from "../../lib/api-validators";

/* ------------------------------------------------------------------ */
/*  Chain verification                                                 */
/* ------------------------------------------------------------------ */

export type VerificationStatus = "verified" | "broken" | "missing" | "orphan";

export interface ChainResult {
  status: VerificationStatus;
  reason: string;
}

export interface ChainLink {
  previous: TrustLogItem | null;
  current: TrustLogItem;
  next: TrustLogItem | null;
  result: ChainResult;
}

/* ------------------------------------------------------------------ */
/*  Audit summary                                                      */
/* ------------------------------------------------------------------ */

export interface AuditSummary {
  total: number;
  verified: number;
  broken: number;
  missing: number;
  orphan: number;
  replayLinked: number;
  /** policy_version → count */
  policyVersions: Record<string, number>;
}

/* ------------------------------------------------------------------ */
/*  Timeline row (derived from TrustLogItem for display)               */
/* ------------------------------------------------------------------ */

export interface TimelineRow {
  item: TrustLogItem;
  chain: ChainResult;
  severity: string;
  stage: string;
  timestamp: string;
  requestId: string;
  decisionId: string;
  replayId: string;
  policyVersion: string;
}

/* ------------------------------------------------------------------ */
/*  Selected audit detail tabs                                         */
/* ------------------------------------------------------------------ */

export type DetailTab = "summary" | "metadata" | "hash" | "related" | "raw";

export interface SelectedAuditDetail {
  item: TrustLogItem;
  chain: ChainLink;
  humanSummary: string;
}

/* ------------------------------------------------------------------ */
/*  Cross-search                                                       */
/* ------------------------------------------------------------------ */

export type SearchField = "all" | "decision_id" | "request_id" | "replay_id" | "policy_version";

export interface CrossSearchParams {
  query: string;
  field: SearchField;
}

/* ------------------------------------------------------------------ */
/*  Export                                                              */
/* ------------------------------------------------------------------ */

export type ExportFormat = "json" | "pdf";
export type RedactionMode = "full" | "redacted" | "metadata-only";

export interface ExportConfig {
  format: ExportFormat;
  redaction: RedactionMode;
  startDate: string;
  endDate: string;
  piiAcknowledged: boolean;
}

export interface RegulatoryReport {
  generatedAt: string;
  totalEntries: number;
  verified: number;
  broken: number;
  missing: number;
  orphan: number;
  mismatchLinks: number;
  brokenCount: number;
  redactionMode: RedactionMode;
  policyVersions: Record<string, number>;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

export function getString(item: TrustLogItem, key: string): string {
  const value = item[key];
  return typeof value === "string" ? value : "-";
}

export function shortHash(value: string | undefined | null): string {
  if (!value) return "---";
  if (value.length <= 18) return value;
  return `${value.slice(0, 10)}...${value.slice(-6)}`;
}

export function toPrettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

/**
 * Classifies a single hash-chain link for audit visualization.
 */
export function classifyChain(
  item: TrustLogItem,
  previous: TrustLogItem | null,
): ChainResult {
  if (!item.sha256) {
    return { status: "missing", reason: "current sha256 missing" };
  }
  if (!item.sha256_prev) {
    return previous
      ? { status: "orphan", reason: "no sha256_prev while previous exists" }
      : { status: "verified", reason: "genesis entry" };
  }
  if (!previous?.sha256) {
    return { status: "missing", reason: "previous sha256 missing" };
  }
  if (item.sha256_prev !== previous.sha256) {
    return { status: "broken", reason: "sha256_prev does not match previous sha256" };
  }
  return { status: "verified", reason: "hash chain match" };
}

/**
 * Build a human-readable one-line summary for an audit entry.
 */
export function buildHumanSummary(item: TrustLogItem): string {
  const stage = getString(item, "stage") || "UNKNOWN";
  const status = getString(item, "status");
  const reqId = item.request_id ?? "-";
  const severity = getString(item, "severity");
  const parts: string[] = [`Stage "${stage}"`];
  if (status !== "-") parts.push(`returned ${status}`);
  parts.push(`for request ${reqId}`);
  if (severity !== "-") parts.push(`(severity: ${severity})`);
  return parts.join(" ");
}

/**
 * Compute a full AuditSummary from a list of items.
 */
export function computeAuditSummary(items: TrustLogItem[]): AuditSummary {
  let verified = 0;
  let broken = 0;
  let missing = 0;
  let orphan = 0;
  let replayLinked = 0;
  const policyVersions: Record<string, number> = {};

  for (let i = 0; i < items.length; i += 1) {
    const status = classifyChain(items[i], items[i + 1] ?? null).status;
    if (status === "verified") verified += 1;
    else if (status === "broken") broken += 1;
    else if (status === "missing") missing += 1;
    else if (status === "orphan") orphan += 1;

    if (typeof items[i].replay_id === "string") replayLinked += 1;

    const pv = getString(items[i], "policy_version");
    if (pv !== "-") policyVersions[pv] = (policyVersions[pv] ?? 0) + 1;
  }

  return { total: items.length, verified, broken, missing, orphan, replayLinked, policyVersions };
}
