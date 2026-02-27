import { describe, expect, it } from "vitest";
import { buildCostBenefitAnalytics } from "./costBenefit";

describe("buildCostBenefitAnalytics", () => {
  it("uses backend-provided analytics when present", () => {
    const analytics = buildCostBenefitAnalytics({
      ok: true,
      error: null,
      request_id: "req",
      version: "1",
      decision_status: "allow",
      rejection_reason: null,
      chosen: { uncertainty: 0.4 },
      alternatives: [],
      options: [],
      fuji: {},
      gate: {},
      evidence: [],
      critique: [],
      debate: [],
      telos_score: 0,
      values: {},
      plan: null,
      planner: null,
      persona: {},
      memory_citations: [],
      memory_used_count: 0,
      trust_log: null,
      extras: {
        cost_benefit_analytics: {
          steps: [{ name: "Debate", executed: true, uncertainty_before: 0.4, uncertainty_after: 0.2, token_cost: 200 }],
          total_token_cost: 200,
          uncertainty_reduction: 0.2,
        },
      },
    });

    expect(analytics.inferred).toBe(false);
    expect(analytics.totalTokenCost).toBe(200);
    expect(analytics.steps[0]?.name).toBe("Debate");
  });

  it("infers analytics from response shape when backend data is missing", () => {
    const analytics = buildCostBenefitAnalytics({
      ok: true,
      error: null,
      request_id: "req",
      version: "1",
      decision_status: "modify",
      rejection_reason: null,
      chosen: { confidence: 0.5 },
      alternatives: [],
      options: [],
      fuji: {},
      gate: { decision_status: "modify", risk: 0.7 },
      evidence: [{ source: "a" }],
      critique: [{ check: "b" }],
      debate: [{ point: "c" }],
      telos_score: 0,
      values: {},
      plan: null,
      planner: null,
      persona: {},
      memory_citations: [],
      memory_used_count: 0,
      trust_log: null,
      extras: {},
    });

    expect(analytics.inferred).toBe(true);
    expect(analytics.totalTokenCost).toBeGreaterThan(0);
    expect(analytics.uncertaintyReduction).toBeGreaterThan(0);
  });
});
