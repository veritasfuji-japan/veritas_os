import { describe, expect, it } from "vitest";

import { PRE_BIND_GOVERNANCE_VOCABULARY_LABELS } from "./dashboard-types";
import { resolveMissionGovernanceSnapshot } from "./mission-governance-adapter";

describe("resolveMissionGovernanceSnapshot", () => {
  it("prioritizes governance_layer_snapshot as live ingress", () => {
    const snapshot = resolveMissionGovernanceSnapshot({
      governance_layer_snapshot: {
        participation_state: "decision_shaping",
        preservation_state: "degrading",
        intervention_viability: "minimal",
        concise_rationale: "intervention window is narrowing.",
        bind_outcome: "ESCALATED",
      },
    });

    expect(snapshot.participation_state).toBe("decision_shaping");
    expect(snapshot.preservation_state).toBe("degrading");
    expect(snapshot.intervention_viability).toBe("minimal");
    expect(snapshot.bind_outcome).toBe("ESCALATED");
  });

  it("uses pre_bind_governance_snapshot when primary field is absent", () => {
    const snapshot = resolveMissionGovernanceSnapshot({
      pre_bind_governance_snapshot: {
        participation_state: "participatory",
        preservation_state: "open",
      },
    });

    expect(snapshot.participation_state).toBe("participatory");
    expect(snapshot.preservation_state).toBe("open");
    expect(snapshot.intervention_viability).toBeUndefined();
  });

  it("falls back to render-safe snapshot when ingress data is absent", () => {
    const snapshot = resolveMissionGovernanceSnapshot(undefined);

    expect(snapshot.participation_state).toBe("participatory");
    expect(snapshot.preservation_state).toBe("open");
    expect(snapshot.bind_outcome).toBe("BLOCKED");
  });

  it("keeps shared vocabulary naming unchanged", () => {
    expect(PRE_BIND_GOVERNANCE_VOCABULARY_LABELS).toMatchObject({
      participation_state: "participation_state",
      preservation_state: "preservation_state",
      intervention_viability: "intervention_viability",
      concise_rationale: "concise_rationale",
      bind_outcome: "bind_outcome",
    });
  });
});
