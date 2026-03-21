"use client";

import { Card } from "@veritas/design-system";
import { useI18n } from "../../../components/i18n-provider";
import type { TrustLogEntry } from "../governance-types";

interface TrustLogStreamProps {
  entries: TrustLogEntry[];
}

const SEVERITY_STYLE: Record<TrustLogEntry["severity"], string> = {
  warning: "bg-warning/20 text-warning",
  policy: "bg-info/20 text-info",
  info: "bg-muted text-muted-foreground",
};

export function TrustLogStream({ entries }: TrustLogStreamProps): JSX.Element {
  const { t } = useI18n();

  return (
    <Card title="TrustLog Stream" titleSize="md" variant="elevated">
      <ul className="space-y-1 text-xs">
        {entries.length === 0 ? (
          <li className="text-muted-foreground">{t("ポリシー読み込み後にストリームイベントが表示されます。", "Stream events will appear after loading a policy.")}</li>
        ) : entries.map((entry) => (
          <li key={entry.id} className={`rounded border px-2 py-1 ${entry.severity === "policy" ? "border-info/40 bg-info/5" : ""}`}>
            <span className="font-mono">{entry.at}</span>{" "}
            <span className={`inline-flex items-center rounded px-1 py-0.5 text-[10px] font-semibold ${SEVERITY_STYLE[entry.severity]}`}>{entry.severity}</span>{" "}
            {entry.message}
          </li>
        ))}
      </ul>
    </Card>
  );
}
