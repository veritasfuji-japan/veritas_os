import { LiveEventStream } from "../components/live-event-stream";
import { MissionControlContainer } from "../components/mission-control-container";

import { loadMissionControlIngressPayload } from "./mission-control-ingress";

export default async function CommandDashboardPage(): Promise<JSX.Element> {
  const ingressPayload = await loadMissionControlIngressPayload();

  return (
    <div className="space-y-6">
      <LiveEventStream />
      <MissionControlContainer ingressPayload={ingressPayload} />
    </div>
  );
}
