import { type DecideResponse } from "@veritas/types";
import { toArray } from "../analytics/utils";
import { PIPELINE_STAGES, type PipelineStageName } from "../constants";
import {
  type DecisionResultView,
  type FujiGateView,
  type PipelineStageStatus,
  type PipelineStageView,
} from "../types";

const STAGE_ALIASES: Record<PipelineStageName, string[]> = {
  Input: ["input"],
  Evidence: ["evidence"],
  Critique: ["critique"],
  Debate: ["debate"],
  Plan: ["plan", "planner"],
  Value: ["value", "values"],
  FUJI: ["fuji", "gate"],
  TrustLog: ["trustlog", "trust_log"],
};

function toStageStatus(
  result: DecideResponse | null,
  loading: boolean,
  hasError: boolean,
  stageIndex: number,
  activeIndex: number,
  health: string,
): PipelineStageStatus {
  if (health === "failed") {
    return "failed";
  }
  if (health === "warning") {
    return "warning";
  }
  if (hasError && stageIndex <= activeIndex) {
    return "failed";
  }
  if (result) {
    return "complete";
  }
  if (loading && stageIndex === activeIndex) {
    return "running";
  }
  if (loading && stageIndex < activeIndex) {
    return "complete";
  }
  return "idle";
}

/**
 * Maps `/v1/decide` payloads into a stable UI model.
 *
 * This adapter keeps view-specific fallback rules out of React components and
 * prepares for future backend schema evolution.
 */
export function toPipelineStageViews(
  result: DecideResponse | null,
  loading: boolean,
  error: string | null,
  activeIndex: number,
): PipelineStageView[] {
  const metrics = (result?.extras?.stage_metrics ?? {}) as Record<string, unknown>;
  const hasError = Boolean(error && !result);

  return PIPELINE_STAGES.map((stage, stageIndex) => {
    const aliases = STAGE_ALIASES[stage];
    const row = aliases
      .map((alias) => metrics[alias])
      .find((value) => value && typeof value === "object") as Record<string, unknown> | undefined;
    const latencyValue = row?.latency_ms;
    const latencyMs = typeof latencyValue === "number" ? latencyValue : null;
    const health = typeof row?.health === "string" ? row.health : "unknown";
    const status = toStageStatus(result, loading, hasError, stageIndex, activeIndex, health);

    const detail = typeof row?.detail === "string"
      ? row.detail
      : typeof row?.reason === "string"
        ? row.reason
        : status === "failed"
          ? "Execution stopped before completion."
          : "No detailed diagnostics provided.";

    const summary = typeof row?.summary === "string"
      ? row.summary
      : status === "complete"
        ? "Stage finished."
        : status === "running"
          ? "Processing..."
          : "Waiting for execution.";

    return {
      name: stage,
      status,
      latencyMs,
      summary,
      detail,
      raw: row ?? {},
    };
  });
}

function readText(record: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim().length > 0) {
      return value;
    }
  }
  return "n/a";
}

export function toFujiGateView(result: DecideResponse | null): FujiGateView {
  if (!result) {
    return {
      decision: "n/a",
      ruleHit: "n/a",
      severity: "n/a",
      remediationHint: "n/a",
      riskyFragmentPreview: "n/a",
    };
  }

  const merged = {
    ...(result.fuji as Record<string, unknown>),
    ...(result.gate as Record<string, unknown>),
  };

  return {
    decision: readText(merged, "decision_status", "status"),
    ruleHit: readText(merged, "rule_hit", "rule", "policy_rule", "code"),
    severity: readText(merged, "severity", "risk_level"),
    remediationHint: readText(merged, "remediation_hint", "hint", "action"),
    riskyFragmentPreview: readText(merged, "risky_text_fragment", "snippet", "fragment"),
  };
}

export function toDecisionResultView(result: DecideResponse): DecisionResultView {
  const chosen = result.chosen as Record<string, unknown>;
  const alternatives = toArray(result.alternatives) as Array<Record<string, unknown>>;
  const evidenceSources = toArray(result.evidence)
    .map((item) => (item as Record<string, unknown>).source)
    .filter((value): value is string => typeof value === "string");

  return {
    chosen: {
      finalDecision: readText(chosen, "title", "decision", "id"),
      whyChosen: readText(chosen, "why", "rationale", "reason"),
      supportingEvidenceSummary: evidenceSources.length > 0 ? evidenceSources.slice(0, 3).join(", ") : "n/a",
      valueRationale: readText((result.values ?? {}) as Record<string, unknown>, "rationale"),
    },
    alternatives: alternatives.map((item, index) => ({
      optionSummary: readText(item, "title", "description", "id") || `Option ${index + 1}`,
      tradeOff: readText(item, "trade_off", "tradeoff", "impact", "description"),
      relativeWeakness: readText(item, "weakness", "relative_weakness", "risk"),
    })),
    rejectedReasons: {
      fujiBlock: readText((result.gate ?? {}) as Record<string, unknown>, "reason"),
      weakEvidence: typeof result.evidence[0]?.confidence === "number" && result.evidence[0].confidence < 0.6
        ? "Low confidence evidence detected."
        : "n/a",
      poorDebateOutcome: result.debate.length === 0 ? "Debate did not provide decisive support." : "n/a",
      valueConflict: readText((result.values ?? {}) as Record<string, unknown>, "conflict", "warning"),
    },
  };
}
