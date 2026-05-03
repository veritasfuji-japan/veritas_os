export type SourceState = "live" | "fixture" | "demo" | "unavailable";

/**
 * Resolve display provenance for Mission Control cards.
 */
export function resolveSourceState(value: unknown, options?: { demo?: boolean; fixture?: boolean }): SourceState {
  if (options?.demo) {
    return "demo";
  }
  if (options?.fixture) {
    return "fixture";
  }
  if (value === null || value === undefined || value === "") {
    return "unavailable";
  }
  return "live";
}

export function resolveGovernanceSourceState(source?: string | null, demoScenario?: string | null): SourceState {
  if (demoScenario) {
    return "demo";
  }
  if (!source || source === "none" || source === "pre_bind_artifact_retrieval_failed") {
    return "unavailable";
  }
  if (source.includes("trustlog") || source.includes("latest_bind_receipt")) {
    return "live";
  }
  return "fixture";
}
