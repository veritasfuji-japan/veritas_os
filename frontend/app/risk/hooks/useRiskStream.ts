"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { RiskPoint } from "../risk-types";
import {
  buildTrendBuckets,
  createInitialPoints,
  createStreamPoint,
  enrichFlaggedEntry,
  getCluster,
} from "../data-helpers";
import {
  ELEVATED_RISK_THRESHOLD,
  MAX_POINTS,
  STREAM_TICK_MS,
  STREAM_WINDOW_MS,
  UNSAFE_BURST_THRESHOLD,
} from "../constants";

export function useRiskStream() {
  const [points, setPoints] = useState<RiskPoint[]>([]);
  const [now, setNow] = useState<number>(0);
  const [timeWindowHours, setTimeWindowHours] = useState<number>(24);
  const [selectedCluster, setSelectedCluster] = useState<"all" | "critical" | "risky" | "uncertain">("all");
  const [selectedPointId, setSelectedPointId] = useState<string | null>(null);
  const [hoveredPointId, setHoveredPointId] = useState<string | null>(null);

  // Track previous points length to avoid unnecessary derived recalculations
  const pointsRef = useRef(points);
  pointsRef.current = points;

  useEffect(() => {
    const initial = Date.now();
    setNow(initial);
    setPoints(createInitialPoints(initial));
  }, []);

  const tickCallback = useCallback(() => {
    const tick = Date.now();
    setNow(tick);
    setPoints((previous) => {
      const next = [...previous, createStreamPoint(tick)];
      // Filter expired and cap in one pass
      const cutoff = tick - STREAM_WINDOW_MS;
      const filtered = next.filter((point) => point.timestamp > cutoff);
      return filtered.length > MAX_POINTS
        ? filtered.slice(filtered.length - MAX_POINTS)
        : filtered;
    });
  }, []);

  useEffect(() => {
    const timer = window.setInterval(tickCallback, STREAM_TICK_MS);
    return () => { window.clearInterval(timer); };
  }, [tickCallback]);

  const visiblePoints = useMemo(() => {
    const cutoff = now - timeWindowHours * 60 * 60 * 1000;
    return points.filter((point) => point.timestamp > cutoff);
  }, [points, now, timeWindowHours]);

  const filteredPoints = useMemo(() => {
    if (selectedCluster === "all") return visiblePoints;
    return visiblePoints.filter((point) => getCluster(point) === selectedCluster);
  }, [visiblePoints, selectedCluster]);

  const clusterStats = useMemo(() => {
    let criticalCount = 0;
    for (let i = 0; i < visiblePoints.length; i++) {
      if (getCluster(visiblePoints[i]) === "critical") criticalCount++;
    }
    const ratio = visiblePoints.length === 0 ? 0 : criticalCount / visiblePoints.length;
    return { ratio, count: criticalCount, alert: criticalCount >= 15 || ratio >= 0.08 };
  }, [visiblePoints]);

  const trend = useMemo(() => buildTrendBuckets(visiblePoints, now), [visiblePoints, now]);

  // Derived from trend — memoize to avoid recalc in render
  const trendDerived = useMemo(() => {
    const previousHighRisk = trend.slice(0, 7).reduce((sum, bucket) => sum + bucket.highRisk, 0) / 7;
    const latestHighRisk = trend[7]?.highRisk ?? 0;
    const spikeDetected = latestHighRisk >= previousHighRisk * 1.8 && latestHighRisk >= ELEVATED_RISK_THRESHOLD;
    const unsafeBurst = latestHighRisk >= UNSAFE_BURST_THRESHOLD;
    return { latestHighRisk, spikeDetected, unsafeBurst };
  }, [trend]);

  const flaggedEntries = useMemo(() => {
    return visiblePoints
      .filter((point) => getCluster(point) !== "stable")
      .sort((left, right) => right.risk + right.uncertainty - (left.risk + left.uncertainty))
      .slice(0, 20)
      .map(enrichFlaggedEntry);
  }, [visiblePoints]);

  const selectedEntry = useMemo(
    () => flaggedEntries.find((entry) => entry.point.id === selectedPointId) ?? flaggedEntries[0] ?? null,
    [flaggedEntries, selectedPointId],
  );

  const hoveredPoint = useMemo(
    () => (hoveredPointId ? visiblePoints.find((point) => point.id === hoveredPointId) ?? null : null),
    [hoveredPointId, visiblePoints],
  );

  return {
    now,
    visiblePoints,
    filteredPoints,
    clusterStats,
    trend,
    latestHighRisk: trendDerived.latestHighRisk,
    spikeDetected: trendDerived.spikeDetected,
    unsafeBurst: trendDerived.unsafeBurst,
    flaggedEntries,
    selectedEntry,
    hoveredPoint,
    timeWindowHours,
    setTimeWindowHours,
    selectedCluster,
    setSelectedCluster,
    selectedPointId,
    setSelectedPointId,
    hoveredPointId,
    setHoveredPointId,
  };
}
