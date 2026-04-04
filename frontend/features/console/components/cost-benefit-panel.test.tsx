import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { CostBenefitPanel } from "./cost-benefit-panel";
import type { DecideResponse } from "@veritas/types";

function makeResult(overrides: Partial<DecideResponse> = {}): DecideResponse {
  return {
    decision_status: "approved",
    chosen: "A",
    rejection_reason: null,
    gate: { decision_status: "approved", risk: 0.3 },
    evidence: ["ev1"],
    critique: ["c1"],
    debate: [],
    ...overrides,
  } as DecideResponse;
}

describe("CostBenefitPanel", () => {
  it("renders section with heading", () => {
    render(<CostBenefitPanel result={makeResult()} />);
    expect(screen.getByRole("region", { name: "cost-benefit analytics" })).toBeInTheDocument();
    expect(screen.getByText("Cost-Benefit Analytics")).toBeInTheDocument();
  });

  it("renders table with step rows", () => {
    render(<CostBenefitPanel result={makeResult()} />);
    expect(screen.getByText("Step")).toBeInTheDocument();
    expect(screen.getByText("Executed")).toBeInTheDocument();
  });

  it("shows inferred banner when analytics are inferred", () => {
    // Without cost_benefit_analytics from backend, the component should show inferred
    render(<CostBenefitPanel result={makeResult()} />);
    expect(screen.getByText(/推定表示/)).toBeInTheDocument();
  });

  it("renders total token cost and uncertainty reduction", () => {
    render(<CostBenefitPanel result={makeResult()} />);
    expect(screen.getByText("Total Token Cost")).toBeInTheDocument();
    expect(screen.getByText("Uncertainty Reduction")).toBeInTheDocument();
  });
});
