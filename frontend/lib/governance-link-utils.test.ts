import { describe, expect, it } from "vitest";

import { normalizeSafeInternalHref } from "./governance-link-utils";

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
