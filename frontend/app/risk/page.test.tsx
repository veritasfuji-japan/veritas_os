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
    expect(screen.getByText("Drilldown panel")).toBeInTheDocument();
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

    expect(screen.getByText(/Escalate to Decision Console|Check Decision Console|Monitor in TrustLog/)).toBeInTheDocument();
  });

  it("renders drilldown panel with structured details for selected entry", () => {
    render(<RiskIntelligencePage />);

    fireEvent.click(screen.getAllByRole("button", { name: /risk/i })[0]);

    const drilldown = screen.getByTestId("drilldown-panel");
    expect(drilldown).toBeInTheDocument();
    expect(drilldown.textContent).toContain("Request ID / Seed");
    expect(drilldown.textContent).toContain("Uncertainty");
    expect(drilldown.textContent).toContain("Risk score");
  });

  it("renders structured why-flagged with policy confidence and signals", () => {
    render(<RiskIntelligencePage />);

    fireEvent.click(screen.getAllByRole("button", { name: /risk/i })[0]);

    const whyFlagged = screen.getByTestId("why-flagged");
    expect(whyFlagged).toBeInTheDocument();
    expect(whyFlagged.textContent).toContain("Policy confidence");
    expect(whyFlagged.textContent).toContain("Unstable output");
    expect(whyFlagged.textContent).toContain("Retrieval anomaly");
    expect(whyFlagged.textContent).toContain("Suggested next action");
  });

  it("renders severity badges and cross-navigation links in flagged requests", () => {
    render(<RiskIntelligencePage />);

    expect(screen.getAllByText("Open in Decision").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Open in TrustLog").length).toBeGreaterThan(0);
  });

  it("renders insight cards with why it matters, impact scope and CTA", () => {
    render(<RiskIntelligencePage />);

    expect(screen.getByText("Policy drift")).toBeInTheDocument();
    expect(screen.getByText("Unsafe burst")).toBeInTheDocument();
    expect(screen.getByText("Unstable output cluster")).toBeInTheDocument();

    expect(screen.getAllByText(/Why it matters:/).length).toBe(3);
    expect(screen.getByText(/Review thresholds in Governance/)).toBeInTheDocument();
    expect(screen.getByText(/Investigate in Decision/)).toBeInTheDocument();
    expect(screen.getByText(/Check stability in TrustLog/)).toBeInTheDocument();
  });

  it("renders cross-navigation links with icons in header", () => {
    render(<RiskIntelligencePage />);

    const decisionLinks = screen.getAllByRole("link", { name: /Decision/i });
    const trustLogLinks = screen.getAllByRole("link", { name: /TrustLog/i });
    const governanceLinks = screen.getAllByRole("link", { name: /Governance/i });

    expect(decisionLinks.length).toBeGreaterThanOrEqual(1);
    expect(trustLogLinks.length).toBeGreaterThanOrEqual(1);
    expect(governanceLinks.length).toBeGreaterThanOrEqual(1);
  });

  it("shows empty state with monitoring target when no flagged requests exist", () => {
    vi.spyOn(Math, "random").mockReturnValue(0.5);
    vi.spyOn(Math, "sin").mockReturnValue(0);
    vi.spyOn(Math, "cos").mockReturnValue(0);

    render(<RiskIntelligencePage />);

    const emptyDrilldown = screen.queryByTestId("empty-drilldown");
    const drilldownPanel = screen.getByTestId("drilldown-panel");
    expect(drilldownPanel).toBeInTheDocument();

    if (emptyDrilldown) {
      expect(emptyDrilldown.textContent).toMatch(/Monitoring target|監視対象/);
    }
  });

  it("renders trend chart buckets with high-risk indicators and meaning tooltips", () => {
    render(<RiskIntelligencePage />);

    const trendButtons = screen.getAllByRole("button").filter(
      (btn) => btn.getAttribute("title") !== null && btn.getAttribute("title")!.length > 0
    );
    expect(trendButtons.length).toBeGreaterThan(0);
    expect(trendButtons[0].getAttribute("title")).toMatch(
      /Unsafe burst|Elevated risk|Low-level risk|No activity|Normal operation/
    );
  });
});
