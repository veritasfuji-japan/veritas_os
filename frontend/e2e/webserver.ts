/**
 * Returns the Playwright webServer command used by e2e tests.
 *
 * CI pipeline already performs a dedicated frontend build step before e2e.
 * To reduce flaky reruns/timeouts, CI reuses existing `.next` output and only
 * falls back to `pnpm build` when build artifacts are missing.
 */
export function getE2EWebServerCommand(isCi: boolean): string {
  if (isCi) {
    return "test -f .next/BUILD_ID || pnpm build; pnpm start -H 127.0.0.1 -p 3000";
  }
  return "pnpm dev --port 3000";
}
