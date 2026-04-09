"use client";

import { useI18n } from "../../../components/i18n-provider";
import type { DiffChange, GovernancePolicyUI } from "../governance-types";
import { DIFF_CATEGORY_LABELS } from "../constants";
import { collectChanges, isRecordObject } from "../helpers";

interface DiffPreviewProps {
  before: GovernancePolicyUI | null;
  after: GovernancePolicyUI | null;
}

export function DiffPreview({ before, after }: DiffPreviewProps): JSX.Element {
  const { t } = useI18n();
  const beforeRecord = isRecordObject(before) ? before : null;
  const afterRecord = isRecordObject(after) ? after : null;
  const rows = beforeRecord && afterRecord ? collectChanges("", beforeRecord, afterRecord) : [];
  if (rows.length === 0) return <p className="text-xs text-muted-foreground">{t("変更はありません。", "No changes.")}</p>;

  const grouped = rows.reduce<Record<string, DiffChange[]>>((acc, row) => {
    const cat = row.category;
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(row);
    return acc;
  }, {});
  const highImpactCount = rows.filter((row) => row.category === "threshold" || row.category === "escalation").length;

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">{t(`${rows.length} 件の変更を検出`, `${rows.length} change(s) detected`)}</p>
      {highImpactCount > 0 ? (
        <p className="rounded border border-warning/40 bg-warning/10 px-2 py-1 text-xs text-warning">
          {t(
            `高影響変更 ${highImpactCount} 件: risk threshold / auto-stop は承認前に再評価が必要です。`,
            `${highImpactCount} high-impact change(s): risk threshold and auto-stop updates require re-evaluation before approval.`,
          )}
        </p>
      ) : null}
      {(Object.keys(grouped) as DiffChange["category"][]).map((cat) => (
        <div key={cat}>
          <p className="mb-1 text-xs font-semibold text-muted-foreground">{DIFF_CATEGORY_LABELS[cat]}</p>
          <div className="space-y-1">
            {grouped[cat].map((row) => (
              <div key={row.path} className="rounded-md border px-3 py-1 text-xs">
                <p className="font-semibold">{row.path}</p>
                <div className="flex gap-2">
                  <span className="text-red-400 line-through">{row.old}</span>
                  <span className="text-green-400">{row.next}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
