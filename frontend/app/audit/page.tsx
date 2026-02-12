import { MissionPage } from "../../components/mission-page";

export default function TrustLogExplorerPage(): JSX.Element {
  return (
    <MissionPage
      title="TrustLog Explorer"
      subtitle="証跡を時系列で再構成し、説明責任のための監査証明を提供します。"
      chips={["Immutable Ledger", "Trace Timeline", "Evidence Pack"]}
    />
  );
}
