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
 */
export function toAssistantMessage(
  payload: DecideResponse,
  t: (ja: string, en: string) => string,
): string {
  const decision = payload.decision_status ?? "unknown";
  const chosen = payload.chosen ? renderValue(payload.chosen) : t("なし", "none");
  const rejection = payload.rejection_reason ?? t("なし", "none");
  return [
    `${t("判定", "Decision")}: ${decision}`,
    `${t("採択案", "Chosen")}: ${chosen}`,
    `${t("拒否理由", "Rejection")}: ${rejection}`,
  ].join("\n");
}
