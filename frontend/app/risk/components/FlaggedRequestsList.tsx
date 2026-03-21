"use client";

import { memo } from "react";
import Link from "next/link";
import { useI18n } from "../../../components/i18n-provider";
import type { FlaggedEntry } from "../risk-types";
import { SEVERITY_CLASSES, STATUS_LABELS } from "../constants";

interface FlaggedRequestsListProps {
  entries: FlaggedEntry[];
  selectedPointId: string | null;
  onSelectPoint: (id: string) => void;
}

export const FlaggedRequestsList = memo(function FlaggedRequestsList({ entries, selectedPointId, onSelectPoint }: FlaggedRequestsListProps): JSX.Element {
  const { t } = useI18n();

  return (
    <div className="rounded-lg border border-border/50 bg-background/60 p-3 text-xs">
      <p className="mb-2 font-semibold">Flagged requests</p>
      {entries.length === 0 ? (
        <div className="rounded-lg border border-border/30 bg-muted/10 px-3 py-4 text-center text-muted-foreground" data-testid="empty-flagged">
          <p className="text-sm font-medium">{t("監視中", "Monitoring active")}</p>
          <p className="mt-1 text-[11px]">{t("現在フラグされたリクエストはありません。リアルタイムで監視を継続しています。", "No flagged requests in this window. Real-time monitoring continues.")}</p>
        </div>
      ) : (
        <ul className="max-h-64 space-y-2 overflow-auto pr-1">
          {entries.map((entry) => (
            <li key={entry.point.id}>
              <button
                type="button"
                onClick={() => onSelectPoint(entry.point.id)}
                className={`w-full rounded border px-2 py-1.5 text-left hover:bg-muted/30 ${selectedPointId === entry.point.id ? "ring-1 ring-primary/50 bg-muted/20" : "border-border/40"}`}
              >
                <div className="flex items-center justify-between">
                  <p className="font-mono text-[10px]">{entry.point.id}</p>
                  <div className="flex items-center gap-1">
                    <span className={`rounded-full border px-1.5 py-0.5 text-[9px] font-semibold uppercase ${SEVERITY_CLASSES[entry.severity]}`}>
                      {entry.severity}
                    </span>
                    <span className="rounded bg-muted/40 px-1 py-0.5 text-[9px]">{STATUS_LABELS[entry.status]}</span>
                  </div>
                </div>
                <p className="mt-0.5 text-muted-foreground">risk {entry.point.risk.toFixed(2)} / uncertainty {entry.point.uncertainty.toFixed(2)}</p>
                <div className="mt-1 flex gap-1">
                  <Link href={`/console?request_id=${encodeURIComponent(entry.point.id)}`} className="rounded border border-border/50 px-1.5 py-0.5 text-[9px] hover:bg-muted/40" onClick={(event) => event.stopPropagation()}>
                    Open in Decision
                  </Link>
                  <Link href={`/audit?request_id=${encodeURIComponent(entry.point.id)}`} className="rounded border border-border/50 px-1.5 py-0.5 text-[9px] hover:bg-muted/40" onClick={(event) => event.stopPropagation()}>
                    Open in TrustLog
                  </Link>
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
});
