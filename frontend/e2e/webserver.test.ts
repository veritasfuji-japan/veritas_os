import { describe, expect, it } from "vitest";

import { getE2EWebServerCommand } from "./webserver";

describe("getE2EWebServerCommand", () => {
  it("returns deterministic CI command using pnpm scripts", () => {
    expect(getE2EWebServerCommand(true)).toBe(
      "pnpm build && pnpm start -H 127.0.0.1 -p 3000",
    );
  });

  it("returns local dev command with explicit port", () => {
    expect(getE2EWebServerCommand(false)).toBe("pnpm dev --port 3000");
  });
});
