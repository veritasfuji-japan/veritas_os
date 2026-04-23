"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card } from "@veritas/design-system";
import { StatusBadge } from "../../../components/ui";
import { veritasFetch } from "../../../lib/api-client";
import {
  type BindTargetCatalogEntry,
  type BindFilterState,
  type CanonicalBindReceipt,
  normalizeBindReceipt,
  parseBindReceiptDetailPayload,
  parseBindReceiptListPayload,
} from "./bind-cockpit-normalization";

const DEFAULT_FILTERS: BindFilterState = {
  pathType: "all",
  outcome: "all",
  reasonCode: "",
  lineageQuery: "",
  failedOnly: false,
  recentOnly: false,
};

const DEFAULT_LIST_LIMIT = 50;

const FALLBACK_TARGET_CATALOG: BindTargetCatalogEntry[] = [];

function deriveCatalogFromReceipts(receipts: CanonicalBindReceipt[]): BindTargetCatalogEntry[] {
  const deduped = new Map<string, BindTargetCatalogEntry>();
  receipts.forEach((receipt) => {
    if (!receipt.targetPath || receipt.targetPath === "-" || receipt.targetPathType === "other") {
      return;
    }
    const key = `${receipt.targetPathType}::${receipt.targetPath}::${receipt.targetType}`;
    if (deduped.has(key)) {
      return;
    }
    deduped.set(key, {
      targetPath: receipt.targetPath,
      targetType: receipt.targetType === "-" ? "" : receipt.targetType,
      targetPathType: receipt.targetPathType,
      label: receipt.targetLabel || receipt.targetPathType.replaceAll("_", " "),
      operatorSurface: receipt.operatorSurface || "audit",
      relevantUiHref: receipt.relevantUiHref || "/audit",
      supportsFiltering: true,
    });
  });
  return Array.from(deduped.values());
}

function buildBindReceiptListQuery(
  filters: BindFilterState,
  targetCatalog: BindTargetCatalogEntry[],
  cursor?: string | null,
): string {
  const params = new URLSearchParams();
  params.set("sort", "newest");
  params.set("limit", String(DEFAULT_LIST_LIMIT));

  if (filters.pathType !== "all" && filters.pathType !== "other") {
    const matched = targetCatalog.find((entry) => entry.targetPathType === filters.pathType);
    if (matched?.targetPath) {
      params.set("target_path", matched.targetPath);
    }
  }
  if (filters.outcome !== "all") {
    params.set("outcome", filters.outcome);
  }
  if (filters.reasonCode.trim()) {
    params.set("reason_code", filters.reasonCode.trim());
  }
  if (filters.lineageQuery.trim()) {
    params.set("lineage_query", filters.lineageQuery.trim());
  }
  if (filters.failedOnly) {
    params.set("failed_only", "true");
  }
  if (filters.recentOnly) {
    params.set("recent_only", "true");
  }
  if (cursor) {
    params.set("cursor", cursor);
  }

  return params.toString();
}

function isSameCatalog(left: BindTargetCatalogEntry[], right: BindTargetCatalogEntry[]): boolean {
  if (left.length !== right.length) {
    return false;
  }
  return left.every((entry, index) => {
    const candidate = right[index];
    return (
      entry.targetPath === candidate?.targetPath
      && entry.targetType === candidate?.targetType
      && entry.targetPathType === candidate?.targetPathType
      && entry.label === candidate?.label
      && entry.operatorSurface === candidate?.operatorSurface
      && entry.relevantUiHref === candidate?.relevantUiHref
      && entry.supportsFiltering === candidate?.supportsFiltering
    );
  });
}

