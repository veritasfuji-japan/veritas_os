import { describe, it, expect } from "vitest";
import { PAGE_LIMIT, STATUS_COLORS, STATUS_BG, STATUS_DOT } from "./constants";

describe("audit constants", () => {
  it("PAGE_LIMIT is 50", () => {
    expect(PAGE_LIMIT).toBe(50);
  });

  it("STATUS_COLORS covers all verification statuses", () => {
    expect(STATUS_COLORS.verified).toContain("success");
    expect(STATUS_COLORS.broken).toContain("danger");
    expect(STATUS_COLORS.missing).toContain("warning");
    expect(STATUS_COLORS.orphan).toContain("info");
  });

  it("STATUS_BG covers all verification statuses", () => {
    for (const key of ["verified", "broken", "missing", "orphan"] as const) {
      expect(STATUS_BG[key]).toBeTruthy();
    }
  });

  it("STATUS_DOT covers all verification statuses", () => {
    for (const key of ["verified", "broken", "missing", "orphan"] as const) {
      expect(STATUS_DOT[key]).toBeTruthy();
    }
  });
});
