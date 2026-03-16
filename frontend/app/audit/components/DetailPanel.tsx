"use client";

import { Card } from "@veritas/design-system";
import type { TrustLogItem } from "../../../lib/api-validators";
import { useI18n } from "../../../components/i18n-provider";
import {
  buildHumanSummary,
  getString,
  shortHash,
  toPrettyJson,
  type ChainResult,
  type DetailTab,
} from "../audit-types";
import { STATUS_BG, STATUS_COLORS } from "../constants";

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

interface DetailPanelProps {
  selected: TrustLogItem | null;
  selectedChain: ChainResult | null;
  previousEntry: TrustLogItem | null;
  nextEntry: TrustLogItem | null;
  detailTab: DetailTab;
  onDetailTabChange: (tab: DetailTab) => void;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function DetailPanel({
  selected,
  selectedChain,
  previousEntry,
  nextEntry,
  detailTab,
  onDetailTabChange,
}: DetailPanelProps): JSX.Element {
  const { t } = useI18n();

  const DETAIL_TABS: { value: DetailTab; label: string }[] = [
    { value: "summary", label: t("サマリー", "Summary") },
    { value: "metadata", label: t("メタデータ", "Metadata") },
    { value: "hash", label: t("ハッシュ", "Hash") },
    { value: "related", label: t("関連ID", "Related") },
    { value: "raw", label: "Raw JSON" },
  ];

  return (
    <Card title="Selected Audit" titleSize="md" variant="elevated">
      {selected ? (
        <div className="space-y-3 text-xs">
          {/* Tab bar */}
          <div className="flex gap-1 border-b border-border pb-1">
            {DETAIL_TABS.map((tab) => (
              <button
                key={tab.value}
                type="button"
                onClick={() => onDetailTabChange(tab.value)}
                className={`rounded-t px-3 py-1.5 text-xs transition-colors ${
                  detailTab === tab.value
                    ? "border-b-2 border-primary bg-primary/5 font-semibold"
                    : "text-muted-foreground hover:bg-muted/20"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab: Summary */}
          {detailTab === "summary" && (
            <div className="space-y-3">
              <div
                className={`rounded border p-3 ${selectedChain ? STATUS_BG[selectedChain.status] : "border-border"}`}
              >
                <p className="text-sm font-medium">
                  {buildHumanSummary(selected)}
                </p>
                {selectedChain && (
                  <p className="mt-1">
                    <span className="font-semibold">
                      {t("チェーン状態", "Chain status")}:
                    </span>{" "}
                    <span className={STATUS_COLORS[selectedChain.status]}>
                      {selectedChain.status.toUpperCase()}
                    </span>{" "}
                    — {selectedChain.reason}
                  </p>
                )}
              </div>
              <div className="grid gap-2 rounded border border-border p-3 md:grid-cols-2">
                <p>
                  <strong>Stage:</strong> {getString(selected, "stage")}
                </p>
                <p>
                  <strong>Status:</strong> {getString(selected, "status")}
                </p>
                <p>
                  <strong>Policy Version:</strong>{" "}
                  {getString(selected, "policy_version")}
                </p>
                <p>
                  <strong>Severity:</strong>{" "}
                  {getString(selected, "severity")}
                </p>
              </div>
            </div>
          )}

          {/* Tab: Metadata */}
          {detailTab === "metadata" && (
            <div className="rounded border border-border p-3">
              <p className="mb-2 font-semibold">
                {t("メタデータカード", "Metadata Card")}
              </p>
              <pre className="overflow-x-auto whitespace-pre-wrap rounded bg-muted/20 p-2 text-2xs">
                {toPrettyJson(selected.metadata ?? {})}
              </pre>
            </div>
          )}

          {/* Tab: Hash */}
          {detailTab === "hash" && (
            <div className="space-y-2">
              <div className="grid gap-2 md:grid-cols-3">
                <div className="rounded border border-border p-3 text-center">
                  <p className="text-2xs text-muted-foreground">
                    {t("前ログ", "Previous")}
                  </p>
                  <p className="mt-1 font-mono text-2xs">
                    {previousEntry
                      ? shortHash(previousEntry.sha256)
                      : t("なし", "none")}
                  </p>
                </div>
                <div
                  className={`rounded border p-3 text-center ${selectedChain ? STATUS_BG[selectedChain.status] : "border-border"}`}
                >
                  <p className="text-2xs font-semibold">
                    {t("現在", "Current")}
                  </p>
                  <p className="mt-1 font-mono text-2xs">
                    {shortHash(selected.sha256)}
                  </p>
                  <p className="mt-0.5 font-mono text-2xs text-muted-foreground">
                    prev: {shortHash(selected.sha256_prev)}
                  </p>
                </div>
                <div className="rounded border border-border p-3 text-center">
                  <p className="text-2xs text-muted-foreground">
                    {t("次ログ", "Next")}
                  </p>
                  <p className="mt-1 font-mono text-2xs">
                    {nextEntry
                      ? shortHash(nextEntry.sha256)
                      : t("なし", "none")}
                  </p>
                </div>
              </div>
              {selectedChain && selectedChain.status !== "verified" && (
                <div
                  className={`rounded border p-3 ${STATUS_BG[selectedChain.status]}`}
                >
                  <p className="font-semibold">
                    {selectedChain.status === "broken" &&
                      t(
                        "チェーン破損: ハッシュの不一致が検出されました。このエントリまたは前のエントリが改竄された可能性があります。",
                        "Chain broken: Hash mismatch detected. This entry or the previous one may have been tampered with.",
                      )}
                    {selectedChain.status === "missing" &&
                      t(
                        "ハッシュ欠損: 検証に必要なハッシュ値が存在しません。ログの欠落が考えられます。",
                        "Hash missing: A required hash value is absent. Log entries may be missing.",
                      )}
                    {selectedChain.status === "orphan" &&
                      t(
                        "孤立エントリ: 前のエントリが存在するにもかかわらず、sha256_prevが設定されていません。",
                        "Orphan entry: Previous entry exists but sha256_prev is not set on this entry.",
                      )}
                  </p>
                  <p className="mt-1 text-2xs">
                    {t("理由", "Reason")}: {selectedChain.reason}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Tab: Related IDs */}
          {detailTab === "related" && (
            <div className="grid gap-2 rounded border border-border p-3 md:grid-cols-2">
              <p>
                <strong>request_id:</strong>{" "}
                <span className="font-mono">
                  {selected.request_id ?? "-"}
                </span>
              </p>
              <p>
                <strong>decision_id:</strong>{" "}
                <span className="font-mono">
                  {String(selected.decision_id ?? "-")}
                </span>
              </p>
              <p>
                <strong>replay_id:</strong>{" "}
                {typeof selected.replay_id === "string" ? (
                  <a
                    className="font-mono underline"
                    href={`/replay?replay_id=${encodeURIComponent(selected.replay_id)}`}
                  >
                    {selected.replay_id}
                  </a>
                ) : (
                  "-"
                )}
              </p>
              <p>
                <strong>policy_version:</strong>{" "}
                <span className="font-mono">
                  {getString(selected, "policy_version")}
                </span>
              </p>
            </div>
          )}

          {/* Tab: Raw JSON */}
          {detailTab === "raw" && (
            <details open>
              <summary className="cursor-pointer font-semibold">
                {t("JSON 展開", "Expand JSON")}
              </summary>
              <pre className="mt-2 overflow-x-auto rounded border border-border bg-muted/20 p-3">
                {toPrettyJson(selected)}
              </pre>
            </details>
          )}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          {t(
            "タイムラインからログを選択すると、ここに詳細が表示されます。サマリー・メタデータ・ハッシュ検証・関連ID・生JSONの各タブで確認できます。",
            "Select a log from the timeline to see details. Tabs include summary, metadata, hash verification, related IDs, and raw JSON.",
          )}
        </p>
      )}
    </Card>
  );
}
