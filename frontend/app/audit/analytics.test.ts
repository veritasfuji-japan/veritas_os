import { describe, expect, it } from "vitest";

import { buildAuditSummary, classifyChain, matchesCrossSearch } from "./analytics";

describe("audit analytics", () => {
  it("classifies broken chain with explicit reason", () => {
    const result = classifyChain(
      { sha256: "hash-c", sha256_prev: "hash-a" },
      { sha256: "hash-b" },
    );

    expect(result.status).toBe("broken");
    expect(result.reason).toContain("does not match");
  });

  it("builds summary including replay and policy distribution", () => {
    const summary = buildAuditSummary([
      {
        request_id: "req-1",
        sha256: "hash-1",
        sha256_prev: "hash-0",
        policy_version: "p1",
        replay_id: "rep-1",
      },
      {
        request_id: "req-0",
        sha256: "hash-0",
        policy_version: "p1",
      },
    ]);

    expect(summary.totalEntries).toBe(2);
    expect(summary.verified).toBe(2);
    expect(summary.replayLinked).toBe(1);
    expect(summary.policyVersionDistribution[0]).toEqual({ version: "p1", count: 2 });
  });

  it("matches cross-search on decision/replay/request/policy", () => {
    const item = {
      request_id: "req-42",
      decision_id: "dec-42",
      linked_replay_id: "rep-42",
      policy_version: "2026.03",
    };

    expect(matchesCrossSearch(item, "dec-42")).toBe(true);
    expect(matchesCrossSearch(item, "rep-42")).toBe(true);
    expect(matchesCrossSearch(item, "2026.03")).toBe(true);
    expect(matchesCrossSearch(item, "missing")).toBe(false);
  });
});
