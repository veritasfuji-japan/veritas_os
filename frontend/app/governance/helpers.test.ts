import { describe, it, expect } from "vitest";
import { deepEqual, collectChanges, bumpDraftVersion } from "./helpers";

describe("deepEqual", () => {
  it("returns true for identical primitives", () => {
    expect(deepEqual(1, 1)).toBe(true);
    expect(deepEqual("a", "a")).toBe(true);
    expect(deepEqual(null, null)).toBe(true);
  });

  it("returns false for different primitives", () => {
    expect(deepEqual(1, 2)).toBe(false);
    expect(deepEqual("a", "b")).toBe(false);
  });

  it("returns false when types differ", () => {
    expect(deepEqual(1, "1")).toBe(false);
    expect(deepEqual(null, undefined)).toBe(false);
  });

  it("compares arrays deeply", () => {
    expect(deepEqual([1, 2], [1, 2])).toBe(true);
    expect(deepEqual([1, 2], [1, 3])).toBe(false);
    expect(deepEqual([1], [1, 2])).toBe(false);
  });

  it("compares nested objects deeply", () => {
    expect(deepEqual({ a: { b: 1 } }, { a: { b: 1 } })).toBe(true);
    expect(deepEqual({ a: { b: 1 } }, { a: { b: 2 } })).toBe(false);
  });

  it("returns false for array vs object", () => {
    expect(deepEqual([1], { 0: 1 })).toBe(false);
  });
});

describe("collectChanges", () => {
  it("detects added and changed keys", () => {
    const changes = collectChanges("", { a: 1 }, { a: 2, b: 3 });
    expect(changes).toHaveLength(2);
    expect(changes[0]).toMatchObject({ path: "a", old: "1", next: "2" });
    expect(changes[1]).toMatchObject({ path: "b", next: "3" });
  });

  it("categorizes paths correctly", () => {
    const changes = collectChanges("", { fuji_rules: 1 }, { fuji_rules: 2 });
    expect(changes[0].category).toBe("rule");
  });

  it("categorizes risk thresholds", () => {
    const changes = collectChanges("", { risk_thresholds: 1 }, { risk_thresholds: 2 });
    expect(changes[0].category).toBe("threshold");
  });

  it("categorizes auto_stop as escalation", () => {
    const changes = collectChanges("", { auto_stop: true }, { auto_stop: false });
    expect(changes[0].category).toBe("escalation");
  });

  it("categorizes log_retention as retention", () => {
    const changes = collectChanges("", { log_retention: 30 }, { log_retention: 90 });
    expect(changes[0].category).toBe("retention");
  });

  it("categorizes rollout_controls as rollout", () => {
    const changes = collectChanges("", { rollout_controls: "a" }, { rollout_controls: "b" });
    expect(changes[0].category).toBe("rollout");
  });

  it("categorizes approval_workflow as approval", () => {
    const changes = collectChanges("", { approval_workflow: "x" }, { approval_workflow: "y" });
    expect(changes[0].category).toBe("approval");
  });

  it("defaults unknown paths to meta", () => {
    const changes = collectChanges("", { name: "a" }, { name: "b" });
    expect(changes[0].category).toBe("meta");
  });

  it("recurses into nested objects", () => {
    const changes = collectChanges("", { a: { b: 1 } }, { a: { b: 2 } });
    expect(changes[0].path).toBe("a.b");
  });

  it("returns empty when objects are equal", () => {
    expect(collectChanges("", { a: 1 }, { a: 1 })).toHaveLength(0);
  });
});

describe("bumpDraftVersion", () => {
  it("increments trailing number and appends -draft", () => {
    expect(bumpDraftVersion("1.0.3")).toBe("1.0.4-draft");
  });

  it("appends -draft.1 when version has no trailing number pattern", () => {
    expect(bumpDraftVersion("alpha")).toBe("alpha-draft.1");
  });
});
