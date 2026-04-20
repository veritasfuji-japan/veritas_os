import type {
  BindBreakdown,
  BindPhaseOutcome,
  ClusterKind,
  DecisionPhaseOutcome,
  FlaggedEntry,
  FlagReason,
  RiskPoint,
  Severity,
  RequestStatus,
  TrendBucket,
} from "./risk-types";
import {
  ALERT_CLUSTER_THRESHOLD,
  RISK_CONFIDENCE_WEIGHT,
  STREAM_WINDOW_MS,
  UNCERTAINTY_CONFIDENCE_WEIGHT,
  UNSAFE_BURST_THRESHOLD,
  ELEVATED_RISK_THRESHOLD,
} from "./constants";

/**
 * NOTE: This page uses synthetic telemetry until a per-request risk API is available.
 * It is safe for UI/interaction validation only, and must not be used as evidence for
 * production incident response or compliance reporting.
 */
export function createInitialPoints(now: number): RiskPoint[] {
  return Array.from({ length: 160 }, (_, index) => {
    const wave = (Math.sin(index * 0.42) + 1) / 2;
    const uncertainty = Math.min(1, Math.max(0.03, wave * 0.88 + (index % 5) * 0.02));
    const risk = Math.min(1, Math.max(0.04, ((Math.cos(index * 0.31) + 1) / 2) * 0.9));

    return {
      id: `seed-${index}`,
      uncertainty,
      risk,
      timestamp: now - (index / 160) * STREAM_WINDOW_MS,
    };
  });
}

export function createStreamPoint(now: number): RiskPoint {
  const id = `${now}-${Math.random().toString(36).slice(2, 8)}`;
  const uncertainty = Math.random();
  const baseRisk = uncertainty * 0.65 + Math.random() * 0.35;
  const spike = Math.random() > 0.93 ? 0.15 : 0;

  return {
    id,
    uncertainty,
    risk: Math.min(1, baseRisk + spike),
    timestamp: now,
  };
}

export function getCluster(point: RiskPoint): ClusterKind {
  if (point.uncertainty >= ALERT_CLUSTER_THRESHOLD && point.risk >= ALERT_CLUSTER_THRESHOLD) {
    return "critical";
  }
  if (point.risk >= ALERT_CLUSTER_THRESHOLD) {
    return "risky";
  }
  if (point.uncertainty >= ALERT_CLUSTER_THRESHOLD) {
    return "uncertain";
  }
  return "stable";
}

export function deriveSeverity(point: RiskPoint): Severity {
  const combined = point.risk * 0.6 + point.uncertainty * 0.4;
  if (combined >= 0.85) return "critical";
  if (combined >= 0.7) return "high";
  if (combined >= 0.5) return "medium";
  return "low";
}

export function deriveStatus(point: RiskPoint): RequestStatus {
  if (point.id.startsWith("seed-")) {
    const idx = Number(point.id.replace("seed-", ""));
    if (idx % 7 === 0) return "mitigated";
    if (idx % 5 === 0) return "investigating";
  }
  return "new";
}

function deriveDecisionOutcome(point: RiskPoint): DecisionPhaseOutcome {
  if (point.risk >= 0.9) return "deny";
  if (point.risk >= 0.75 || point.uncertainty >= 0.8) return "modify";
  if (point.uncertainty >= 0.65) return "hold";
  return "allow";
}

/**
 * Builds synthetic bind-phase state for Mission Control visualization.
 *
 * The values are deterministic from risk telemetry so tests and UI state stay
 * stable without introducing backend coupling.
 */
function deriveBindPhase(point: RiskPoint): {
  outcome: BindPhaseOutcome;
  failureReason: string;
  breakdown: BindBreakdown;
} {
  if (point.risk >= 0.92) {
    return {
      outcome: "BLOCKED",
      failureReason: "Authority denied due to critical policy risk.",
      breakdown: {
        authority: "FAIL",
        constraints: "PASS",
        drift: "PASS",
        risk: "FAIL",
      },
    };
  }
  if (point.risk >= 0.84 && point.uncertainty >= 0.78) {
    return {
      outcome: "ESCALATED",
      failureReason: "Human escalation required for unstable high-risk profile.",
      breakdown: {
        authority: "PASS",
        constraints: "PASS",
        drift: "FAIL",
        risk: "FAIL",
      },
    };
  }
  if (point.uncertainty >= 0.88) {
    return {
      outcome: "ROLLED_BACK",
      failureReason: "Bind was rolled back after drift threshold exceeded.",
      breakdown: {
        authority: "PASS",
        constraints: "PASS",
        drift: "FAIL",
        risk: "PASS",
      },
    };
  }
  return {
    outcome: "COMMITTED",
    failureReason: "none",
    breakdown: {
      authority: "PASS",
      constraints: "PASS",
      drift: "PASS",
      risk: "PASS",
    },
  };
}

