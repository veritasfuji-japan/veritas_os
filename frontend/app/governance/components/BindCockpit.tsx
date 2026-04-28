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

function summarizeBasis(items: unknown): string {
  if (!Array.isArray(items)) {
    return "-";
  }
  const values = items.filter((item): item is string => typeof item === "string");
  return values.length > 0 ? values.join(", ") : "-";
}

function countPredicates(items: unknown): number {
  if (!Array.isArray(items)) {
    return 0;
  }
  return items.filter((item) => typeof item === "object" && item !== null).length;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function formatStringList(items: unknown): string {
  if (!Array.isArray(items)) {
    return "-";
  }
  const values = items.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
  return values.length > 0 ? values.join(", ") : "-";
}

function pickStringField(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" && value.trim().length > 0 ? value : "-";
}

function hasPreBindSurface(detail: CanonicalBindReceipt): boolean {
  return (
    isRecord(detail.raw.pre_bind_detection_summary)
    || isRecord(detail.raw.pre_bind_preservation_summary)
    || isRecord(detail.raw.pre_bind_detection_detail)
    || isRecord(detail.raw.pre_bind_preservation_detail)
  );
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
                <dt>Audit Log</dt>
                <dd className="font-mono">{selectedDetail.bindReceiptId}</dd>
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
              </dl>

              <div className="rounded border border-border/70 bg-surface/20 px-2 py-2">
                <p className="font-semibold">Pre-bind governance surface</p>
                <p className="text-muted-foreground">
                  Upstream state before bind gate. Keep separate from bind_outcome.
                </p>
                {hasPreBindSurface(selectedDetail) ? (
                  <div className="mt-2 space-y-2">
                    <ol className="space-y-2">
                      <li className="rounded border border-border/60 bg-background/70 px-2 py-2">
                        <p className="font-semibold">1. participation (pre_bind_detection_summary)</p>
                        {isRecord(selectedDetail.raw.pre_bind_detection_summary) ? (
                          <div className="mt-1 space-y-1">
                            <p>participation_state: <span className="font-mono">{pickStringField(selectedDetail.raw.pre_bind_detection_summary, "participation_state")}</span></p>
                            <p>concise_rationale: <span>{pickStringField(selectedDetail.raw.pre_bind_detection_summary, "concise_rationale")}</span></p>
                            <p>primary_contributing_signals: <span>{formatStringList(selectedDetail.raw.pre_bind_detection_summary.primary_contributing_signals)}</span></p>
                          </div>
                        ) : (
                          <p className="text-muted-foreground">pre_bind_detection_summary is not present.</p>
                        )}
                      </li>
                      <li className="rounded border border-border/60 bg-background/70 px-2 py-2">
                        <p className="font-semibold">2. preservation (pre_bind_preservation_summary)</p>
                        {isRecord(selectedDetail.raw.pre_bind_preservation_summary) ? (
                          <div className="mt-1 space-y-1">
                            <p>preservation_state: <span className="font-mono">{pickStringField(selectedDetail.raw.pre_bind_preservation_summary, "preservation_state")}</span></p>
                            <p>intervention_viability: <span className="font-mono">{pickStringField(selectedDetail.raw.pre_bind_preservation_summary, "intervention_viability")}</span></p>
                            <p>concise_rationale: <span>{pickStringField(selectedDetail.raw.pre_bind_preservation_summary, "concise_rationale")}</span></p>
                            <p>main_contributing_conditions: <span>{formatStringList(selectedDetail.raw.pre_bind_preservation_summary.main_contributing_conditions)}</span></p>
                          </div>
                        ) : (
                          <p className="text-muted-foreground">pre_bind_preservation_summary is not present.</p>
                        )}
                      </li>
                      <li className="rounded border border-border/60 bg-background/70 px-2 py-2">
                        <p className="font-semibold">3. bind gate (bind_outcome)</p>
                        <p>bind_outcome: <span className="font-mono">{selectedDetail.outcome}</span></p>
                        <p>bind_reason_code: <span className="font-mono">{selectedDetail.reasonCode}</span></p>
                      </li>
                    </ol>
                  </div>
                ) : (
                  <p className="mt-2 text-muted-foreground">
                    pre_bind_detection_summary / pre_bind_preservation_summary are absent in this bind receipt payload.
                  </p>
                )}
              </div>

              <div className="rounded border border-border/70 bg-surface/40 px-2 py-2">
                <p className="font-semibold">Bind-time governance surface</p>
                <p className="text-muted-foreground">Bind checks and artifacts after gate adjudication.</p>
              </div>
              <div className="rounded border border-border/70 bg-surface/40 px-2 py-2">
                <p className="font-semibold">Action Contract</p>
                <p className="font-mono">{String(selectedDetail.raw.action_contract_id ?? "-")}</p>
              </div>
              <div className="rounded border border-border/70 bg-surface/40 px-2 py-2">
                <p className="font-semibold">Authority Evidence</p>
                <p className="font-mono">
                  id: {String(selectedDetail.raw.authority_evidence_id ?? "-")} / validation: {String(selectedDetail.raw.authority_validation_status ?? "-")}
                </p>
              </div>
              <div className="rounded border border-border/70 bg-surface/40 px-2 py-2">
                <p className="font-semibold">Runtime Authority</p>
                <p className="font-mono">
                  authority {selectedDetail.checks.authority} / constraint {selectedDetail.checks.constraint} / drift {selectedDetail.checks.drift} / risk {selectedDetail.checks.risk}
                </p>
              </div>
              <div className="rounded border border-border/70 bg-surface/40 px-2 py-2">
                <p className="font-semibold">Predicate Results</p>
                <p className="font-mono">
                  Failed Predicates: {countPredicates(selectedDetail.raw.failed_predicates)} / Stale Predicates: {countPredicates(selectedDetail.raw.stale_predicates)} / Missing Predicates: {countPredicates(selectedDetail.raw.missing_predicates)}
                </p>
              </div>
              <div className="rounded border border-border/70 bg-surface/40 px-2 py-2">
                <p className="font-semibold">Commit Boundary Result</p>
                <p className="font-mono">{String(selectedDetail.raw.commit_boundary_result ?? "-")}</p>
              </div>
              <div className="rounded border border-border/70 bg-surface/40 px-2 py-2">
                <p className="font-semibold">Refusal Basis</p>
                <p>{summarizeBasis(selectedDetail.raw.refusal_basis)}</p>
              </div>
              <div className="rounded border border-border/70 bg-surface/40 px-2 py-2">
                <p className="font-semibold">Escalation Basis</p>
                <p>{summarizeBasis(selectedDetail.raw.escalation_basis)}</p>
              </div>
              <div className="rounded border border-border/70 bg-surface/40 px-2 py-2">
                <p className="font-semibold">Irreversibility Boundary</p>
                <p className="font-mono">{String(selectedDetail.raw.irreversibility_boundary_id ?? "-")}</p>
              </div>

              <details>
                <summary className="cursor-pointer text-muted-foreground">Expanded governance detail</summary>
                <div className="mt-2 rounded border border-border/60 bg-background/70 p-2 text-[11px]">
                  <p className="font-mono">authority_evidence_hash: {String(selectedDetail.raw.authority_evidence_hash ?? "-")}</p>
                  <p className="font-mono">failed_predicates: {JSON.stringify(selectedDetail.raw.failed_predicates ?? [])}</p>
                  <p className="font-mono">stale_predicates: {JSON.stringify(selectedDetail.raw.stale_predicates ?? [])}</p>
                  <p className="font-mono">missing_predicates: {JSON.stringify(selectedDetail.raw.missing_predicates ?? [])}</p>
                </div>
              </details>

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
