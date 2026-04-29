import { type PreBindGovernanceSnapshot } from "./dashboard-types";

const DEFAULT_GOVERNANCE_LAYER_SNAPSHOT: PreBindGovernanceSnapshot = {
  participation_state: "participatory",
  preservation_state: "open",
  intervention_viability: "high",
  concise_rationale:
    "pre-bind participation and preservation signals remain stable before bind classification.",
  bind_outcome: "BLOCKED",
};

export interface MissionGovernanceIngressPayload {
  governance_layer_snapshot?: PreBindGovernanceSnapshot;
  pre_bind_governance_snapshot?: PreBindGovernanceSnapshot;
}

function selectLiveGovernanceSnapshot(
  payload?: MissionGovernanceIngressPayload | null,
): PreBindGovernanceSnapshot | undefined {
  return payload?.governance_layer_snapshot ?? payload?.pre_bind_governance_snapshot;
}

/**
 * Resolves Mission Control governance snapshot from live ingress payload first,
 * then contracts down to the minimal fallback snapshot for render safety.
 */
export function resolveMissionGovernanceSnapshot(
  payload?: MissionGovernanceIngressPayload | null,
): PreBindGovernanceSnapshot {
  return selectLiveGovernanceSnapshot(payload) ?? DEFAULT_GOVERNANCE_LAYER_SNAPSHOT;
}
