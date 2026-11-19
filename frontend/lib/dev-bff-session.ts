/**
 * Returns whether the runtime should be treated as production.
 */
export function isProductionRuntime(): boolean {
  const veritasEnv = (process.env.VERITAS_ENV ?? "").toLowerCase();
  const nodeEnv = (process.env.NODE_ENV ?? "").toLowerCase();
  return (
    veritasEnv === "prod" ||
    veritasEnv === "production" ||
    nodeEnv === "production"
  );
}

/** Permit local shared sessions only after explicit operator opt-in. */
export function isDevBffSessionEnabled(): boolean {
  return !isProductionRuntime() && process.env.VERITAS_BFF_ENABLE_DEV_SESSION === "true";
}
