import { describe, expect, it } from "vitest";

import { buildApiUrl } from "./api";

describe("buildApiUrl", () => {
  it("prefixes backend paths with same-origin /api", () => {
    expect(buildApiUrl("/v1/decide")).toBe("/api/v1/decide");
    expect(buildApiUrl("v1/trust/logs")).toBe("/api/v1/trust/logs");
  });
});
