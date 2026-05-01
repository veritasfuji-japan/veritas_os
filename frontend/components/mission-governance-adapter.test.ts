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



  it("preserves governance_observation fields when present", () => {
    const snapshot = resolveMissionGovernanceSnapshot({
      governance_layer_snapshot: {
        participation_state: "decision_shaping",
        governance_observation: {
          policy_mode: "observe",
          environment: "development",
          would_have_blocked: true,
          would_have_blocked_reason: "policy_violation:missing_authority_evidence",
          effective_outcome: "proceed",
          observed_outcome: "block",
          operator_warning: true,
          audit_required: true,
        },
      },
    });

    expect(snapshot.governance_observation).toBeDefined();
    expect(snapshot.governance_observation?.policy_mode).toBe("observe");
    expect(snapshot.governance_observation?.environment).toBe("development");
    expect(snapshot.governance_observation?.would_have_blocked).toBe(true);
    expect(snapshot.governance_observation?.would_have_blocked_reason).toBe("policy_violation:missing_authority_evidence");
    expect(snapshot.governance_observation?.effective_outcome).toBe("proceed");
    expect(snapshot.governance_observation?.observed_outcome).toBe("block");
    expect(snapshot.governance_observation?.operator_warning).toBe(true);
    expect(snapshot.governance_observation?.audit_required).toBe(true);
  });

  it("keeps governance_observation undefined when absent", () => {
    const snapshot = resolveMissionGovernanceSnapshot({
      governance_layer_snapshot: {
        participation_state: "decision_shaping",
      },
    });

    expect(snapshot.governance_observation).toBeUndefined();
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
