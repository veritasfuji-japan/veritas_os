import { defineConfig, devices } from "@playwright/test";

import { getE2EBaseUrl, getE2EWebServerCommand } from "./e2e/webserver";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 1,
  workers: 1,
  reporter: [["html", { open: "never" }], ["list"]],
  timeout: 30_000,
  use: {
    baseURL: getE2EBaseUrl(),
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: getE2EWebServerCommand(Boolean(process.env.CI)),
    url: getE2EBaseUrl(),
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
