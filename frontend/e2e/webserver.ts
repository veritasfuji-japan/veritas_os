/**
 * Returns the Playwright webServer command used by e2e tests.
 *
 * CI must reuse the already-built bundle from workflow steps for stability.
 */
const E2E_PORT = 4173;

/**
 * Returns canonical E2E server URL used by Playwright.
 */
export function getE2EBaseUrl(): string {
  return `http://127.0.0.1:${E2E_PORT}`;
}

export function getE2EWebServerCommand(isCi: boolean): string {
  if (isCi) {
    return `pnpm start -H 127.0.0.1 -p ${E2E_PORT}`;
  }
  return `pnpm dev --port ${E2E_PORT}`;
}
