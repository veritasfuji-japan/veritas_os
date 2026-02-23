"use client";

import { MissionPage } from "../components/mission-page";
import { LiveEventStream } from "../components/live-event-stream";
import { useI18n } from "../components/i18n";

export default function CommandDashboardPage(): JSX.Element {
  const { t } = useI18n();

  return (
    <div className="space-y-6">
      <LiveEventStream />
      <MissionPage
        title="Command Dashboard"
        subtitle={t("page.dashboard.subtitle")}
        chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
      />
    </div>
  );
}
