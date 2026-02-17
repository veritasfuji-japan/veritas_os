import { defineConfig } from "@playwright/test";

const PORT = Number(process.env.E2E_FRONTEND_PORT ?? 3000);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  timeout: 180_000,
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: [
    {
      command:
        "bash -lc 'cd .. && VERITAS_API_KEY=${VERITAS_API_KEY:-test-e2e-key} python -m uvicorn veritas_os.api.server:app --host 0.0.0.0 --port 8000'",
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: true,
      timeout: 180000,
    },
    {
      command:
        "bash -lc 'BACKEND_URL=http://127.0.0.1:8000 NEXT_PUBLIC_E2E=1 NEXT_PUBLIC_VERITAS_API_KEY=${VERITAS_API_KEY:-test-e2e-key} pnpm dev --port 3000'",
      url: `http://127.0.0.1:${PORT}`,
      reuseExistingServer: true,
      timeout: 180000,
    },
  ],
});
