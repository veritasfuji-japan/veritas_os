import { LiveEventStream } from "../components/live-event-stream";
import { MissionControlContainer } from "../components/mission-control-container";

import { loadMissionControlIngressPayload } from "./mission-control-ingress";
import { areE2EScenariosEnabled } from "./e2e-scenarios";

interface CommandDashboardPageProps {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}

export default async function CommandDashboardPage({
  searchParams,
}: CommandDashboardPageProps = {}): Promise<JSX.Element> {
  const resolvedSearchParams = searchParams ? await searchParams : undefined;
  const scenarioParam = resolvedSearchParams?.e2e_governance_scenario;
  const scenarioOverride = areE2EScenariosEnabled()
    ? (Array.isArray(scenarioParam) ? scenarioParam[0] : scenarioParam)
    : null;
  const ingressPayload = await loadMissionControlIngressPayload(scenarioOverride);

  return (
    <div className="space-y-6">
      <LiveEventStream />
      <MissionControlContainer ingressPayload={ingressPayload} />
    </div>
  );
}
