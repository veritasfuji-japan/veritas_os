/**
 * Returns the Playwright webServer command used by e2e tests.
 *
 * CI must reuse the already-built bundle from workflow steps for stability.
 */
export function getE2EWebServerCommand(isCi: boolean): string {
  if (isCi) {
    return "pnpm start -H 127.0.0.1 -p 3000";
  }
  return "pnpm dev --port 3000";
}
