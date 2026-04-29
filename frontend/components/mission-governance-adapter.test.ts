import { describe, expect, it } from "vitest";

import { resolveMissionGovernanceSnapshot } from "./mission-governance-adapter";

describe("resolveMissionGovernanceSnapshot", () => {
  it("prefers governance_layer_snapshot from live ingress", () => {
    const result = resolveMissionGovernanceSnapshot({
      governance_layer_snapshot: {
        participation_state: "decision_shaping",
        preservation_state: "degrading",
        intervention_viability: "minimal",
        concise_rationale: "live governance ingress",
        bind_outcome: "ESCALATED",
      },
      pre_bind_governance_snapshot: {
        participation_state: "participatory",
      },
    });

    expect(result.participation_state).toBe("decision_shaping");
    expect(result.bind_outcome).toBe("ESCALATED");
  });

  it("falls back to pre_bind_governance_snapshot when primary field is absent", () => {
    const result = resolveMissionGovernanceSnapshot({
      pre_bind_governance_snapshot: {
        participation_state: "informative",
        preservation_state: "open",
      },
    });

    expect(result.participation_state).toBe("informative");
    expect(result.preservation_state).toBe("open");
  });

  it("returns render-safety fallback snapshot when ingress is absent", () => {
    const result = resolveMissionGovernanceSnapshot();

    expect(result.participation_state).toBe("participatory");
    expect(result.preservation_state).toBe("open");
    expect(result.intervention_viability).toBe("high");
    expect(result.bind_outcome).toBe("BLOCKED");
  });
});

