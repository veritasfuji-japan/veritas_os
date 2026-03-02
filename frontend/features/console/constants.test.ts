import { afterEach, describe, expect, it, vi } from "vitest";

import { isDangerPresetsEnabled } from "./constants";

describe("isDangerPresetsEnabled", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("returns true only in non-production when explicit opt-in is enabled", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_ENABLE_DANGER_PRESETS", "true");

    expect(isDangerPresetsEnabled()).toBe(true);
  });

  it("returns false in production even if opt-in is set", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_ENABLE_DANGER_PRESETS", "true");

    expect(isDangerPresetsEnabled()).toBe(false);
  });

  it("returns false when opt-in is not explicitly enabled", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_ENABLE_DANGER_PRESETS", "false");

    expect(isDangerPresetsEnabled()).toBe(false);
  });
});
