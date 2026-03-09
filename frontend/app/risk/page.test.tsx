import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import RiskIntelligencePage from "./page";

describe("RiskIntelligencePage", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("renders risk analysis workspace sections", () => {
    render(<RiskIntelligencePage />);

    expect(screen.getByText("Risk Intelligence")).toBeInTheDocument();
    expect(screen.getByText("Flagged requests")).toBeInTheDocument();
    expect(screen.getByText("Trend / Spike / Burst")).toBeInTheDocument();
    expect(screen.getByText("Why flagged")).toBeInTheDocument();
  });

  it("raises cluster alert when high risk points continue to stream", () => {
    vi.spyOn(Math, "random").mockReturnValue(0.99);
    render(<RiskIntelligencePage />);

    act(() => {
      vi.advanceTimersByTime(30_000);
    });

    expect(screen.getByText("Cluster Alert")).toBeInTheDocument();
  });

  it("supports time range selection and request drilldown", () => {
    render(<RiskIntelligencePage />);

    fireEvent.change(screen.getByDisplayValue("24h"), { target: { value: "1" } });
    fireEvent.click(screen.getAllByRole("button", { name: /risk/i })[0]);

    expect(screen.getByText("What to do next: open Decision for immediate mitigation, verify in TrustLog, then enforce policy updates in Governance.")).toBeInTheDocument();
  });
});
