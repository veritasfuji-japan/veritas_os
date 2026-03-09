/**
 * Returns the Playwright webServer command used by e2e tests.
 *
 * CI must use pnpm scripts to avoid npx/npm resolution drift in workspaces.
 */
export function getE2EWebServerCommand(isCi: boolean): string {
  if (isCi) {
    return "pnpm build && pnpm start -H 127.0.0.1 -p 3000";
  }
  return "pnpm dev --port 3000";
}
