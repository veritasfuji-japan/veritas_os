import { headers } from "next/headers";

import { mapGovernanceFeedToIngressPayload, type MissionGovernanceIngressPayload } from "../components/mission-governance-adapter";

import { GET as readGovernanceFeed } from "./api/veritas/v1/report/governance/route";
import { areE2EScenariosEnabled } from "./e2e-scenarios";

const GOVERNANCE_REPORT_ENDPOINT = "/api/veritas/v1/report/governance";
const E2E_SCENARIO_HEADER = "x-veritas-e2e-governance-scenario";
const E2E_SCENARIO_QUERY = "e2e_governance_scenario";
const DEMO_SCENARIO_QUERY = "demo_scenario";

export async function loadMissionControlIngressPayload(
  scenarioOverride?: string | null,
  demoScenarioOverride?: string | null,
): Promise<MissionGovernanceIngressPayload | null> {
  try {
    const requestHeaders = await headers();
    const scenario = areE2EScenariosEnabled()
      ? scenarioOverride?.trim() || requestHeaders.get(E2E_SCENARIO_HEADER)?.trim()
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
    const credentials = new Headers();
    for (const name of ["authorization", "cookie"]) {
      const value = requestHeaders.get(name);
      if (value !== null) {
        credentials.set(name, value);
      }
    }
    // Invoke the same handler in-process so credentials never travel via an
    // origin derived from inbound host headers.
    const response = await readGovernanceFeed(
      new Request(new URL(endpointPath, "http://localhost"), { headers: credentials }),
    );

    if (!response.ok) {
      return null;
    }

    const payload = (await response.json()) as unknown;
    return mapGovernanceFeedToIngressPayload(payload);
  } catch {
    return null;
  }
}
