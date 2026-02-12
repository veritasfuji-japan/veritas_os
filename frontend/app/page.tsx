import { MissionPage } from "../components/mission-page";
import { LiveEventStream } from "../components/live-event-stream";

export default function CommandDashboardPage(): JSX.Element {
  return (
    <div className="space-y-6">
      <LiveEventStream />
      <MissionPage
        title="Command Dashboard"
        subtitle="ミッション全体の健全性を俯瞰監視し、異常シグナルを即時に検出します。"
        chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
      />
    </div>
  );
}
