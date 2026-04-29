"use client";

import { LiveEventStream } from "../components/live-event-stream";
import { MissionControlContainer } from "../components/mission-control-container";

const DASHBOARD_LIVE_INGRESS = {
  governance_layer_snapshot: {
    participation_state: "participatory",
    preservation_state: "open",
    intervention_viability: "high",
    concise_rationale:
      "pre-bind participation and preservation signals remain stable before bind classification.",
    bind_outcome: "BLOCKED",
  },
};

export default function CommandDashboardPage(): JSX.Element {
  return (
    <div className="space-y-6">
      <LiveEventStream />
      <MissionControlContainer ingressPayload={DASHBOARD_LIVE_INGRESS} />
    </div>
  );
}
