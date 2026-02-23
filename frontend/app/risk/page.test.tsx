import { act, render, screen } from "@testing-library/react";
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

  it("renders the real-time scatter heatmap", () => {
    render(<RiskIntelligencePage />);

    expect(screen.getByText("Risk Intelligence")).toBeInTheDocument();
    expect(screen.getByText("Real-time Risk Heatmap")).toBeInTheDocument();
    expect(
      screen.getByRole("img", {
        name: "Scatter plot of request uncertainty and risk from the last 24 hours",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Normal")).toBeInTheDocument();
  });

  it("raises cluster alert when high risk points continue to stream", () => {
    vi.spyOn(Math, "random").mockReturnValue(0.99);
    render(<RiskIntelligencePage />);

    act(() => {
      vi.advanceTimersByTime(30_000);
    });

    expect(screen.getByText("Cluster Alert")).toBeInTheDocument();
  });
});
