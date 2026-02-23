"use client";

import { MissionPage } from "../../components/mission-page";
import { useI18n } from "../../components/i18n";

export default function RiskIntelligencePage(): JSX.Element {
  const { t } = useI18n();

  return (
    <MissionPage
      title="Risk Intelligence"
      subtitle={t("page.risk.subtitle")}
      chips={["Predictive Radar", "Threat Horizon", "Impact Forecast"]}
    />
  );
}
