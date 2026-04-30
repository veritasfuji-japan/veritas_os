import { LiveEventStream } from "../components/live-event-stream";
import { MissionControlContainer } from "../components/mission-control-container";

import { loadMissionControlIngressPayload } from "./mission-control-ingress";

interface CommandDashboardPageProps {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}

export default async function CommandDashboardPage({
  searchParams,
}: CommandDashboardPageProps = {}): Promise<JSX.Element> {
  const resolvedSearchParams = searchParams ? await searchParams : undefined;
  const scenarioParam = resolvedSearchParams?.e2e_governance_scenario;
  const scenarioOverride = Array.isArray(scenarioParam) ? scenarioParam[0] : scenarioParam;
  const ingressPayload = await loadMissionControlIngressPayload(scenarioOverride ?? null);

  return (
    <div className="space-y-6">
      <LiveEventStream />
      <MissionControlContainer ingressPayload={ingressPayload} />
    </div>
  );
}
