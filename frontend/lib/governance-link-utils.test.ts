import { describe, expect, it } from "vitest";

import { buildAuditArtifactHref, normalizeSafeInternalHref } from "./governance-link-utils";

describe("normalizeSafeInternalHref", () => {
  it("returns trimmed safe internal paths", () => {
    expect(normalizeSafeInternalHref("/governance")).toBe("/governance");
    expect(normalizeSafeInternalHref("/governance/receipts/br_123")).toBe("/governance/receipts/br_123");
    expect(normalizeSafeInternalHref(" /audit?receipt=br_123 ")).toBe("/audit?receipt=br_123");
  });

  it("rejects non-string or empty values", () => {
    expect(normalizeSafeInternalHref(null)).toBeNull();
    expect(normalizeSafeInternalHref(undefined)).toBeNull();
    expect(normalizeSafeInternalHref({ href: "/governance" })).toBeNull();
    expect(normalizeSafeInternalHref("   ")).toBeNull();
  });

  it("rejects external or protocol-based URLs", () => {
    expect(normalizeSafeInternalHref("https://evil.example")).toBeNull();
    expect(normalizeSafeInternalHref("http://evil.example")).toBeNull();
    expect(normalizeSafeInternalHref("javascript:alert(1)")).toBeNull();
    expect(normalizeSafeInternalHref("data:text/html,<script>alert(1)</script>")).toBeNull();
    expect(normalizeSafeInternalHref("//evil.example")).toBeNull();
  });

  it("rejects malformed internal paths", () => {
    expect(normalizeSafeInternalHref("/foo\\bar")).toBeNull();
    expect(normalizeSafeInternalHref("/foo\nbar")).toBeNull();
    expect(normalizeSafeInternalHref("/foo\tbar")).toBeNull();
    expect(normalizeSafeInternalHref("/foo\rbar")).toBeNull();
  });
});


describe("buildAuditArtifactHref", () => {
  it("builds safe audit query links for supported artifact keys", () => {
    expect(buildAuditArtifactHref("bind_receipt_id", "br_123")).toBe("/audit?bind_receipt_id=br_123");
    expect(buildAuditArtifactHref("decision_id", "dec_123")).toBe("/audit?decision_id=dec_123");
    expect(buildAuditArtifactHref("execution_intent_id", "ei_123")).toBe("/audit?execution_intent_id=ei_123");
  });

  it("rejects unsafe or malformed artifact ids", () => {
    const unsafeValues: unknown[] = [
      null,
      undefined,
      {},
      "",
      "   ",
      "br\n123",
      "br\t123",
      "br\\123",
      "../secret",
      "/audit?x=1",
      "https://evil.example",
      "javascript:alert(1)",
    ];

    unsafeValues.forEach((value) => {
      expect(buildAuditArtifactHref("bind_receipt_id", value)).toBeNull();
    });
  });
});
