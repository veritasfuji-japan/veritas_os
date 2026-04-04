import { describe, it, expect } from "vitest";
import type { RiskPoint, TrendBucket } from "./risk-types";
import {
  createInitialPoints,
  createStreamPoint,
  getCluster,
  deriveSeverity,
  deriveStatus,
  buildFlagReason,
  enrichFlaggedEntry,
  buildTrendBuckets,
  bucketMeaning,
  pointFill,
} from "./data-helpers";

const now = Date.now();

describe("createInitialPoints", () => {
  it("generates 160 seed points", () => {
    const points = createInitialPoints(now);
    expect(points).toHaveLength(160);
    points.forEach((p) => {
      expect(p.id).toMatch(/^seed-\d+$/);
      expect(p.uncertainty).toBeGreaterThanOrEqual(0);
      expect(p.uncertainty).toBeLessThanOrEqual(1);
      expect(p.risk).toBeGreaterThanOrEqual(0);
      expect(p.risk).toBeLessThanOrEqual(1);
    });
  });
});

describe("createStreamPoint", () => {
  it("generates a point with valid fields", () => {
    const point = createStreamPoint(now);
    expect(point.id).toContain(String(now));
    expect(point.uncertainty).toBeGreaterThanOrEqual(0);
    expect(point.risk).toBeLessThanOrEqual(1);
    expect(point.timestamp).toBe(now);
  });
});

describe("getCluster", () => {
  it("returns critical when both high", () => {
    expect(getCluster({ id: "t", uncertainty: 0.9, risk: 0.9, timestamp: 0 })).toBe("critical");
  });

  it("returns risky when only risk is high", () => {
    expect(getCluster({ id: "t", uncertainty: 0.1, risk: 0.9, timestamp: 0 })).toBe("risky");
  });

  it("returns uncertain when only uncertainty is high", () => {
    expect(getCluster({ id: "t", uncertainty: 0.9, risk: 0.1, timestamp: 0 })).toBe("uncertain");
  });

  it("returns stable when both low", () => {
    expect(getCluster({ id: "t", uncertainty: 0.1, risk: 0.1, timestamp: 0 })).toBe("stable");
  });
});

describe("deriveSeverity", () => {
  it("returns critical for combined >= 0.85", () => {
    expect(deriveSeverity({ id: "t", risk: 1, uncertainty: 1, timestamp: 0 })).toBe("critical");
  });

  it("returns high for combined >= 0.7", () => {
    expect(deriveSeverity({ id: "t", risk: 0.8, uncertainty: 0.55, timestamp: 0 })).toBe("high");
  });

  it("returns medium for combined >= 0.5", () => {
    expect(deriveSeverity({ id: "t", risk: 0.6, uncertainty: 0.35, timestamp: 0 })).toBe("medium");
  });

  it("returns low for combined < 0.5", () => {
    expect(deriveSeverity({ id: "t", risk: 0.1, uncertainty: 0.1, timestamp: 0 })).toBe("low");
  });
});

describe("deriveStatus", () => {
  it("returns mitigated for seed indices divisible by 7", () => {
    expect(deriveStatus({ id: "seed-7", uncertainty: 0, risk: 0, timestamp: 0 })).toBe("mitigated");
  });

  it("returns investigating for seed indices divisible by 5", () => {
    expect(deriveStatus({ id: "seed-5", uncertainty: 0, risk: 0, timestamp: 0 })).toBe("investigating");
  });

  it("returns new for non-seed points", () => {
    expect(deriveStatus({ id: "live-1", uncertainty: 0, risk: 0, timestamp: 0 })).toBe("new");
  });
});

describe("buildFlagReason", () => {
  it("returns critical summary for critical cluster", () => {
    const reason = buildFlagReason({ id: "t", uncertainty: 0.9, risk: 0.9, timestamp: 0 });
    expect(reason.summary).toContain("High uncertainty");
    expect(reason.policyConfidence).toBeLessThan(0.5);
    expect(reason.unstableOutputSignal).toBe(true);
    expect(reason.retrievalAnomaly).toBe(true);
  });

  it("returns stable summary for stable cluster", () => {
    const reason = buildFlagReason({ id: "t", uncertainty: 0.1, risk: 0.1, timestamp: 0 });
    expect(reason.summary).toContain("expected safety envelope");
    expect(reason.suggestedAction).toContain("No immediate action");
  });
});

describe("enrichFlaggedEntry", () => {
  it("returns a complete flagged entry", () => {
    const point: RiskPoint = { id: "seed-0", uncertainty: 0.9, risk: 0.95, timestamp: now };
    const entry = enrichFlaggedEntry(point);
    expect(entry.point).toBe(point);
    expect(entry.cluster).toBe("critical");
    expect(entry.severity).toBe("critical");
    expect(entry.relatedPolicyHits.length).toBeGreaterThan(0);
    expect(entry.stageAnomalies.length).toBeGreaterThan(0);
  });
});

describe("buildTrendBuckets", () => {
  it("returns 8 buckets", () => {
    const points = createInitialPoints(now);
    const buckets = buildTrendBuckets(points, now);
    expect(buckets).toHaveLength(8);
    buckets.forEach((b) => {
      expect(b.label).toMatch(/\d+-\d+h/);
      expect(b.total).toBeGreaterThanOrEqual(0);
    });
  });
});

describe("bucketMeaning", () => {
  it("returns unsafe burst for high-risk count >= 6", () => {
    const bucket: TrendBucket = { label: "0-3h", total: 10, highRisk: 6 };
    expect(bucketMeaning(bucket)).toContain("Unsafe burst");
  });

  it("returns elevated risk for high-risk count >= 3", () => {
    const bucket: TrendBucket = { label: "0-3h", total: 10, highRisk: 3 };
    expect(bucketMeaning(bucket)).toContain("Elevated risk");
  });

  it("returns low-level for small high-risk count", () => {
    const bucket: TrendBucket = { label: "0-3h", total: 10, highRisk: 1 };
    expect(bucketMeaning(bucket)).toContain("Low-level");
  });

  it("returns no activity for empty bucket", () => {
    const bucket: TrendBucket = { label: "0-3h", total: 0, highRisk: 0 };
    expect(bucketMeaning(bucket)).toContain("No activity");
  });

  it("returns normal operation for no high-risk events", () => {
    const bucket: TrendBucket = { label: "0-3h", total: 5, highRisk: 0 };
    expect(bucketMeaning(bucket)).toContain("Normal operation");
  });
});

describe("pointFill", () => {
  it("returns destructive color for critical", () => {
    expect(pointFill("critical")).toContain("destructive");
  });

  it("returns warning color for risky", () => {
    expect(pointFill("risky")).toContain("warning");
  });

  it("returns info color for uncertain", () => {
    expect(pointFill("uncertain")).toContain("info");
  });

  it("returns primary color for stable", () => {
    expect(pointFill("stable")).toContain("primary");
  });
});
