"use client";

import { useEffect, useState } from "react";

import { MissionPage } from "./mission-page";
import { useI18n } from "./i18n-provider";
import {
  mapGovernanceFeedToIngressPayload,
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
  const [browserPayload, setBrowserPayload] = useState<MissionGovernanceIngressPayload | null>(null);

  useEffect(() => {
    // The path-scoped session cookie reaches the feed URL from the browser.
    if (ingressPayload !== null) {
      setBrowserPayload(null);
      return;
    }

    const controller = new AbortController();
    async function loadFeed() {
      try {
        const response = await fetch("/api/veritas/v1/report/governance", {
          cache: "no-store",
          credentials: "same-origin",
          signal: controller.signal,
        });
        if (!response.ok) {
          return;
        }
        const payload: unknown = await response.json();
        if (!controller.signal.aborted) {
          setBrowserPayload(mapGovernanceFeedToIngressPayload(payload));
        }
      } catch {
        // Keep the fallback snapshot when the feed is unavailable.
      }
    }
    void loadFeed();
    return () => controller.abort();
  }, [ingressPayload]);

  const governanceLayerSnapshot = resolveMissionGovernanceSnapshot(ingressPayload ?? browserPayload);

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
