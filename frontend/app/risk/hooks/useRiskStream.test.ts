import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

vi.mock("../data-helpers", () => ({
  createInitialPoints: (now: number) => [
    { id: "p1", uncertainty: 0.1, risk: 0.2, timestamp: now - 1000 },
    { id: "p2", uncertainty: 0.9, risk: 0.95, timestamp: now - 500 },
    { id: "p3", uncertainty: 0.5, risk: 0.5, timestamp: now - 200 },
  ],
  createStreamPoint: (tick: number) => ({
    id: `stream-${tick}`,
    uncertainty: 0.3,
    risk: 0.4,
    timestamp: tick,
  }),
  getCluster: (point: { risk: number; uncertainty: number }) => {
    if (point.risk > 0.8 && point.uncertainty > 0.8) return "critical";
    if (point.risk > 0.5) return "risky";
    if (point.uncertainty > 0.5) return "uncertain";
    return "stable";
  },
  enrichFlaggedEntry: (point: { id: string; uncertainty: number; risk: number; timestamp: number }) => ({
    point,
    cluster: "critical",
    severity: "critical",
    status: "new",
    reason: { policyConfidence: 0.1, unstableOutputSignal: true, retrievalAnomaly: false, summary: "test", suggestedAction: "test" },
    relatedPolicyHits: [],
    stageAnomalies: [],
  }),
  buildTrendBuckets: () =>
    Array.from({ length: 8 }, (_, i) => ({ label: `${i * 3}-${(i + 1) * 3}h`, total: 10, highRisk: i === 7 ? 2 : 0 })),
  pointFill: () => "#000",
}));

import { useRiskStream } from "./useRiskStream";

describe("useRiskStream", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("initialises with points from createInitialPoints", () => {
    const { result } = renderHook(() => useRiskStream());
    expect(result.current.visiblePoints.length).toBe(3);
  });

  it("filters by time window", () => {
    const { result } = renderHook(() => useRiskStream());
    // Default 24h window should include all points
    expect(result.current.visiblePoints.length).toBe(3);

    act(() => { result.current.setTimeWindowHours(24); });
    expect(result.current.visiblePoints.length).toBe(3);
  });

  it("filters by selected cluster", () => {
    const { result } = renderHook(() => useRiskStream());

    act(() => { result.current.setSelectedCluster("critical"); });
    // Only p2 has risk > 0.8 and uncertainty > 0.8
    expect(result.current.filteredPoints.length).toBe(1);
    expect(result.current.filteredPoints[0].id).toBe("p2");

    act(() => { result.current.setSelectedCluster("all"); });
    expect(result.current.filteredPoints.length).toBe(3);
  });

  it("tracks selected and hovered point IDs", () => {
    const { result } = renderHook(() => useRiskStream());

    act(() => { result.current.setSelectedPointId("p1"); });
    expect(result.current.selectedPointId).toBe("p1");

    act(() => { result.current.setHoveredPointId("p2"); });
    expect(result.current.hoveredPointId).toBe("p2");
    expect(result.current.hoveredPoint).not.toBeNull();
    expect(result.current.hoveredPoint!.id).toBe("p2");

    act(() => { result.current.setHoveredPointId(null); });
    expect(result.current.hoveredPoint).toBeNull();
  });

  it("computes flaggedEntries from non-stable points", () => {
    const { result } = renderHook(() => useRiskStream());
    // Non-stable points are flagged (getCluster mock determines which are stable)
    expect(result.current.flaggedEntries.length).toBeGreaterThanOrEqual(1);
  });

  it("provides trend data", () => {
    const { result } = renderHook(() => useRiskStream());
    expect(result.current.trend).toHaveLength(8);
  });

  it("selectedEntry defaults to first flaggedEntry", () => {
    const { result } = renderHook(() => useRiskStream());
    expect(result.current.selectedEntry).not.toBeNull();
  });
});
