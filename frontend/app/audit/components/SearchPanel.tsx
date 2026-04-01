"use client";

import { type Dispatch, type SetStateAction } from "react";
import { Card } from "@veritas/design-system";
import type { RequestLogResponse } from "@veritas/types";
import { useI18n } from "../../../components/i18n-provider";
import type { CrossSearchParams, SearchField } from "../audit-types";

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

interface SearchPanelProps {
  /* request ID search */
  requestId: string;
  onRequestIdChange: (v: string) => void;
  requestResult: RequestLogResponse | null;
  onSearchByRequestId: () => void;

  /* cross-search */
  crossSearch: CrossSearchParams;
  onCrossSearchChange: Dispatch<SetStateAction<CrossSearchParams>>;
  filteredCount: number;

  /* connection */
  loading: boolean;
  hasMore: boolean;
  cursor: string | null;
  onLoadLogs: (nextCursor: string | null, replace: boolean) => void;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function SearchPanel({
  requestId,
  onRequestIdChange,
  requestResult,
  onSearchByRequestId,
  crossSearch,
  onCrossSearchChange,
  filteredCount,
  loading,
  hasMore,
  cursor,
  onLoadLogs,
}: SearchPanelProps): JSX.Element {
  const { t } = useI18n();

  const SEARCH_FIELDS: { value: SearchField; label: string }[] = [
    { value: "all", label: t("すべて", "All fields") },
    { value: "decision_id", label: "decision_id" },
    { value: "request_id", label: "request_id" },
    { value: "replay_id", label: "replay_id" },
    { value: "policy_version", label: "policy_version" },
  ];

  return (
    <>
      {/* Connection */}
      <Card
        title={t("接続・読み込み", "Connection")}
        titleSize="sm"
        variant="elevated"
      >
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-lg border border-primary/40 bg-primary/10 px-4 py-2 text-sm"
            disabled={loading}
            onClick={() => onLoadLogs(null, true)}
          >
            {loading
              ? t("読み込み中...", "Loading...")
              : t("最新ログを読み込み", "Load latest logs")}
          </button>
          <button
            type="button"
            className="rounded-lg border border-border px-4 py-2 text-sm"
            disabled={loading || !hasMore || !cursor}
            onClick={() => onLoadLogs(cursor, false)}
          >
            {t("追加読み込み", "Load more")}
          </button>
        </div>
      </Card>

      {/* request_id search */}
      <Card
        title={t("request_id 検索", "request_id Search")}
        titleSize="sm"
        variant="elevated"
      >
        <div className="flex gap-2">
          <input
            aria-label={t("リクエストIDで検索", "Search by request ID")}
            className="w-full rounded-lg border border-border px-3 py-2 text-sm"
            value={requestId}
            onChange={(e) => onRequestIdChange(e.target.value)}
            placeholder="request_id"
          />
          <button
            type="button"
            className="rounded-lg border border-primary/40 bg-primary/10 px-4 py-2 text-sm"
            disabled={loading}
            onClick={onSearchByRequestId}
          >
            {t("検索", "Search")}
          </button>
        </div>
        {requestResult ? (
          <p className="mt-2 text-xs">
            count: {requestResult.count} / chain_ok:{" "}
            {String(requestResult.chain_ok)} / result:{" "}
            {requestResult.verification_result}
          </p>
        ) : null}
      </Card>

      {/* Cross-search */}
      <Card
        title={t("横断検索", "Cross-search")}
        titleSize="sm"
        variant="elevated"
      >
        <div className="flex gap-2">
          <select
            aria-label={t("検索フィールド", "Search field")}
            className="rounded-lg border border-border px-2 py-2 text-sm"
            value={crossSearch.field}
            onChange={(e) =>
              onCrossSearchChange((prev) => ({
                ...prev,
                field: e.target.value as SearchField,
              }))
            }
          >
            {SEARCH_FIELDS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
          <input
            aria-label="cross-search"
            className="w-full rounded-lg border border-border px-3 py-2 text-sm"
            value={crossSearch.query}
            onChange={(e) =>
              onCrossSearchChange((prev) => ({ ...prev, query: e.target.value }))
            }
            placeholder={t(
              "ID・ポリシーバージョンで検索",
              "Search by ID or policy version",
            )}
          />
        </div>
        {crossSearch.query && (
          <p className="mt-1 text-xs text-muted-foreground">
            {t("一致", "Matches")}: {filteredCount}
          </p>
        )}
      </Card>
    </>
  );
}
