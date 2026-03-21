"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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

  useEffect(() => {
    const initial = Date.now();
    setNow(initial);
    setPoints(createInitialPoints(initial));
  }, []);

  const tickCallback = useCallback(() => {
    const tick = Date.now();
    setNow(tick);
    setPoints((previous) => {
      return [...previous, createStreamPoint(tick)]
        .filter((point) => tick - point.timestamp <= STREAM_WINDOW_MS)
        .slice(-MAX_POINTS);
    });
  }, []);

  useEffect(() => {
    const timer = window.setInterval(tickCallback, STREAM_TICK_MS);
    return () => { window.clearInterval(timer); };
  }, [tickCallback]);

  const visiblePoints = useMemo(() => {
    return points.filter((point) => now - point.timestamp <= timeWindowHours * 60 * 60 * 1000);
  }, [points, now, timeWindowHours]);

  const filteredPoints = useMemo(() => {
    if (selectedCluster === "all") return visiblePoints;
    return visiblePoints.filter((point) => getCluster(point) === selectedCluster);
  }, [visiblePoints, selectedCluster]);

  const clusterStats = useMemo(() => {
    const highRiskPoints = visiblePoints.filter((point) => getCluster(point) === "critical");
    const ratio = visiblePoints.length === 0 ? 0 : highRiskPoints.length / visiblePoints.length;
    return { ratio, count: highRiskPoints.length, alert: highRiskPoints.length >= 15 || ratio >= 0.08 };
  }, [visiblePoints]);

  const trend = useMemo(() => buildTrendBuckets(visiblePoints, now), [visiblePoints, now]);
  const previousHighRisk = trend.slice(0, 7).reduce((sum, bucket) => sum + bucket.highRisk, 0) / 7;
  const latestHighRisk = trend[7]?.highRisk ?? 0;
  const spikeDetected = latestHighRisk >= previousHighRisk * 1.8 && latestHighRisk >= ELEVATED_RISK_THRESHOLD;
  const unsafeBurst = latestHighRisk >= UNSAFE_BURST_THRESHOLD;

  const flaggedEntries = useMemo(() => {
    return visiblePoints
      .filter((point) => getCluster(point) !== "stable")
      .sort((left, right) => right.risk + right.uncertainty - (left.risk + left.uncertainty))
      .slice(0, 20)
      .map(enrichFlaggedEntry);
  }, [visiblePoints]);

  const selectedEntry = flaggedEntries.find((entry) => entry.point.id === selectedPointId) ?? flaggedEntries[0] ?? null;
  const hoveredPoint = hoveredPointId ? visiblePoints.find((point) => point.id === hoveredPointId) ?? null : null;

  return {
    now,
    visiblePoints,
    filteredPoints,
    clusterStats,
    trend,
    latestHighRisk,
    spikeDetected,
    unsafeBurst,
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
