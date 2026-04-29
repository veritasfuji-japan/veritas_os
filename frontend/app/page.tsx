"use client";

import { MissionPage } from "../components/mission-page";
import { LiveEventStream } from "../components/live-event-stream";
import { useI18n } from "../components/i18n-provider";
import { resolveMissionGovernanceSnapshot } from "../components/mission-governance-adapter";

const DASHBOARD_LIVE_INGRESS = {
  governance_layer_snapshot: {
    participation_state: "participatory",
    preservation_state: "open",
    intervention_viability: "high",
    concise_rationale: "pre-bind participation and preservation signals remain stable before bind classification.",
    bind_outcome: "BLOCKED",
  },
};

export default function CommandDashboardPage(): JSX.Element {
  const { t } = useI18n();
  const governanceLayerSnapshot = resolveMissionGovernanceSnapshot(DASHBOARD_LIVE_INGRESS);

  return (
    <div className="space-y-6">
      <LiveEventStream />
      <MissionPage
        title={t("コマンドダッシュボード", "Command Dashboard")}
        subtitle={t(
          "ミッション全体の健全性を俯瞰監視し、異常シグナルを即時に検出します。",
          "Monitor overall mission health at a glance and detect abnormal signals immediately.",
        )}
        chips={[
          t("稼働格子", "Uptime Lattice"),
          t("シグナル監視", "Signal Watch"),
          t("異常キュー", "Anomaly Queue"),
        ]}
        governanceLayerSnapshot={governanceLayerSnapshot}
      />
    </div>
  );
}
