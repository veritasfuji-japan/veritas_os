const E2E_SCENARIOS_FLAG = "VERITAS_ENABLE_E2E_SCENARIOS";

/**
 * Returns true only in explicit test contexts where deterministic E2E scenario injection is allowed.
 */
export function areE2EScenariosEnabled(): boolean {
  return process.env.NODE_ENV === "test" || process.env[E2E_SCENARIOS_FLAG] === "1";
}
