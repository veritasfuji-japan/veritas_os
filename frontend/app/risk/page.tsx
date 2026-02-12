import { MissionPage } from "../../components/mission-page";

export default function RiskIntelligencePage(): JSX.Element {
  return (
    <MissionPage
      title="Risk Intelligence"
      subtitle="先行指標とシナリオ推論により、未来リスクの予兆を可視化します。"
      chips={["Predictive Radar", "Threat Horizon", "Impact Forecast"]}
    />
  );
}
