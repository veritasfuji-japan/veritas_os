import { describe, expect, it } from "vitest";

import { getE2EWebServerCommand } from "./webserver";

describe("getE2EWebServerCommand", () => {
  it("returns CI command that reuses existing build artifacts", () => {
    expect(getE2EWebServerCommand(true)).toBe(
      "test -f .next/BUILD_ID || pnpm build; pnpm start -H 127.0.0.1 -p 3000",
    );
  });

  it("returns local dev command with explicit port", () => {
    expect(getE2EWebServerCommand(false)).toBe("pnpm dev --port 3000");
  });
});
