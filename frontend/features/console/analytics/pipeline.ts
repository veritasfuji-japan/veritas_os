import { type DecideResponse } from "@veritas/types";
import { type GovernanceDriftAlert, type PipelineStepView } from "../types";
import { renderValue, toArray, toFiniteNumber } from "./utils";

/**
 * Converts backend response to expandable UI steps for a chat-style timeline.
 */
export function buildPipelineStepViews(result: DecideResponse): PipelineStepView[] {
  const gate = (result.gate ?? {}) as Record<string, unknown>;
  const gateStatus = typeof gate.decision_status === "string" ? gate.decision_status : "unknown";
  const plan = Array.isArray(result.plan) ? result.plan : [];

  const planSteps = plan.reduce<PipelineStepView[]>((acc, step) => {
    const asMap = (step ?? {}) as Record<string, unknown>;
    const title = typeof asMap.title === "string" ? asMap.title : null;
    const objective = typeof asMap.objective === "string" ? asMap.objective : null;

    if (!title && !objective) {
      return acc;
    }

    const label = title ?? objective ?? "Untitled step";
    acc.push({
      name: label,
      summary: "Planner generated step",
      status: "complete",
      detail: renderValue(asMap),
    });

    return acc;
  }, []);

  if (planSteps.length > 0) {
    return planSteps;
  }

  const evidenceCount = toArray(result.evidence).length;
  const critiqueCount = toArray(result.critique).length;
  const debateCount = toArray(result.debate).length;

  return [
    {
      name: "Evidence",
      summary: `${evidenceCount} items collected`,
      status: evidenceCount > 0 ? "complete" : "idle",
      detail: renderValue(result.evidence),
    },
    {
      name: "Critique",
      summary: `${critiqueCount} checks generated`,
      status: critiqueCount > 0 ? "complete" : "idle",
      detail: renderValue(result.critique),
    },
    {
      name: "Debate",
      summary: `${debateCount} arguments compared`,
      status: debateCount > 0 ? "complete" : "idle",
      detail: renderValue(result.debate),
    },
    {
      name: "FUJI Gate",
      summary: `Decision ${gateStatus}`,
      status: gateStatus !== "unknown" ? "complete" : "idle",
      detail: renderValue(result.gate),
    },
  ];
}

/**
 * Computes governance drift alert message based on drift/risk thresholds.
 */
export function buildGovernanceDriftAlert(result: DecideResponse | null): GovernanceDriftAlert | null {
  if (!result) {
    return null;
  }

  const values = (result.values ?? {}) as Record<string, unknown>;
  const driftScore = toFiniteNumber(values.valuecore_drift) ?? toFiniteNumber(values.value_drift);
  const gate = (result.gate ?? {}) as Record<string, unknown>;
  const risk = toFiniteNumber(gate.risk);

  if ((driftScore ?? 0) >= 10 || (risk ?? 0) >= 0.7) {
    return {
      title: "1 Issue",
      description: "ValueCoreの乖離が閾値を超えました。レビューを推奨します。",
    };
  }

  return null;
}
