import { headers } from "next/headers";

import { type MissionGovernanceIngressPayload } from "../components/mission-governance-adapter";

import { areE2EScenariosEnabled } from "./e2e-scenarios";

const GOVERNANCE_REPORT_ENDPOINT = "/api/veritas/v1/report/governance";
const E2E_SCENARIO_HEADER = "x-veritas-e2e-governance-scenario";
const E2E_SCENARIO_QUERY = "e2e_governance_scenario";
const DEMO_SCENARIO_HEADER = "x-veritas-demo-scenario";
const DEMO_SCENARIO_QUERY = "demo_scenario";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/**
 * Maps backend governance feed payload into Mission Control ingress contract.
 */
export function mapGovernanceFeedToIngressPayload(
  payload: unknown,
): MissionGovernanceIngressPayload | null {
  if (!isRecord(payload)) {
    return null;
  }

  const governanceLayerSnapshot = payload.governance_layer_snapshot;
  if (isRecord(governanceLayerSnapshot)) {
    return {
      governance_layer_snapshot: governanceLayerSnapshot,
    };
  }

  const preBindGovernanceSnapshot = payload.pre_bind_governance_snapshot;
  if (isRecord(preBindGovernanceSnapshot)) {
    return {
      pre_bind_governance_snapshot: preBindGovernanceSnapshot,
    };
  }

  return null;
}

/**
 * Main path: backend-fed governance feed. Fallback is adapter-level render safety.
 */
async function resolveE2EScenarioHeader(): Promise<string | null> {
  try {
    const requestHeaders = await headers();
    const scenario = requestHeaders.get(E2E_SCENARIO_HEADER);
    return scenario ? scenario.trim() : null;
  } catch {
    return null;
  }
}



async function resolveRequestOrigin(): Promise<string | null> {
  try {
    const requestHeaders = await headers();
    const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host");
    if (!host) {
      return null;
    }

    const proto =
      requestHeaders.get("x-forwarded-proto") ??
      (host.includes("localhost") || host.startsWith("127.0.0.1") ? "http" : "https");

    return `${proto}://${host}`;
  } catch {
    return null;
  }
}

function buildGovernanceFeedEndpoint(pathWithQuery: string, origin: string | null): string {
  return origin ? `${origin}${pathWithQuery}` : pathWithQuery;
}

export async function loadMissionControlIngressPayload(
  scenarioOverride?: string | null,
  demoScenarioOverride?: string | null,
): Promise<MissionGovernanceIngressPayload | null> {
  try {
    const scenario = areE2EScenariosEnabled()
      ? scenarioOverride?.trim() || (await resolveE2EScenarioHeader())
      : null;
    const demoScenario = demoScenarioOverride?.trim() || null;
    const endpointParams = new URLSearchParams();
    if (scenario) {
      endpointParams.set(E2E_SCENARIO_QUERY, scenario);
    }
    if (demoScenario) {
      endpointParams.set(DEMO_SCENARIO_QUERY, demoScenario);
    }
    const endpointPath = endpointParams.size > 0
      ? `${GOVERNANCE_REPORT_ENDPOINT}?${endpointParams.toString()}`
      : GOVERNANCE_REPORT_ENDPOINT;
    const origin = await resolveRequestOrigin();
    const endpoint = buildGovernanceFeedEndpoint(endpointPath, origin);

    const response = await fetch(endpoint, {
      method: "GET",
      cache: "no-store",
      headers: scenario || demoScenario
        ? {
          ...(scenario ? { [E2E_SCENARIO_HEADER]: scenario } : {}),
          ...(demoScenario ? { [DEMO_SCENARIO_HEADER]: demoScenario } : {}),
        }
        : undefined,
    });

    if (!response.ok) {
      return null;
    }

    const payload = (await response.json()) as unknown;
    return mapGovernanceFeedToIngressPayload(payload);
  } catch {
    return null;
  }
}
