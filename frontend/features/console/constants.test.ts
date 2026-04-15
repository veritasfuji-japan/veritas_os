import { afterEach, describe, expect, it, vi } from "vitest";

import { DECISION_SAMPLE_QUESTIONS, isDangerPresetsEnabled } from "./constants";

describe("isDangerPresetsEnabled", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("returns true only in non-production when explicit opt-in is enabled", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_ENABLE_DANGER_PRESETS", "true");

    expect(isDangerPresetsEnabled()).toBe(true);
  });

  it("returns false in production even if opt-in is set", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_ENABLE_DANGER_PRESETS", "true");

    expect(isDangerPresetsEnabled()).toBe(false);
  });

  it("returns false when opt-in is not explicitly enabled", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_ENABLE_DANGER_PRESETS", "false");

    expect(isDangerPresetsEnabled()).toBe(false);
  });
});

describe("DECISION_SAMPLE_QUESTIONS", () => {
  it("includes regression-focused prompts for the public decision schema", () => {
    expect(DECISION_SAMPLE_QUESTIONS.length).toBeGreaterThanOrEqual(6);
    expect(DECISION_SAMPLE_QUESTIONS.some((q) => q.includes("最低条件は何か"))).toBe(true);
    expect(DECISION_SAMPLE_QUESTIONS.some((q) => q.includes("人手審査境界"))).toBe(true);
    expect(DECISION_SAMPLE_QUESTIONS.some((q) => q.includes("必要証拠"))).toBe(true);
    expect(DECISION_SAMPLE_QUESTIONS.some((q) => q.includes("通しすぎと止めすぎ"))).toBe(true);
    expect(DECISION_SAMPLE_QUESTIONS.some((q) => q.includes("ルールを形式化"))).toBe(true);
    expect(DECISION_SAMPLE_QUESTIONS.some((q) => q.includes("FujiGate と Value Core"))).toBe(true);
    expect(DECISION_SAMPLE_QUESTIONS.some((q) => q.includes("gate_decision"))).toBe(true);
  });
});
