import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PipelineVisualizer } from "./pipeline-visualizer";

/**
 * Pipeline visualizer behavior tests.
 *
 * Ensures stage cards render consistently and live timers are cleaned up
 * when the component is unmounted during an active run.
 */
describe("PipelineVisualizer", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("renders all pipeline stages and supports stage drilldown", () => {
    render(<PipelineVisualizer loading={false} result={null} error={null} />);

    expect(screen.getByText("Pipeline Operations View")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /1\. Evidence/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /7\. TrustLog/i })).toBeInTheDocument();

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(7);

    fireEvent.click(screen.getByRole("button", { name: /2\. Critique/i }));
    expect(screen.getByText("Critique details")).toBeInTheDocument();
    expect(screen.getByText("status: idle")).toBeInTheDocument();
  });

  it("clears interval on unmount during live execution", () => {
    vi.useFakeTimers();
    const clearIntervalSpy = vi.spyOn(globalThis, "clearInterval");

    const { unmount } = render(<PipelineVisualizer loading result={null} error={null} />);

    act(() => {
      vi.advanceTimersByTime(1300);
    });

    unmount();

    expect(clearIntervalSpy).toHaveBeenCalled();
  });
});
