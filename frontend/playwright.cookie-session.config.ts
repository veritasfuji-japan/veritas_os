import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e-cookie-session",
  workers: 1,
  retries: 0,
  reporter: [["html", { open: "never", outputFolder: "playwright-report/cookie-session" }], ["list"]],
  outputDir: "test-results/cookie-session",
  use: { baseURL: "http://127.0.0.1:3101", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "pnpm exec next start -H 127.0.0.1 -p 3101",
    url: "http://127.0.0.1:3101",
    reuseExistingServer: false,
    timeout: 60_000,
    env: {
      ...process.env,
      NODE_ENV: "production",
      VERITAS_ENV: "local",
      // Synthetic fixture only: normal production issuance remains disabled.
      VERITAS_BFF_ALLOW_GLOBAL_SESSION_IN_PROD: "true",
      VERITAS_BFF_SESSION_TOKEN: "cookie-path-admin-test-only",
      VERITAS_BFF_AUTH_TOKENS_JSON: JSON.stringify({
        "cookie-path-admin-test-only": "admin", "cookie-path-viewer-test-only": "viewer",
      }),
      // No backend requests or business operations are possible in this fixture.
      VERITAS_API_BASE_URL: "",
      NEXT_PUBLIC_VERITAS_API_BASE_URL: "",
      VERITAS_API_KEY: "",
    },
  },
});
