import { type PreBindGovernanceSnapshot } from "./dashboard-types";

const DEFAULT_GOVERNANCE_LAYER_SNAPSHOT: PreBindGovernanceSnapshot = {
  participation_state: "participatory",
  preservation_state: "open",
  intervention_viability: "high",
  concise_rationale:
    "pre-bind participation and preservation signals remain stable before bind classification.",
  bind_outcome: "BLOCKED",
};

interface MissionGovernanceIngressPayload {
  governance_layer_snapshot?: PreBindGovernanceSnapshot;
  pre_bind_governance_snapshot?: PreBindGovernanceSnapshot;
}

/**
 * Resolves Mission Control governance snapshot from live ingress payload first,
 * then contracts down to the minimal fallback snapshot for render safety.
 */
export function resolveMissionGovernanceSnapshot(
  payload?: MissionGovernanceIngressPayload | null,
): PreBindGovernanceSnapshot {
  if (payload?.governance_layer_snapshot) {
    return payload.governance_layer_snapshot;
  }

  if (payload?.pre_bind_governance_snapshot) {
    return payload.pre_bind_governance_snapshot;
  }

  return DEFAULT_GOVERNANCE_LAYER_SNAPSHOT;
}

