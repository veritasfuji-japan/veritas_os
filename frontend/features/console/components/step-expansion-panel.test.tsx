import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StepExpansionPanel } from "./step-expansion-panel";
import type { DecideResponse } from "@veritas/types";

function makeResult(overrides: Partial<DecideResponse> = {}): DecideResponse {
  return {
    decision_status: "approved",
    chosen: "A",
    rejection_reason: null,
    evidence: ["ev1"],
    critique: [],
    debate: [],
    gate: { decision_status: "approved" },
    ...overrides,
  } as DecideResponse;
}

describe("StepExpansionPanel", () => {
  it("returns null when result is null", () => {
    const { container } = render(<StepExpansionPanel result={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders pipeline step views", () => {
    render(<StepExpansionPanel result={makeResult()} />);
    expect(screen.getByText(/Evidence/)).toBeInTheDocument();
    expect(screen.getByText(/FUJI Gate/)).toBeInTheDocument();
  });

  it("renders stage metrics when present", () => {
    const result = makeResult({
      extras: {
        stage_metrics: {
          retrieval: { latency_ms: 150, health: "healthy" },
          safety: { latency_ms: 300, health: "warning" },
        },
      },
    });
    render(<StepExpansionPanel result={result} />);
    expect(screen.getByText("retrieval")).toBeInTheDocument();
    expect(screen.getByText("safety")).toBeInTheDocument();
    expect(screen.getByText(/150/)).toBeInTheDocument();
    expect(screen.getByText("healthy")).toBeInTheDocument();
    expect(screen.getByText("warning")).toBeInTheDocument();
  });
});
