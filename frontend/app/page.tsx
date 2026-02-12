import { MissionPage } from "../components/mission-page";

export default function CommandDashboardPage(): JSX.Element {
  return (
    <MissionPage
      title="Command Dashboard"
      subtitle="ミッション全体の健全性を俯瞰監視し、異常シグナルを即時に検出します。"
      chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
    />
  );
}
