import { describe, expect, it } from "vitest";

import { getE2EBaseUrl, getE2EWebServerCommand } from "../e2e/webserver";

describe("getE2EWebServerCommand", () => {
  it("returns deterministic CI command that reuses prebuilt output", () => {
    expect(getE2EWebServerCommand(true)).toBe(
      "pnpm start -H 127.0.0.1 -p 4173",
    );
  });

  it("returns local dev command with explicit port", () => {
    expect(getE2EWebServerCommand(false)).toBe("pnpm dev --port 4173");
  });

  it("returns canonical localhost base url", () => {
    expect(getE2EBaseUrl()).toBe("http://127.0.0.1:4173");
  });
});
