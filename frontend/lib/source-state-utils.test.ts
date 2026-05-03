import { describe, expect, it } from "vitest";

import { resolveGovernanceSourceState, resolveSourceState } from "./source-state-utils";

describe("resolveSourceState", () => {
  it("resolves live / fixture / demo / unavailable", () => {
    expect(resolveSourceState({ ok: true })).toBe("live");
    expect(resolveSourceState({ ok: true }, { fixture: true })).toBe("fixture");
    expect(resolveSourceState({ ok: true }, { demo: true })).toBe("demo");
    expect(resolveSourceState(null)).toBe("unavailable");
  });
});

describe("resolveGovernanceSourceState", () => {
  it("maps governance source into source-state", () => {
    expect(resolveGovernanceSourceState("trustlog_matching_decision", null)).toBe("live");
    expect(resolveGovernanceSourceState("sample_data", null)).toBe("fixture");
    expect(resolveGovernanceSourceState("none", null)).toBe("unavailable");
    expect(resolveGovernanceSourceState("trustlog_matching_decision", "pre_boundary_collapse")).toBe("demo");
  });
});
