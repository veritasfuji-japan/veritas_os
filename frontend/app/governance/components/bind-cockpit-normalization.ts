export type CanonicalBindOutcome =
  | "COMMITTED"
  | "BLOCKED"
  | "ESCALATED"
  | "ROLLED_BACK"
  | "APPLY_FAILED"
  | "SNAPSHOT_FAILED"
  | "PRECONDITION_FAILED";

export type CanonicalTargetPathType =
  | "governance_policy_update"
  | "policy_bundle_promotion"
  | "compliance_config_update"
  | "other";

export interface BindCheckPayload {
  passed?: boolean;
  result?: string;
  reason_code?: string;
}

export interface BindCockpitReceipt {
  bind_receipt_id: string;
  execution_intent_id?: string;
  decision_id?: string;
  target_path?: string;
  target_resource?: string;
  target_type?: string;
  final_outcome?: string;
  bind_reason_code?: string;
  bind_failure_reason?: string;
  occurred_at?: string;
  created_at?: string;
  policy_snapshot_id?: string;
  trust_log_id?: string;
  authority_check_result?: BindCheckPayload;
  constraint_check_result?: BindCheckPayload;
  drift_check_result?: BindCheckPayload;
  risk_check_result?: BindCheckPayload;
  [key: string]: unknown;
}

export interface CanonicalBindReceipt {
  bindReceiptId: string;
  executionIntentId: string | null;
  decisionId: string | null;
  policySnapshotId: string | null;
  trustLogId: string | null;
  targetPath: string;
  targetResource: string;
  targetType: string;
  targetPathType: CanonicalTargetPathType;
  outcome: CanonicalBindOutcome | "UNKNOWN";
  reasonCode: string;
  failureReason: string;
  timestamp: string;
  timestampMs: number;
  checks: {
    authority: "PASS" | "FAIL" | "UNKNOWN";
    constraint: "PASS" | "FAIL" | "UNKNOWN";
    drift: "PASS" | "FAIL" | "UNKNOWN";
    risk: "PASS" | "FAIL" | "UNKNOWN";
  };
  nextOperatorStep: string;
  raw: BindCockpitReceipt;
}

export interface BindReceiptListResponseMeta {
  count: number;
  returnedCount: number;
  hasMore: boolean;
  nextCursor: string | null;
  sort: "newest" | "oldest";
  limit: number | null;
  appliedFilters: Record<string, unknown>;
  totalCount: number | null;
}

export interface BindReceiptListParsedPayload {
  items: BindCockpitReceipt[];
  meta: BindReceiptListResponseMeta;
}

export interface BindFilterState {
  pathType: CanonicalTargetPathType | "all";
  outcome: CanonicalBindOutcome | "all";
  reasonCode: string;
  lineageQuery: string;
  failedOnly: boolean;
  recentOnly: boolean;
}

const CANONICAL_BIND_OUTCOMES: ReadonlySet<CanonicalBindOutcome> = new Set([
  "COMMITTED",
  "BLOCKED",
  "ESCALATED",
  "ROLLED_BACK",
  "APPLY_FAILED",
  "SNAPSHOT_FAILED",
  "PRECONDITION_FAILED",
]);

const TARGET_PATH_TYPE_MAP: Record<string, CanonicalTargetPathType> = {
  "/v1/governance/policy": "governance_policy_update",
  "/v1/governance/policy-bundles/promote": "policy_bundle_promotion",
  "/v1/compliance/config": "compliance_config_update",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function normalizeBindOutcome(outcome: unknown): CanonicalBindOutcome | "UNKNOWN" {
  if (typeof outcome !== "string") {
    return "UNKNOWN";
  }
  const normalized = outcome.trim().toUpperCase();
  if (normalized === "SUCCESS") {
    return "COMMITTED";
  }
  if (CANONICAL_BIND_OUTCOMES.has(normalized as CanonicalBindOutcome)) {
    return normalized as CanonicalBindOutcome;
  }
  return "UNKNOWN";
}

function normalizePathType(path: unknown): CanonicalTargetPathType {
  if (typeof path !== "string") {
    return "other";
  }
  return TARGET_PATH_TYPE_MAP[path] ?? "other";
}

function resolveCheck(value: unknown): "PASS" | "FAIL" | "UNKNOWN" {
  if (!isRecord(value)) {
    return "UNKNOWN";
  }
  if (typeof value.passed === "boolean") {
    return value.passed ? "PASS" : "FAIL";
  }
  if (typeof value.result === "string") {
    const normalized = value.result.trim().toUpperCase();
    if (["PASS", "OK", "ALLOW"].includes(normalized)) {
      return "PASS";
    }
    if (["FAIL", "DENY", "BLOCK"].includes(normalized)) {
      return "FAIL";
    }
  }
  return "UNKNOWN";
}

function pickString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim().length > 0) {
      return value.trim();
    }
  }
  return null;
}

function toTimestampMs(value: string): number {
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : 0;
}

