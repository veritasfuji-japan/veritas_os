import { MissionPage } from "../../components/mission-page";

export default function DecisionConsolePage(): JSX.Element {
  return (
    <MissionPage
      title="Decision Console"
      subtitle="承認フローと自動実行チェーンを管理し、意思決定の即応性を高めます。"
      chips={["Execution Matrix", "Approval Gate", "Runbook Pulse"]}
    />
  );
}