export function buildFlagReason(point: RiskPoint): FlagReason {
  const cluster = getCluster(point);
  const policyConfidence = Math.max(0, 1 - point.risk * RISK_CONFIDENCE_WEIGHT - point.uncertainty * UNCERTAINTY_CONFIDENCE_WEIGHT);
  const unstableOutputSignal = point.uncertainty >= 0.75;
  const retrievalAnomaly = point.risk >= 0.7 && point.uncertainty >= 0.6;

  let summary: string;
  let suggestedAction: string;

  if (cluster === "critical") {
    summary = "High uncertainty combined with high risk score. Policy confidence is low and output stability cannot be guaranteed.";
    suggestedAction = "Escalate to Decision Console for immediate review; verify trust chain in TrustLog.";
  } else if (cluster === "risky") {
    summary = "Risk score exceeds threshold. Policy violation likelihood is elevated despite moderate uncertainty.";
    suggestedAction = "Check Decision Console for policy hit details; review Governance thresholds.";
  } else if (cluster === "uncertain") {
    summary = "Uncertainty is high. Model behavior may drift or produce unstable outputs.";
    suggestedAction = "Monitor in TrustLog for output consistency; consider tightening retrieval quality checks.";
  } else {
    summary = "Within expected safety envelope.";
    suggestedAction = "No immediate action required.";
  }

  return { policyConfidence, unstableOutputSignal, retrievalAnomaly, summary, suggestedAction };
}

function deriveRelatedPolicyHits(point: RiskPoint): string[] {
  const hits: string[] = [];
  if (point.risk >= 0.82) hits.push("content-safety-v2");
  if (point.uncertainty >= 0.82) hits.push("output-stability-check");
  if (point.risk >= 0.7 && point.uncertainty >= 0.6) hits.push("retrieval-quality-gate");
  if (point.risk >= 0.9) hits.push("prompt-injection-shield");
  return hits;
}

function deriveStageAnomalies(point: RiskPoint): string[] {
  const anomalies: string[] = [];
  if (point.uncertainty >= 0.75) anomalies.push("LLM output variance high");
  if (point.risk >= 0.8) anomalies.push("Safety gate triggered");
  if (point.risk >= 0.7 && point.uncertainty >= 0.6) anomalies.push("Retrieval confidence low");
  if (point.risk >= 0.9) anomalies.push("Post-processing filter activated");
  return anomalies;
}

export function enrichFlaggedEntry(point: RiskPoint): FlaggedEntry {
  const bindPhase = deriveBindPhase(point);
  const bindReceiptId = `bind-${point.id}`;
  return {
    point,
    cluster: getCluster(point),
    severity: deriveSeverity(point),
    status: deriveStatus(point),
    decisionOutcome: deriveDecisionOutcome(point),
    bindOutcome: bindPhase.outcome,
    bindFailureReason: bindPhase.failureReason,
    bindReceiptId,
    bindLineageHref: `/audit?bind_receipt_id=${encodeURIComponent(bindReceiptId)}`,
    bindBreakdown: bindPhase.breakdown,
    reason: buildFlagReason(point),
    relatedPolicyHits: deriveRelatedPolicyHits(point),
    stageAnomalies: deriveStageAnomalies(point),
  };
}

export function buildTrendBuckets(points: RiskPoint[], now: number): TrendBucket[] {
  const bucketMs = 3 * 60 * 60 * 1000;
  return Array.from({ length: 8 }, (_, index) => {
    const start = now - (8 - index) * bucketMs;
    const end = start + bucketMs;
    const segment = points.filter((point) => point.timestamp >= start && point.timestamp < end);
    const highRisk = segment.filter((point) => getCluster(point) === "critical").length;

    return {
      label: `${index * 3}-${(index + 1) * 3}h`,
      total: segment.length,
      highRisk,
    };
  });
}

export function bucketMeaning(bucket: TrendBucket): string {
  if (bucket.highRisk >= UNSAFE_BURST_THRESHOLD) return "Unsafe burst — critical concentration detected";
  if (bucket.highRisk >= ELEVATED_RISK_THRESHOLD) return "Elevated risk — multiple critical events";
  if (bucket.highRisk > 0) return "Low-level risk events present";
  if (bucket.total === 0) return "No activity in this window";
  return "Normal operation";
}

export function pointFill(cluster: ClusterKind): string {
  if (cluster === "critical") return "hsl(var(--destructive))";
  if (cluster === "risky") return "hsl(var(--ds-color-warning))";
  if (cluster === "uncertain") return "hsl(var(--ds-color-info))";
  return "hsl(var(--primary) / 0.82)";
}
