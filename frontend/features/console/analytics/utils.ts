import { type DecideResponse } from "@veritas/types";

/**
 * Render-safe serializer for unknown values.
 */
export function renderValue(value: unknown): string {
  if (value === null) {
    return "null";
  }

  if (value === undefined) {
    return "undefined";
  }

  if (typeof value === "string") {
    return value;
  }

  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/**
 * Normalizes known list-like response fields into arrays for stable rendering.
 */
export function toArray(value: unknown): unknown[] {
  if (Array.isArray(value)) {
    return value;
  }

  if (value === null || value === undefined) {
    return [];
  }

  return [value];
}

/**
 * Parse unknown numeric input into finite number when available.
 */
export function toFiniteNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }

  return null;
}

/**
 * Builds a human-readable assistant message from decide API payload.
 *
 * When user_summary is present (simple_qa / knowledge_qa modes),
 * returns the polished natural-language summary directly.
 * Otherwise falls back to the structured decision/chosen/rejection format.
 */
export function toAssistantMessage(
  payload: DecideResponse,
  t: (ja: string, en: string) => string,
): string {
  const userSummary = payload.user_summary;
  if (typeof userSummary === "string" && userSummary.trim().length > 0) {
    return userSummary;
  }

  const businessDecision = payload.business_decision ?? "HOLD";
  const gateDecision = payload.gate_decision ?? payload.decision_status ?? "unknown";
  const gateDecisionWithMeaning = gateDecision === "allow"
    ? `${gateDecision} (${t("案件承認ではなく、応答出力可", "not case approval; response may be returned")})`
    : gateDecision;
  const nextAction = payload.next_action ?? t("要再評価", "Reassess required");
  const humanReviewRequired = payload.human_review_required === true ? t("要", "required") : t("不要", "not required");
  const chosen = payload.chosen ? renderValue(payload.chosen) : t("なし", "none");
  const rejection = payload.refusal_reason ?? payload.rejection_reason ?? t("なし", "none");
  return [
    `${t("案件状態", "Business Decision")}: ${businessDecision}`,
    `${t("ゲート判定", "Gate Decision")}: ${gateDecisionWithMeaning}`,
    `${t("次アクション", "Next Action")}: ${nextAction}`,
    `${t("人手レビュー", "Human Review")}: ${humanReviewRequired}`,
    `${t("採択案", "Chosen")}: ${chosen}`,
    `${t("拒否理由", "Rejection")}: ${rejection}`,
  ].join("\n");
}
