import { describe, it, expect } from "vitest";
import type { DecideResponse } from "@veritas/types";
import { buildPipelineStepViews, buildGovernanceDriftAlert } from "./pipeline";

function makeResult(overrides: Partial<DecideResponse> = {}): DecideResponse {
  return {
    decision_status: "approved",
    chosen: "option A",
    rejection_reason: null,
    ...overrides,
  } as DecideResponse;
}

describe("buildPipelineStepViews", () => {
  it("returns plan steps when plan is provided", () => {
    const result = makeResult({
      plan: [
        { title: "Step 1", objective: "Gather data" },
        { title: "Step 2", objective: "Analyze" },
      ],
    });
    const steps = buildPipelineStepViews(result);
    expect(steps).toHaveLength(2);
    expect(steps[0].name).toBe("Step 1");
    expect(steps[0].status).toBe("complete");
  });

  it("falls back to evidence/critique/debate/gate when no plan", () => {
    const result = makeResult({
      evidence: ["ev1", "ev2"],
      critique: ["c1"],
      debate: [],
      gate: { decision_status: "approved" },
    });
    const steps = buildPipelineStepViews(result);
    expect(steps).toHaveLength(4);
    expect(steps[0].name).toBe("Evidence");
    expect(steps[0].summary).toContain("2 items");
    expect(steps[3].name).toBe("FUJI Gate");
  });

  it("skips plan entries without title or objective", () => {
    const result = makeResult({
      plan: [{ title: "Valid" }, {}, { objective: "Also valid" }],
    });
    const steps = buildPipelineStepViews(result);
    expect(steps).toHaveLength(2);
  });

  it("uses objective when title is missing", () => {
    const result = makeResult({
      plan: [{ objective: "My objective" }],
    });
    const steps = buildPipelineStepViews(result);
    expect(steps[0].name).toBe("My objective");
  });
});

describe("buildGovernanceDriftAlert", () => {
  it("returns null for null result", () => {
    expect(buildGovernanceDriftAlert(null)).toBeNull();
  });

  it("returns null when drift and risk are low", () => {
    const result = makeResult({
      values: { valuecore_drift: 2 },
      gate: { risk: 0.1 },
    });
    expect(buildGovernanceDriftAlert(result)).toBeNull();
  });

  it("returns alert when drift >= 10", () => {
    const result = makeResult({
      values: { valuecore_drift: 15 },
      gate: { risk: 0.1 },
    });
    const alert = buildGovernanceDriftAlert(result);
    expect(alert).not.toBeNull();
    expect(alert!.title).toBe("1 Issue");
  });

  it("returns alert when risk >= 0.7", () => {
    const result = makeResult({
      values: {},
      gate: { risk: 0.8 },
    });
    const alert = buildGovernanceDriftAlert(result);
    expect(alert).not.toBeNull();
  });
});
