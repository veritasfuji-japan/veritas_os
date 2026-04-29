import { type MissionGovernanceIngressPayload } from "../components/mission-governance-adapter";

const GOVERNANCE_REPORT_ENDPOINT = "/api/veritas/v1/report/governance";

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
export async function loadMissionControlIngressPayload(): Promise<MissionGovernanceIngressPayload | null> {
  try {
    const response = await fetch(GOVERNANCE_REPORT_ENDPOINT, {
      method: "GET",
      cache: "no-store",
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
