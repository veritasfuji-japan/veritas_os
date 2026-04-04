import { describe, it, expect } from "vitest";
import {
  getString,
  shortHash,
  toPrettyJson,
  classifyChain,
  buildHumanSummary,
  computeAuditSummary,
} from "./audit-types";
import type { TrustLogItem } from "@veritas/types";

function makeItem(overrides: Partial<TrustLogItem> = {}): TrustLogItem {
  return {
    sha256: "abc123",
    sha256_prev: "prev123",
    request_id: "req-1",
    decision_id: "dec-1",
    ...overrides,
  } as TrustLogItem;
}

describe("getString", () => {
  it("returns string value for existing key", () => {
    const item = makeItem({ stage: "retrieval" } as Partial<TrustLogItem>);
    expect(getString(item, "stage")).toBe("retrieval");
  });

  it("returns '-' for missing key", () => {
    const item = makeItem();
    expect(getString(item, "nonexistent")).toBe("-");
  });
});

describe("shortHash", () => {
  it("returns --- for nullish", () => {
    expect(shortHash(null)).toBe("---");
    expect(shortHash(undefined)).toBe("---");
  });

  it("returns short strings as-is", () => {
    expect(shortHash("abc")).toBe("abc");
  });

  it("truncates long strings", () => {
    const hash = "abcdefghijklmnopqrstuvwxyz1234567890";
    const result = shortHash(hash);
    expect(result).toContain("...");
    expect(result.length).toBeLessThan(hash.length);
  });
});

describe("toPrettyJson", () => {
  it("formats objects as indented JSON", () => {
    expect(toPrettyJson({ a: 1 })).toBe(JSON.stringify({ a: 1 }, null, 2));
  });
});

describe("classifyChain", () => {
  it("returns missing when current sha256 is absent", () => {
    const item = makeItem({ sha256: undefined });
    expect(classifyChain(item, null)).toEqual({ status: "missing", reason: "current sha256 missing" });
  });

  it("returns verified for genesis entry (no prev, no previous item)", () => {
    const item = makeItem({ sha256_prev: undefined });
    expect(classifyChain(item, null)).toEqual({ status: "verified", reason: "genesis entry" });
  });

  it("returns orphan when sha256_prev missing but previous exists", () => {
    const item = makeItem({ sha256_prev: undefined });
    const prev = makeItem();
    expect(classifyChain(item, prev)).toEqual({ status: "orphan", reason: "no sha256_prev while previous exists" });
  });

  it("returns missing when previous sha256 is absent", () => {
    const item = makeItem({ sha256_prev: "some" });
    const prev = makeItem({ sha256: undefined });
    expect(classifyChain(item, prev)).toEqual({ status: "missing", reason: "previous sha256 missing" });
  });

  it("returns broken when hashes do not match", () => {
    const item = makeItem({ sha256_prev: "wrong" });
    const prev = makeItem({ sha256: "correct" });
    expect(classifyChain(item, prev)).toEqual({ status: "broken", reason: "sha256_prev does not match previous sha256" });
  });

  it("returns verified when hashes match", () => {
    const item = makeItem({ sha256_prev: "match" });
    const prev = makeItem({ sha256: "match" });
    expect(classifyChain(item, prev)).toEqual({ status: "verified", reason: "hash chain match" });
  });
});

describe("buildHumanSummary", () => {
  it("builds readable summary", () => {
    const item = makeItem({ stage: "safety", status: "pass", request_id: "req-123", severity: "low" } as Partial<TrustLogItem>);
    const summary = buildHumanSummary(item);
    expect(summary).toContain("safety");
    expect(summary).toContain("pass");
    expect(summary).toContain("req-123");
    expect(summary).toContain("low");
  });
});

describe("computeAuditSummary", () => {
  it("computes correct summary from items", () => {
    const items: TrustLogItem[] = [
      makeItem({ sha256: "a", sha256_prev: "b", replay_id: "r1", policy_version: "v1" }),
      makeItem({ sha256: "b", sha256_prev: undefined }),
    ];
    const summary = computeAuditSummary(items);
    expect(summary.total).toBe(2);
    expect(summary.replayLinked).toBe(1);
    expect(summary.policyVersions["v1"]).toBe(1);
  });

  it("returns zero counts for empty array", () => {
    const summary = computeAuditSummary([]);
    expect(summary.total).toBe(0);
    expect(summary.verified).toBe(0);
  });
});