export function resolveOperatorStep(
  outcome: CanonicalBindOutcome | "UNKNOWN",
  reasonCode: string,
): string {
  if (outcome === "COMMITTED") {
    return "Post-bind audit verification を実施し、TrustLog / evidence export を確認。";
  }
  if (outcome === "BLOCKED" || outcome === "PRECONDITION_FAILED") {
    return `Policy / approval / input assumptions を確認（reason_code: ${reasonCode || "-"}）。`;
  }
  if (outcome === "ESCALATED") {
    return "Human handoff: governance approver に bind receipt と execution intent を引き継ぐ。";
  }
  if (outcome === "ROLLED_BACK") {
    return "Rollback trigger と prior policy snapshot を確認し、再適用可否を判断。";
  }
  if (outcome === "APPLY_FAILED" || outcome === "SNAPSHOT_FAILED") {
    return "Runtime / snapshot integrity を調査し、根因特定後に再試行可否を判断。";
  }
  return "Bind receipt raw payload と trust lineage を確認して次の運用手順を判断。";
}

export function normalizeBindReceipt(receipt: BindCockpitReceipt): CanonicalBindReceipt {
  const outcome = normalizeBindOutcome(receipt.final_outcome);
  const reasonCode = pickString(
    receipt.bind_reason_code,
    receipt.authority_check_result?.reason_code,
    receipt.constraint_check_result?.reason_code,
    receipt.drift_check_result?.reason_code,
    receipt.risk_check_result?.reason_code,
  ) ?? "-";
  const failureReason = pickString(receipt.bind_failure_reason) ?? "-";
  const timestamp =
    pickString(receipt.occurred_at, receipt.created_at) ?? new Date(0).toISOString();

  return {
    bindReceiptId: pickString(receipt.bind_receipt_id) ?? "-",
    executionIntentId: pickString(receipt.execution_intent_id),
    decisionId: pickString(receipt.decision_id),
    policySnapshotId: pickString(receipt.policy_snapshot_id),
    trustLogId: pickString(receipt.trust_log_id),
    targetPath: pickString(receipt.target_path) ?? "-",
    targetResource: pickString(receipt.target_resource) ?? "-",
    targetType: pickString(receipt.target_type) ?? "-",
    targetPathType: normalizePathType(receipt.target_path),
    outcome,
    reasonCode,
    failureReason,
    timestamp,
    timestampMs: toTimestampMs(timestamp),
    checks: {
      authority: resolveCheck(receipt.authority_check_result),
      constraint: resolveCheck(receipt.constraint_check_result),
      drift: resolveCheck(receipt.drift_check_result),
      risk: resolveCheck(receipt.risk_check_result),
    },
    nextOperatorStep: resolveOperatorStep(outcome, reasonCode),
    raw: receipt,
  };
}

export function filterCanonicalReceipts(
  receipts: CanonicalBindReceipt[],
  filters: BindFilterState,
): CanonicalBindReceipt[] {
  const nowMs = Date.now();
  const recentWindowMs = 24 * 60 * 60 * 1000;
  const query = filters.lineageQuery.trim().toLowerCase();
  const reasonQuery = filters.reasonCode.trim().toLowerCase();

  return receipts.filter((receipt) => {
    if (filters.pathType !== "all" && receipt.targetPathType !== filters.pathType) {
      return false;
    }
    if (filters.outcome !== "all" && receipt.outcome !== filters.outcome) {
      return false;
    }
    if (filters.failedOnly && receipt.outcome === "COMMITTED") {
      return false;
    }
    if (filters.recentOnly && nowMs - receipt.timestampMs > recentWindowMs) {
      return false;
    }
    if (reasonQuery && !receipt.reasonCode.toLowerCase().includes(reasonQuery)) {
      return false;
    }
    if (query) {
      const haystacks = [
        receipt.bindReceiptId,
        receipt.executionIntentId ?? "",
        receipt.decisionId ?? "",
        receipt.policySnapshotId ?? "",
      ].map((value) => value.toLowerCase());
      if (!haystacks.some((value) => value.includes(query))) {
        return false;
      }
    }
    return true;
  });
}

export function parseBindReceiptListPayload(value: unknown): BindReceiptListParsedPayload {
  if (!isRecord(value) || !Array.isArray(value.items)) {
    return {
      items: [],
      meta: {
        count: 0,
        returnedCount: 0,
        hasMore: false,
        nextCursor: null,
        sort: "newest",
        limit: null,
        appliedFilters: {},
        totalCount: null,
      },
    };
  }

  const items = value.items.filter((item): item is BindCockpitReceipt => {
    return isRecord(item) && typeof item.bind_receipt_id === "string";
  });
  const nextCursor = typeof value.next_cursor === "string" ? value.next_cursor : null;
  const sort = value.sort === "oldest" ? "oldest" : "newest";
  const appliedFilters = isRecord(value.applied_filters) ? value.applied_filters : {};

  return {
    items,
    meta: {
      count: typeof value.count === "number" ? value.count : items.length,
      returnedCount: typeof value.returned_count === "number" ? value.returned_count : items.length,
      hasMore: Boolean(value.has_more),
      nextCursor,
      sort,
      limit: typeof value.limit === "number" ? value.limit : null,
      appliedFilters,
      totalCount: typeof value.total_count === "number" ? value.total_count : null,
    },
  };
}

export function parseBindReceiptDetailPayload(value: unknown): BindCockpitReceipt | null {
  if (!isRecord(value) || !isRecord(value.bind_receipt)) {
    return null;
  }
  const payload = value.bind_receipt;
  if (typeof payload.bind_receipt_id !== "string") {
    return null;
  }
  return payload as BindCockpitReceipt;
}
