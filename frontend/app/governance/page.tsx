import { MissionPage } from "../../components/mission-page";

export default function GovernanceControlPage(): JSX.Element {
  return (
    <MissionPage
      title="Governance Control"
      subtitle="ポリシー階層と責任分界を明文化し、統制状態を維持します。"
      chips={["Policy Fabric", "Org Mandate", "Control Score"]}
    />
  );
}
