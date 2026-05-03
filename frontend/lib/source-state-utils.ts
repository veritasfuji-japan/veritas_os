export type SourceState = "live" | "fixture" | "demo" | "unavailable";
export type SourceStateReason =
  | "runtime_snapshot"
  | "trustlog_matching_decision"
  | "latest_bind_receipt"
  | "deterministic_fixture"
  | "static_fixture"
  | "demo_scenario"
  | "missing_payload"
  | "connector_unavailable"
  | "retrieval_failed"
  | "unknown_source";
export interface SourceStateResolution {
  state: SourceState;
  reason: SourceStateReason;
}

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

export function resolveOperationalSourceState(value: unknown): SourceStateResolution {
  if (value === null || value === undefined || value === "") {
    return { state: "unavailable", reason: "missing_payload" };
  }
  return { state: "live", reason: "runtime_snapshot" };
}

export function resolveStaticFixtureSourceState(value: unknown): SourceStateResolution {
  if (value === null || value === undefined || value === "") {
    return { state: "unavailable", reason: "missing_payload" };
  }
  return { state: "fixture", reason: "static_fixture" };
}

export function resolveDemoSourceState(value: unknown, hasScenario = true): SourceStateResolution {
  if (!hasScenario) {
    return resolveOperationalSourceState(value);
  }
  if (value === null || value === undefined || value === "") {
    return { state: "unavailable", reason: "missing_payload" };
  }
  return { state: "demo", reason: "demo_scenario" };
}

export function resolveUnavailableSourceState(reason: SourceStateReason = "unknown_source"): SourceStateResolution {
  return { state: "unavailable", reason };
}
