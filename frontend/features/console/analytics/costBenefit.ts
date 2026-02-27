import { type DecideResponse } from "@veritas/types";
import { type CostBenefitAnalytics, type StepAnalytics } from "../types";
import { toArray, toFiniteNumber } from "./utils";

/**
 * Estimate a baseline uncertainty from known response fields.
 */
function inferBaseUncertainty(result: DecideResponse): number {
  const chosen = result.chosen ?? {};
  const uncertainty = toFiniteNumber((chosen as Record<string, unknown>).uncertainty);
  if (uncertainty !== null) {
    return Math.min(1, Math.max(0, uncertainty));
  }

  const confidence = toFiniteNumber((chosen as Record<string, unknown>).confidence);
  if (confidence !== null) {
    return Math.min(1, Math.max(0, 1 - confidence));
  }

  const risk = toFiniteNumber((result.gate as Record<string, unknown>).risk);
  if (risk !== null) {
    return Math.min(1, Math.max(0.1, risk));
  }

  return 0.6;
}

/**
 * Build cost-benefit analytics from backend payload, falling back to inferred values.
 */
export function buildCostBenefitAnalytics(result: DecideResponse): CostBenefitAnalytics {
  const extras = (result.extras ?? {}) as Record<string, unknown>;
  const rawAnalytics = extras.cost_benefit_analytics;

  if (rawAnalytics && typeof rawAnalytics === "object") {
    const asMap = rawAnalytics as Record<string, unknown>;
    const rawSteps = Array.isArray(asMap.steps) ? asMap.steps : [];
    const steps: StepAnalytics[] = rawSteps.map((step) => {
      const item = (step ?? {}) as Record<string, unknown>;
      return {
        name: typeof item.name === "string" ? item.name : "Unknown",
        executed: item.executed !== false,
        uncertaintyBefore: toFiniteNumber(item.uncertainty_before),
        uncertaintyAfter: toFiniteNumber(item.uncertainty_after),
        tokenCost: toFiniteNumber(item.token_cost),
        inferred: false,
      };
    });

    const totalTokenCost = toFiniteNumber(asMap.total_token_cost) ?? 0;
    const uncertaintyReduction = toFiniteNumber(asMap.uncertainty_reduction);
    return {
      steps,
      totalTokenCost,
      uncertaintyReduction,
      inferred: false,
    };
  }

  const baseline = inferBaseUncertainty(result);
  const evidenceCount = toArray(result.evidence).length;
  const critiqueCount = toArray(result.critique).length;
  const debateCount = toArray(result.debate).length;
  const hasGate = Boolean((result.gate as Record<string, unknown>).decision_status);

  const tokenByStage = {
    Evidence: evidenceCount > 0 ? 180 : 0,
    Critique: critiqueCount > 0 ? 220 : 0,
    Debate: debateCount > 0 ? 420 : 0,
    "FUJI Gate": hasGate ? 120 : 0,
  };
  const reductionByStage = {
    Evidence: evidenceCount > 0 ? 0.08 : 0,
    Critique: critiqueCount > 0 ? 0.06 : 0,
    Debate: debateCount > 0 ? 0.12 : 0,
    "FUJI Gate": hasGate ? 0.1 : 0,
  };

  const orderedStages = ["Evidence", "Critique", "Debate", "FUJI Gate"] as const;
  let current = baseline;
  const steps: StepAnalytics[] = orderedStages.map((name) => {
    const before = current;
    const reduction = reductionByStage[name];
    current = Math.max(0.03, before - reduction);
    const executed = tokenByStage[name] > 0;
    return {
      name,
      executed,
      uncertaintyBefore: executed ? before : null,
      uncertaintyAfter: executed ? current : null,
      tokenCost: executed ? tokenByStage[name] : null,
      inferred: true,
    };
  });

  return {
    steps,
    totalTokenCost: steps.reduce((acc, step) => acc + (step.tokenCost ?? 0), 0),
    uncertaintyReduction: Math.max(0, baseline - current),
    inferred: true,
  };
}
