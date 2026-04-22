import { describe, expect, it, vi } from "vitest";
import {
  filterCanonicalReceipts,
  normalizeBindReceipt,
  normalizeBindOutcome,
  parseBindReceiptDetailPayload,
  parseBindReceiptListPayload,
} from "./bind-cockpit-normalization";

describe("bind-cockpit-normalization", () => {
  it("normalizes canonical bind outcomes", () => {
    expect(normalizeBindOutcome("committed")).toBe("COMMITTED");
    expect(normalizeBindOutcome("SUCCESS")).toBe("COMMITTED");
    expect(normalizeBindOutcome("unexpected")).toBe("UNKNOWN");
  });

  it("parses list/detail payload safely", () => {
    expect(parseBindReceiptListPayload({ items: [{ bind_receipt_id: "br-1" }], count: 1 }).items).toHaveLength(1);
    expect(parseBindReceiptListPayload({ bad: [] }).items).toHaveLength(0);
    expect(parseBindReceiptDetailPayload({ bind_receipt: { bind_receipt_id: "br-1" } })?.bind_receipt_id).toBe("br-1");
    expect(parseBindReceiptDetailPayload({ bind_receipt: {} })).toBeNull();
  });

  it("normalizes path, checks, and operator step", () => {
    const normalized = normalizeBindReceipt({
      bind_receipt_id: "br-7",
      target_path: "/v1/governance/policy-bundles/promote",
      final_outcome: "blocked",
      bind_reason_code: "APPROVAL_MISSING",
      authority_check_result: { passed: true },
      constraint_check_result: { result: "deny" },
    });
    expect(normalized.targetPathType).toBe("policy_bundle_promotion");
    expect(normalized.outcome).toBe("BLOCKED");
    expect(normalized.checks.authority).toBe("PASS");
    expect(normalized.checks.constraint).toBe("FAIL");
    expect(normalized.nextOperatorStep).toContain("Policy / approval / input assumptions");
  });

  it("filters by path/outcome/reason/lineage and recent", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-22T12:00:00Z"));

    const committed = normalizeBindReceipt({
      bind_receipt_id: "br-1",
      target_path: "/v1/governance/policy",
      final_outcome: "COMMITTED",
      occurred_at: "2026-04-22T10:00:00Z",
      bind_reason_code: "OK",
      decision_id: "dec-1",
    });
    const blockedOld = normalizeBindReceipt({
      bind_receipt_id: "br-2",
      target_path: "/v1/compliance/config",
      final_outcome: "BLOCKED",
      occurred_at: "2026-04-20T10:00:00Z",
      bind_reason_code: "DENY",
      decision_id: "dec-2",
    });

    const filtered = filterCanonicalReceipts([committed, blockedOld], {
      pathType: "compliance_config_update",
      outcome: "BLOCKED",
      reasonCode: "deny",
      lineageQuery: "dec-2",
      failedOnly: true,
      recentOnly: false,
    });
    expect(filtered).toHaveLength(1);

    const recentOnly = filterCanonicalReceipts([committed, blockedOld], {
      pathType: "all",
      outcome: "all",
      reasonCode: "",
      lineageQuery: "",
      failedOnly: false,
      recentOnly: true,
    });
    expect(recentOnly.map((item) => item.bindReceiptId)).toEqual(["br-1"]);
    vi.useRealTimers();
  });
});
