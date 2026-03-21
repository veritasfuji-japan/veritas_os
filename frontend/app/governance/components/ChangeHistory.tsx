"use client";

import { Card } from "@veritas/design-system";
import { useI18n } from "../../../components/i18n-provider";
import type { HistoryEntry } from "../governance-types";

interface ChangeHistoryProps {
  entries: HistoryEntry[];
}

const ACTION_STYLE: Record<string, string> = {
  apply: "bg-success/20 text-success",
  rollback: "bg-warning/20 text-warning",
  approve: "bg-success/20 text-success",
  reject: "bg-danger/20 text-danger",
};

export function ChangeHistory({ entries }: ChangeHistoryProps): JSX.Element {
  const { t } = useI18n();

  return (
    <Card title="Change History" titleSize="md" variant="elevated">
      <ul className="space-y-1 text-xs">
        {entries.length === 0 ? (
          <li className="text-muted-foreground">{t("ポリシー操作後に変更履歴が表示されます。", "Change history will appear after policy operations.")}</li>
        ) : entries.map((entry) => (
          <li key={entry.id} className="rounded border px-2 py-1">
            <span className={`inline-flex items-center rounded px-1 py-0.5 text-[10px] font-semibold mr-1 ${ACTION_STYLE[entry.action] ?? "bg-muted text-muted-foreground"}`}>{entry.action}</span>
            <span className="text-muted-foreground">{entry.actor}</span> / {entry.summary} / <span className="font-mono">{entry.at}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
