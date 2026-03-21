"use client";

import { Card } from "@veritas/design-system";
import { useI18n } from "../../../components/i18n-provider";
import { classifyChain, getString, type DetailTab } from "../audit-types";
import { STATUS_COLORS, STATUS_DOT } from "../constants";
import type { TrustLogItem } from "../../../lib/api-validators";

interface AuditTimelineProps {
  filteredItems: TrustLogItem[];
  stageFilter: string;
  stageOptions: string[];
  selected: TrustLogItem | null;
  onStageFilterChange: (value: string) => void;
  onSelect: (item: TrustLogItem) => void;
  onDetailTabChange: (tab: DetailTab) => void;
}

export function AuditTimeline({
  filteredItems,
  stageFilter,
  stageOptions,
  selected,
  onStageFilterChange,
  onSelect,
  onDetailTabChange,
}: AuditTimelineProps): JSX.Element {
  const { t } = useI18n();

  return (
    <Card title="Timeline" titleSize="md" variant="elevated">
      <div className="mb-2 flex items-center gap-2">
        <label htmlFor="stage-filter" className="text-xs">Stage</label>
        <select
          id="stage-filter"
          value={stageFilter}
          onChange={(e) => onStageFilterChange(e.target.value)}
          className="rounded border border-border px-2 py-1 text-xs"
        >
          {stageOptions.map((stage) => (
            <option key={stage} value={stage}>{stage}</option>
          ))}
        </select>
        <span className="ml-auto text-xs">
          {t("表示件数", "Visible")}: {filteredItems.length}
        </span>
      </div>

      {filteredItems.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          {t(
            "監査対象が未読込です。request_id/decision_id・ハッシュ整合・リプレイ関連をここで確認できます。",
            "No logs loaded yet. This timeline verifies request/decision IDs, hash chain, and replay linkage.",
          )}
        </p>
      ) : null}

      {/* Column header */}
      {filteredItems.length > 0 && (
        <div className="mb-1 grid grid-cols-2 gap-1 px-3 text-2xs font-semibold text-muted-foreground md:grid-cols-7">
          <span>{t("重要度", "Severity")}</span>
          <span>Stage</span>
          <span>{t("タイムスタンプ", "Timestamp")}</span>
          <span>request_id</span>
          <span>decision_id</span>
          <span>{t("チェーン", "Chain")}</span>
          <span>Replay</span>
        </div>
      )}

      <ol className="space-y-1">
        {filteredItems.map((item, index) => {
          const chain = classifyChain(item, filteredItems[index + 1] ?? null);
          const isSelected = selected === item;
          const timelineKey = [
            item.request_id ?? "unknown",
            String(item.decision_id ?? "no-decision"),
            item.created_at ?? "no-timestamp",
            item.sha256 ?? "no-sha",
            item.sha256_prev ?? "no-prev-sha",
          ].join("-");
          return (
            <li key={timelineKey}>
              <button
                type="button"
                onClick={() => {
                  onSelect(item);
                  onDetailTabChange("summary");
                }}
                className={`w-full rounded border px-3 py-2 text-left text-xs transition-colors ${
                  isSelected
                    ? "border-primary/50 bg-primary/5"
                    : "border-border hover:bg-muted/30"
                }`}
              >
                <div className="grid grid-cols-2 gap-1 md:grid-cols-7">
                  <span className="font-medium">{getString(item, "severity")}</span>
                  <span>{getString(item, "stage")}</span>
                  <span className="font-mono text-2xs">{item.created_at ?? "-"}</span>
                  <span className="truncate font-mono text-2xs">{item.request_id ?? "-"}</span>
                  <span className="truncate font-mono text-2xs">{String(item.decision_id ?? "-")}</span>
                  <span className="flex items-center gap-1">
                    <span className={`inline-block h-2 w-2 rounded-full ${STATUS_DOT[chain.status]}`} />
                    <span className={STATUS_COLORS[chain.status]}>{chain.status}</span>
                  </span>
                  <span className="text-2xs">
                    {typeof item.replay_id === "string" ? "linked" : "-"}
                  </span>
                </div>
              </button>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
