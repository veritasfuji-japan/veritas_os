import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { GlobalHealthSummary } from "./global-health-summary";
import type { GlobalHealthSummaryModel } from "./dashboard-types";

const summary: GlobalHealthSummaryModel = {
  band: "healthy",
  todayChanges: ["Policy v2.1 deployed", "Trust score improved"],
  incidents24h: "3",
  policyDrift: "0.02",
  trustDegradation: "none",
  decisionAnomalies: "1",
};

describe("GlobalHealthSummary", () => {
  it("renders current band", () => {
    render(<GlobalHealthSummary summary={summary} />);
    expect(screen.getByText("healthy")).toBeInTheDocument();
  });

  it("renders today's changes", () => {
    render(<GlobalHealthSummary summary={summary} />);
    expect(screen.getByText("Policy v2.1 deployed")).toBeInTheDocument();
    expect(screen.getByText("Trust score improved")).toBeInTheDocument();
  });

  it("renders metrics", () => {
    render(<GlobalHealthSummary summary={summary} />);
    expect(screen.getByText("24h incidents: 3")).toBeInTheDocument();
    expect(screen.getByText("Policy drift: 0.02")).toBeInTheDocument();
    expect(screen.getByText("Decision anomalies: 1")).toBeInTheDocument();
  });
});
