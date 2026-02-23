"use client";

import { MissionPage } from "../components/mission-page";
import { LiveEventStream } from "../components/live-event-stream";
import { useI18n } from "../components/i18n-provider";

export default function CommandDashboardPage(): JSX.Element {
  const { t } = useI18n();

  return (
    <div className="space-y-6">
      <LiveEventStream />
      <MissionPage
        title="Command Dashboard"
        subtitle={t(
          "ミッション全体の健全性を俯瞰監視し、異常シグナルを即時に検出します。",
          "Monitor overall mission health at a glance and detect abnormal signals immediately.",
        )}
        chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
      />
    </div>
  );
}