function resolveOutcomeVariant(
  outcome: CanonicalBindReceipt["outcome"],
): "success" | "warning" | "danger" | "muted" {
  if (outcome === "COMMITTED") {
    return "success";
  }
  if (outcome === "BLOCKED" || outcome === "ROLLED_BACK" || outcome === "PRECONDITION_FAILED") {
    return "warning";
  }
  if (outcome === "ESCALATED" || outcome === "APPLY_FAILED" || outcome === "SNAPSHOT_FAILED") {
    return "danger";
  }
  return "muted";
}

function isActionRequiredOutcome(outcome: CanonicalBindReceipt["outcome"]): boolean {
  return outcome === "BLOCKED" || outcome === "ESCALATED";
}

/**
 * Bind Cockpit: operator-facing cross-path surface for bind lifecycle triage.
 */
export function BindCockpit(): JSX.Element {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [filters, setFilters] = useState<BindFilterState>(DEFAULT_FILTERS);
  const [receipts, setReceipts] = useState<CanonicalBindReceipt[]>([]);
  const [selectedReceiptId, setSelectedReceiptId] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<CanonicalBindReceipt | null>(null);
  const [returnedCount, setReturnedCount] = useState(0);
  const [totalCount, setTotalCount] = useState<number | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [currentSort, setCurrentSort] = useState<"newest" | "oldest">("newest");
  const [targetCatalog, setTargetCatalog] = useState<BindTargetCatalogEntry[]>(FALLBACK_TARGET_CATALOG);

  const effectiveCatalog = useMemo(() => {
    if (targetCatalog.length > 0) {
      return targetCatalog;
    }
    const derived = deriveCatalogFromReceipts(receipts);
    return derived.length > 0 ? derived : FALLBACK_TARGET_CATALOG;
  }, [receipts, targetCatalog]);

  const exportUrl = useMemo(
    () => `/api/veritas/v1/governance/bind-receipts/export?${buildBindReceiptListQuery(filters, targetCatalog)}`,
    [filters, targetCatalog],
  );

  const loadReceipts = useCallback(async (cursor?: string | null, append = false): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const query = buildBindReceiptListQuery(filters, targetCatalog, cursor);
      const response = await veritasFetch(`/api/veritas/v1/governance/bind-receipts?${query}`);
      if (!response.ok) {
        setError(`HTTP ${response.status}: Failed to load bind receipts.`);
        if (!append) {
          setReceipts([]);
        }
        return;
      }
      const payload = parseBindReceiptListPayload(await response.json());
      const normalized = payload.items.map(normalizeBindReceipt);
      if (payload.targetCatalog.length > 0 && !isSameCatalog(payload.targetCatalog, targetCatalog)) {
        setTargetCatalog(payload.targetCatalog);
      }
      setReturnedCount(payload.meta.returnedCount);
      setTotalCount(payload.meta.totalCount);
      setHasMore(payload.meta.hasMore);
      setNextCursor(payload.meta.nextCursor);
      setCurrentSort(payload.meta.sort);
      setReceipts((prev) => (append ? [...prev, ...normalized] : normalized));
    } catch (caught: unknown) {
      console.error("loadReceipts failed", caught);
      setError("Network error: failed to load bind receipts.");
      if (!append) {
        setReceipts([]);
      }
    } finally {
      setLoading(false);
    }
  }, [filters, targetCatalog]);

  useEffect(() => {
    void loadReceipts(null, false);
    // targetCatalog update alone should not retrigger list fetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters]);

  useEffect(() => {
    if (receipts.length > 0 && !selectedReceiptId) {
      setSelectedReceiptId(receipts[0].bindReceiptId);
    }
  }, [receipts, selectedReceiptId]);

  useEffect(() => {
    if (!selectedReceiptId) {
      setSelectedDetail(null);
      return;
    }
    setDetailError(null);
    void (async () => {
      try {
        const response = await veritasFetch(`/api/veritas/v1/governance/bind-receipts/${selectedReceiptId}`);
        if (!response.ok) {
          setDetailError(`HTTP ${response.status}: Failed to load bind receipt detail.`);
          setSelectedDetail(null);
          return;
        }
        const payload = parseBindReceiptDetailPayload(await response.json());
        if (!payload) {
          setDetailError("Bind receipt detail payload is malformed.");
          setSelectedDetail(null);
          return;
        }
        setSelectedDetail(normalizeBindReceipt(payload));
      } catch (caught: unknown) {
        console.error("loadReceiptDetail failed", caught);
        setDetailError("Network error: failed to load bind receipt detail.");
        setSelectedDetail(null);
      }
    })();
  }, [selectedReceiptId]);

  const filterableCatalog = useMemo(
    () => effectiveCatalog.filter((entry) => entry.supportsFiltering && entry.targetPathType !== "other"),
    [effectiveCatalog],
  );

  const filteredReceipts = useMemo(() => {
    if (filters.pathType !== "other") {
      return receipts;
    }
    return receipts.filter((receipt) => receipt.targetPathType === "other");
  }, [receipts, filters.pathType]);

  const blockedOrEscalatedReceipts = useMemo(
    () => filteredReceipts.filter((receipt) => isActionRequiredOutcome(receipt.outcome)).slice(0, 5),
    [filteredReceipts],
  );

  return (
    <Card
      title="Bind Cockpit"
      description="Cross-path operator surface for bind outcomes, lineage triage, and bind receipt drill-down."
      titleSize="md"
      variant="elevated"
    >
      <div className="space-y-4">
        <div className="grid gap-2 md:grid-cols-4">
          <label className="text-xs">
            path type
            <select
              aria-label="bind-path-type"
              className="mt-1 w-full rounded border px-2 py-1"
              value={filters.pathType}
              onChange={(event) => {
                setFilters((prev) => ({
                  ...prev,
                  pathType: event.target.value as BindFilterState["pathType"],
                }));
              }}
            >
              <option value="all">all</option>
              {filterableCatalog.map((entry) => (
                <option key={entry.targetPathType} value={entry.targetPathType}>
                  {entry.label}
                </option>
              ))}
              <option value="other">other</option>
            </select>
          </label>
          <label className="text-xs">
            outcome
            <select
              aria-label="bind-outcome"
              className="mt-1 w-full rounded border px-2 py-1"
              value={filters.outcome}
              onChange={(event) => {
                setFilters((prev) => ({
                  ...prev,
                  outcome: event.target.value as BindFilterState["outcome"],
                }));
              }}
            >
              <option value="all">all</option>
              <option value="COMMITTED">COMMITTED</option>
              <option value="BLOCKED">BLOCKED</option>
              <option value="ESCALATED">ESCALATED</option>
              <option value="ROLLED_BACK">ROLLED_BACK</option>
              <option value="APPLY_FAILED">APPLY_FAILED</option>
              <option value="SNAPSHOT_FAILED">SNAPSHOT_FAILED</option>
              <option value="PRECONDITION_FAILED">PRECONDITION_FAILED</option>
            </select>
          </label>
          <label className="text-xs">
            reason code
            <input
              aria-label="bind-reason-code"
              className="mt-1 w-full rounded border px-2 py-1"
              value={filters.reasonCode}
              onChange={(event) => {
                setFilters((prev) => ({ ...prev, reasonCode: event.target.value }));
              }}
            />
          </label>
          <label className="text-xs">
            lineage id search
            <input
              aria-label="bind-lineage-search"
              className="mt-1 w-full rounded border px-2 py-1"
              placeholder="decision / execution_intent / bind_receipt"
              value={filters.lineageQuery}
              onChange={(event) => {
                setFilters((prev) => ({ ...prev, lineageQuery: event.target.value }));
              }}
            />
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <label>
            <input
              aria-label="failed-only"
              type="checkbox"
              checked={filters.failedOnly}
              onChange={(event) => {
                setFilters((prev) => ({ ...prev, failedOnly: event.target.checked }));
              }}
            />
            <span className="ml-1">failed only</span>
          </label>
          <label>
            <input
              aria-label="recent-only"
              type="checkbox"
              checked={filters.recentOnly}
              onChange={(event) => {
                setFilters((prev) => ({ ...prev, recentOnly: event.target.checked }));
              }}
            />
            <span className="ml-1">recent only (24h)</span>
          </label>
          <button
            type="button"
            className="rounded border px-2 py-1"
            onClick={() => void loadReceipts(null, false)}
            disabled={loading}
          >
            {loading ? "loading..." : "refresh receipts"}
          </button>
          <span className="text-muted-foreground">returned {returnedCount} / total {totalCount ?? filteredReceipts.length} (sort: {currentSort})</span>
          <span className="text-muted-foreground">{hasMore ? "more available" : "end of results"}</span>
          <a className="rounded border px-2 py-1" href={exportUrl}>
            export current filtered set (json)
          </a>
        </div>

        {error ? <p className="rounded border border-danger/30 bg-danger/10 px-2 py-1 text-xs">{error}</p> : null}

        {blockedOrEscalatedReceipts.length > 0 ? (
          <div className="rounded border border-warning/40 bg-warning/10 p-3">
            <h4 className="text-sm font-semibold">Blocked / Escalated queue</h4>
            <p className="mt-1 text-xs text-muted-foreground">
              Why it is blocked and what to inspect next.
            </p>
            <ul className="mt-2 space-y-2 text-xs">
              {blockedOrEscalatedReceipts.map((receipt) => (
                <li key={`action-required-${receipt.bindReceiptId}`} className="rounded border border-warning/30 bg-background/80 px-2 py-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge label={receipt.outcome} variant={resolveOutcomeVariant(receipt.outcome)} />
                    <span className="font-mono">{receipt.bindReceiptId}</span>
                    <span className="text-muted-foreground">reason_code: {receipt.reasonCode}</span>
                  </div>
                  <p className="mt-1">
                    {receipt.failureReason !== "-" ? receipt.failureReason : "No bind_failure_reason; inspect detail checks."}
                  </p>
                  <button
                    type="button"
                    className="mt-2 rounded border px-2 py-1"
                    onClick={() => {
                      setSelectedReceiptId(receipt.bindReceiptId);
                    }}
                  >
                    inspect blocked/escalated reason
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="overflow-x-auto rounded border">
          <table className="w-full min-w-[980px] text-xs">
            <thead className="bg-surface/50">
              <tr>
                <th className="px-2 py-2 text-left">timestamp</th>
                <th className="px-2 py-2 text-left">target path / type</th>
                <th className="px-2 py-2 text-left">bind_outcome</th>
                <th className="px-2 py-2 text-left">bind_reason_code</th>
                <th className="px-2 py-2 text-left">bind_receipt_id</th>
                <th className="px-2 py-2 text-left">execution_intent_id</th>
                <th className="px-2 py-2 text-left">decision_id</th>
              </tr>
            </thead>
            <tbody>
              {filteredReceipts.map((receipt) => (
                <tr
                  key={receipt.bindReceiptId}
                  className={[
                    "cursor-pointer border-t",
                    selectedReceiptId === receipt.bindReceiptId ? "bg-primary/5" : "hover:bg-surface/20",
                  ].join(" ")}
                  onClick={() => {
                    setSelectedReceiptId(receipt.bindReceiptId);
                  }}
                >
                  <td className="px-2 py-2 font-mono">{receipt.timestamp}</td>
                  <td className="px-2 py-2">
                    <div className="font-mono">{receipt.targetPath}</div>
                    <div className="text-muted-foreground">{receipt.targetLabel}</div>
                  </td>
                  <td className="px-2 py-2">
                    <StatusBadge label={receipt.outcome} variant={resolveOutcomeVariant(receipt.outcome)} />
                  </td>
                  <td className="px-2 py-2 font-mono">{receipt.reasonCode}</td>
                  <td className="px-2 py-2 font-mono">{receipt.bindReceiptId}</td>
                  <td className="px-2 py-2 font-mono">{receipt.executionIntentId ?? "-"}</td>
                  <td className="px-2 py-2 font-mono">{receipt.decisionId ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!loading && filteredReceipts.length === 0 ? (
            <p className="px-3 py-4 text-xs text-muted-foreground">
              No bind receipts matched filters. Check path/outcome filters or refresh.
            </p>
          ) : null}
        </div>
        <div className="flex items-center gap-2 text-xs">
          <button
            type="button"
            className="rounded border px-2 py-1"
            disabled={!hasMore || loading || !nextCursor}
            onClick={() => void loadReceipts(nextCursor, true)}
          >
            load more receipts
          </button>
          <span className="text-muted-foreground">{hasMore ? "has more pages" : "no more pages"}</span>
        </div>

        <div className="rounded border p-3">
          <h4 className="text-sm font-semibold">Receipt Drill-down</h4>
          {detailError ? <p className="mt-2 text-xs text-danger">{detailError}</p> : null}
          {!selectedDetail && !detailError ? (
            <p className="mt-2 text-xs text-muted-foreground">Select a bind receipt row to inspect detail.</p>
          ) : null}
          {selectedDetail ? (
            <div className="mt-2 space-y-2 text-xs">
              <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1">
                <dt>bind_outcome</dt>
                <dd><StatusBadge label={selectedDetail.outcome} variant={resolveOutcomeVariant(selectedDetail.outcome)} /></dd>
                <dt>bind_failure_reason</dt>
                <dd>{selectedDetail.failureReason}</dd>
                <dt>bind_reason_code</dt>
                <dd className="font-mono">{selectedDetail.reasonCode}</dd>
                <dt>governance lineage</dt>
                <dd className="font-mono">
                  decision:{selectedDetail.decisionId ?? "-"} / execution_intent:{selectedDetail.executionIntentId ?? "-"}
                </dd>
                <dt>check summary</dt>
                <dd className="font-mono">
                  authority {selectedDetail.checks.authority} / constraint {selectedDetail.checks.constraint} / drift {selectedDetail.checks.drift} / risk {selectedDetail.checks.risk}
                </dd>
              </dl>

              <div className="rounded border border-warning/30 bg-warning/10 px-2 py-2">
                <p className="font-semibold">Next operator step</p>
                <p>{selectedDetail.nextOperatorStep}</p>
              </div>

              <div className="flex flex-wrap gap-2">
                {selectedDetail.decisionId ? (
                  <a className="rounded border px-2 py-1" href={`/audit?decision_id=${encodeURIComponent(selectedDetail.decisionId)}`}>
                    related decision
                  </a>
                ) : null}
                {selectedDetail.executionIntentId ? (
                  <a className="rounded border px-2 py-1" href={`/audit?cross=${encodeURIComponent(selectedDetail.executionIntentId)}`}>
                    related execution intent
                  </a>
                ) : null}
                <a className="rounded border px-2 py-1" href={`/audit?bind_receipt_id=${encodeURIComponent(selectedDetail.bindReceiptId)}`}>
                  related bind receipt
                </a>
                <a className="rounded border px-2 py-1" href="/audit">
                  trust / audit explorer
                </a>
                <a className="rounded border px-2 py-1" href={selectedDetail.relevantUiHref}>
                  relevant governance/compliance surface
                </a>
              </div>

              <details>
                <summary className="cursor-pointer text-muted-foreground">bind receipt raw payload</summary>
                <pre className="mt-1 max-h-60 overflow-auto rounded border bg-surface/40 p-2 font-mono text-[10px]">
                  {JSON.stringify(selectedDetail.raw, null, 2)}
                </pre>
              </details>
            </div>
          ) : null}
        </div>
      </div>
    </Card>
  );
}
