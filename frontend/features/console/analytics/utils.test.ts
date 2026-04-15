import { describe, it, expect } from "vitest";
import { renderValue, toArray, toFiniteNumber, toAssistantMessage } from "./utils";
import type { DecideResponse } from "@veritas/types";

describe("renderValue", () => {
  it("returns 'null' for null", () => {
    expect(renderValue(null)).toBe("null");
  });

  it("returns 'undefined' for undefined", () => {
    expect(renderValue(undefined)).toBe("undefined");
  });

  it("returns string as-is", () => {
    expect(renderValue("hello")).toBe("hello");
  });

  it("JSON-stringifies objects", () => {
    expect(renderValue({ a: 1 })).toBe(JSON.stringify({ a: 1 }, null, 2));
  });

  it("handles circular references gracefully", () => {
    const obj: Record<string, unknown> = {};
    obj.self = obj;
    // Should not throw; falls back to String()
    expect(typeof renderValue(obj)).toBe("string");
  });
});

describe("toArray", () => {
  it("returns arrays as-is", () => {
    expect(toArray([1, 2])).toEqual([1, 2]);
  });

  it("returns empty array for null and undefined", () => {
    expect(toArray(null)).toEqual([]);
    expect(toArray(undefined)).toEqual([]);
  });

  it("wraps single values in array", () => {
    expect(toArray("hello")).toEqual(["hello"]);
    expect(toArray(42)).toEqual([42]);
  });
});

describe("toFiniteNumber", () => {
  it("returns finite numbers as-is", () => {
    expect(toFiniteNumber(42)).toBe(42);
    expect(toFiniteNumber(0)).toBe(0);
  });

  it("returns null for Infinity and NaN", () => {
    expect(toFiniteNumber(Infinity)).toBeNull();
    expect(toFiniteNumber(NaN)).toBeNull();
  });

  it("parses numeric strings", () => {
    expect(toFiniteNumber("3.14")).toBe(3.14);
    expect(toFiniteNumber("42")).toBe(42);
  });

  it("returns null for non-numeric strings", () => {
    expect(toFiniteNumber("abc")).toBeNull();
    expect(toFiniteNumber("")).toBeNull();
    expect(toFiniteNumber("  ")).toBeNull();
  });

  it("returns null for non-number types", () => {
    expect(toFiniteNumber(null)).toBeNull();
    expect(toFiniteNumber(undefined)).toBeNull();
    expect(toFiniteNumber({})).toBeNull();
  });
});

describe("toAssistantMessage", () => {
  it("formats decision response for Japanese", () => {
    const payload = {
      decision_status: "allow",
      gate_decision: "allow",
      business_decision: "APPROVE",
      next_action: "EXECUTE_WITH_STANDARD_MONITORING",
      human_review_required: false,
      chosen: "Option A",
      rejection_reason: null,
    } as DecideResponse;
    const t = (ja: string, _en: string) => ja;
    const message = toAssistantMessage(payload, t);
    expect(message).toContain("案件状態: APPROVE");
    expect(message).toContain("ゲート判定: allow (案件承認ではなく、応答出力可)");
    expect(message).toContain("次アクション: EXECUTE_WITH_STANDARD_MONITORING");
    expect(message).toContain("採択案: Option A");
    expect(message).toContain("拒否理由: なし");
  });

  it("formats decision response for English", () => {
    const payload = {
      decision_status: "rejected",
      gate_decision: "deny",
      business_decision: "DENY",
      next_action: "DO_NOT_EXECUTE",
      human_review_required: true,
      chosen: null,
      refusal_reason: "Too risky",
    } as unknown as DecideResponse;
    const t = (_ja: string, en: string) => en;
    const message = toAssistantMessage(payload, t);
    expect(message).toContain("Business Decision: DENY");
    expect(message).toContain("Gate Decision: deny");
    expect(message).toContain("Next Action: DO_NOT_EXECUTE");
    expect(message).toContain("Human Review: required");
    expect(message).toContain("Chosen: none");
    expect(message).toContain("Rejection: Too risky");
  });

  it("prefers user_summary when present (simple_qa mode)", () => {
    const payload = {
      decision_status: "allow",
      chosen: { id: "abc", title: "現在時刻は 14:30 頃です" },
      rejection_reason: null,
      user_summary: "現在時刻は 14:30 (UTC) です。\nサーバーのシステム時刻から取得しています。",
    } as unknown as DecideResponse;
    const t = (ja: string, _en: string) => ja;
    const message = toAssistantMessage(payload, t);
    expect(message).toBe("現在時刻は 14:30 (UTC) です。\nサーバーのシステム時刻から取得しています。");
    expect(message).not.toContain("判定");
    expect(message).not.toContain("採択案");
    expect(message).not.toContain("id");
    expect(message).not.toContain("score");
  });

  it("falls back to structured format when user_summary is null", () => {
    const payload = {
      decision_status: "allow",
      chosen: { id: "x", title: "Option X" },
      rejection_reason: null,
      user_summary: null,
    } as unknown as DecideResponse;
    const t = (ja: string, _en: string) => ja;
    const message = toAssistantMessage(payload, t);
    expect(message).toContain("案件状態: HOLD");
    expect(message).toContain("採択案:");
  });

  it("falls back to structured format when user_summary is empty string", () => {
    const payload = {
      decision_status: "allow",
      chosen: { id: "x", title: "Option X" },
      rejection_reason: null,
      user_summary: "   ",
    } as unknown as DecideResponse;
    const t = (ja: string, _en: string) => ja;
    const message = toAssistantMessage(payload, t);
    expect(message).toContain("案件状態: HOLD");
  });

  it("does not present gate allow as business approval text", () => {
    const payload = {
      decision_status: "allow",
      gate_decision: "allow",
      business_decision: "REVIEW_REQUIRED",
      next_action: "ROUTE_TO_HUMAN_REVIEW",
      human_review_required: true,
      chosen: { id: "x", title: "Option X" },
      rejection_reason: null,
    } as unknown as DecideResponse;
    const t = (ja: string, _en: string) => ja;
    const message = toAssistantMessage(payload, t);
    expect(message).toContain("案件状態: REVIEW_REQUIRED");
    expect(message).not.toContain("案件状態: allow");
    expect(message).toContain("ゲート判定: allow (案件承認ではなく、応答出力可)");
  });
});
