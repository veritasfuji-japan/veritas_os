import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PipelineVisualizer } from "./pipeline-visualizer";

describe("PipelineVisualizer", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("renders all pipeline stages with initial idle state", () => {
    render(<PipelineVisualizer />);
    expect(screen.getByText("Pipeline Visualizer")).toBeInTheDocument();
    expect(screen.getByText("Evidence")).toBeInTheDocument();
    expect(screen.getByText("TrustLog")).toBeInTheDocument();

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(7);
    for (const item of items) {
      expect(item.querySelector("p")?.textContent).toBe("idle");
    }
  });

  it("clears both interval and timeout on unmount (no leak)", () => {
    vi.useFakeTimers();
    const clearIntervalSpy = vi.spyOn(globalThis, "clearInterval");
    const clearTimeoutSpy = vi.spyOn(globalThis, "clearTimeout");

    const { unmount } = render(<PipelineVisualizer />);

    // Advance enough to trigger the setTimeout inside setInterval (7 stages × 900ms)
    act(() => {
      vi.advanceTimersByTime(900 * 7);
    });

    unmount();

    expect(clearIntervalSpy).toHaveBeenCalled();
    expect(clearTimeoutSpy).toHaveBeenCalled();
  });
});
