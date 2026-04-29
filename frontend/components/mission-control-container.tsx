"use client";

import { MissionPage } from "./mission-page";
import { useI18n } from "./i18n-provider";
import {
  resolveMissionGovernanceSnapshot,
  type MissionGovernanceIngressPayload,
} from "./mission-governance-adapter";

interface MissionControlContainerProps {
  ingressPayload?: MissionGovernanceIngressPayload | null;
}

/**
 * MissionControlContainer owns governance snapshot ingress selection,
 * keeping MissionPage focused on pure timeline presentation.
 */
export function MissionControlContainer({ ingressPayload }: MissionControlContainerProps): JSX.Element {
  const { t } = useI18n();
  const governanceLayerSnapshot = resolveMissionGovernanceSnapshot(ingressPayload);

  return (
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
  );
}
