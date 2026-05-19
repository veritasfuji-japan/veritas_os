import { readFile } from "node:fs/promises";
import path from "node:path";

import { NextResponse } from "next/server";

import { resolveApiBaseUrl } from "../../../[...path]/route-config";
import { buildAmlKycReviewerWalkthroughPayload } from "../../../../../../lib/aml-kyc-reviewer-walkthrough";
import { areE2EScenariosEnabled } from "../../../../../e2e-scenarios";

const GOVERNANCE_LIVE_SNAPSHOT_PATH = "/v1/governance/live-snapshot";
const E2E_SCENARIO_HEADER = "x-veritas-e2e-governance-scenario";
const E2E_SCENARIO_QUERY = "e2e_governance_scenario";
const DEMO_SCENARIO_HEADER = "x-veritas-demo-scenario";
const DEMO_SCENARIO_QUERY = "demo_scenario";
const PRE_BOUNDARY_COLLAPSE_SCENARIO = "pre_boundary_collapse";
const AML_KYC_REVIEWER_WALKTHROUGH_SCENARIO = "aml_kyc_reviewer_walkthrough";

const PRE_BOUNDARY_COLLAPSE_PHASE_FIXTURE_FILES = [
  "pre_boundary_collapse_phase_1_open.json",
  "pre_boundary_collapse_phase_2_iterative_shaping.json",
  "pre_boundary_collapse_phase_3_collapse.json",
  "pre_boundary_collapse_phase_4_bind.json",
] as const;

function resolveE2EScenarioPayload(request: Request): Record<string, unknown> | null {
  const scenarioFromQuery = new URL(request.url).searchParams.get(E2E_SCENARIO_QUERY)?.trim();
  const scenario = scenarioFromQuery || request.headers.get(E2E_SCENARIO_HEADER)?.trim();
  if (scenario === "main") {
    return {
      governance_layer_snapshot: {
        participation_state: "decision_shaping",
        preservation_state: "degrading",
        intervention_viability: "minimal",
        bind_outcome: "ESCALATED",
      },
    };
  }

  if (scenario === "fallback") {
    return {
      governance_layer_snapshot: {
        participation_state: "participatory",
        preservation_state: "open",
        intervention_viability: "high",
        bind_outcome: "BLOCKED",
      },
    };
  }

  return null;
}

function resolveApiKey(): string {
  return (process.env.VERITAS_API_KEY ?? "").trim();
}

function normalizeGovernanceReportPayload(payload: unknown): Record<string, unknown> | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }

  const source = payload as Record<string, unknown>;
  const governanceLayerSnapshot = source.governance_layer_snapshot;
  if (typeof governanceLayerSnapshot === "object" && governanceLayerSnapshot !== null) {
    return { governance_layer_snapshot: governanceLayerSnapshot };
  }

  const preBindGovernanceSnapshot = source.pre_bind_governance_snapshot;
  if (typeof preBindGovernanceSnapshot === "object" && preBindGovernanceSnapshot !== null) {
    return { pre_bind_governance_snapshot: preBindGovernanceSnapshot };
  }

  return null;
}

function resolveDemoScenario(request: Request): string | null {
  const requestUrl = new URL(request.url);
  const scenarioFromQuery = requestUrl.searchParams.get(DEMO_SCENARIO_QUERY)?.trim();
  return scenarioFromQuery || request.headers.get(DEMO_SCENARIO_HEADER)?.trim() || null;
}

function resolveFixturePath(filename: string): string {
  return path.resolve(process.cwd(), "..", "veritas_os", "tests", "fixtures", "pre_bind", "pre_boundary_collapse", filename);
}

function mapPreBoundaryCollapsePhaseToSnapshot(phase: Record<string, unknown>): Record<string, unknown> {
  const optionExposure = phase.option_exposure as Record<string, string>;
  return {
    phase_id: phase.phase_id,
    phase_label: phase.phase_label,
    participation_state: phase.expected_participation_state,
    preservation_state: phase.expected_preservation_state,
    intervention_viability: phase.intervention_viability,
    bind_outcome: phase.expected_bind_outcome,
    concise_rationale: phase.concise_rationale,
    lineage_evidence: phase.lineage_evidence,
    effective_optionality: phase.effective_optionality,
    option_exposure_summary: Object.entries(optionExposure)
      .map(([option, exposure]) => `${option}:${exposure}`)
      .join(", "),
    reinforcement_asymmetry_summary: phase.reinforcement_asymmetry,
  };
}

function buildTrajectoryShapingLineageV0(): Record<string, unknown> {
  return {
    scenario_id: PRE_BOUNDARY_COLLAPSE_SCENARIO,
    version: "v0",
    initial_option_space: {
      options: ["A", "B", "C", "D"],
      effective_optionality: "full",
    },
    sequence: [
      {
        phase_id: "phase_1_open_framing",
        phase_label: "Phase 1 — Participation / open framing",
        exposure_state: "symmetric",
        reinforcement_state: "none",
        divergence_state: "open",
        participation_state: "informative",
        preservation_state: "open",
        intervention_viability: "high",
        structural_marker: "reachable_space_open",
      },
      {
        phase_id: "phase_2_iterative_shaping",
        phase_label: "Phase 2 — Iterative shaping",
        exposure_state: "asymmetric_emerging",
        reinforcement_state: "a_b_reinforced",
        divergence_state: "contracting",
        participation_state: "participatory",
        preservation_state: "degrading",
        intervention_viability: "medium",
        structural_marker: "first_detectable_asymmetry",
      },
      {
        phase_id: "phase_3_pre_boundary_collapse",
        phase_label: "Phase 3 — Pre-boundary collapse",
        exposure_state: "asymmetric",
        reinforcement_state: "a_b_dominant",
        divergence_state: "collapsed",
        participation_state: "decision_shaping",
        preservation_state: "collapsed",
        intervention_viability: "low",
        structural_marker: "intervention_viability_loss",
      },
      {
        phase_id: "phase_4_bind",
        phase_label: "Phase 4 — Bind",
        exposure_state: "already_narrowed",
        reinforcement_state: "trajectory_committed",
        divergence_state: "effectively_closed",
        participation_state: "decision_shaping",
        preservation_state: "collapsed",
        intervention_viability: "low",
        bind_outcome: "FORMALLY_VALID_STRUCTURALLY_COLLAPSED",
        structural_marker: "bind_over_narrowed_space",
      },
    ],
    transition_points: {
      first_detectable_asymmetry_phase: "phase_2_iterative_shaping",
      divergence_contraction_phase: "phase_2_iterative_shaping",
      participation_shift_phase: "phase_3_pre_boundary_collapse",
      preservation_degradation_phase: "phase_2_iterative_shaping",
      intervention_viability_loss_phase: "phase_3_pre_boundary_collapse",
      bind_evaluation_phase: "phase_4_bind",
    },
    evidence_requirements: [
      "option_exposure_trace",
      "reinforcement_asymmetry_trace",
      "divergence_contraction_trace",
      "participation_shift_marker",
      "preservation_degradation_marker",
      "intervention_threshold_marker",
      "bind_evaluation_snapshot",
    ],
    summary: {
      concise:
        "Decision lineage records what was bound; trajectory shaping lineage records how reachable alternatives became structurally unavailable before bind.",
      operator:
        "Formal admissibility can still hold at bind while effective intervention capacity has already been lost upstream.",
    },
  };
}

async function resolveDemoScenarioPayload(request: Request): Promise<Record<string, unknown> | null> {
  const demoScenario = resolveDemoScenario(request);
  if (demoScenario === AML_KYC_REVIEWER_WALKTHROUGH_SCENARIO) {
    return buildAmlKycReviewerWalkthroughPayload();
  }

  if (demoScenario !== PRE_BOUNDARY_COLLAPSE_SCENARIO) {
    return null;
  }

  const phases = await Promise.all(
    PRE_BOUNDARY_COLLAPSE_PHASE_FIXTURE_FILES.map(async (filename) => {
      const raw = await readFile(resolveFixturePath(filename), "utf-8");
      return JSON.parse(raw) as Record<string, unknown>;
    }),
  );

  const phaseSnapshots = phases.map(mapPreBoundaryCollapsePhaseToSnapshot);
  const finalPhaseSnapshot = phaseSnapshots[phaseSnapshots.length - 1];

  return {
    governance_layer_snapshot: {
      demo_scenario: PRE_BOUNDARY_COLLAPSE_SCENARIO,
      participation_state: finalPhaseSnapshot.participation_state,
      preservation_state: finalPhaseSnapshot.preservation_state,
      intervention_viability: finalPhaseSnapshot.intervention_viability,
      bind_outcome: finalPhaseSnapshot.bind_outcome,
      concise_rationale: finalPhaseSnapshot.concise_rationale,
      phase_snapshots: phaseSnapshots,
      trajectory_shaping_lineage: buildTrajectoryShapingLineageV0(),
    },
  };
}

export async function GET(request: Request): Promise<Response> {
  if (areE2EScenariosEnabled()) {
    const e2ePayload = resolveE2EScenarioPayload(request);
    if (e2ePayload) {
      return NextResponse.json(e2ePayload, { status: 200 });
    }
  }

  const demoScenarioPayload = await resolveDemoScenarioPayload(request);
  if (demoScenarioPayload) {
    return NextResponse.json(demoScenarioPayload, { status: 200 });
  }

  const apiBaseUrl = resolveApiBaseUrl();
  if (!apiBaseUrl) {
    return NextResponse.json({ error: "governance_feed_unavailable" }, { status: 503 });
  }

  const apiKey = resolveApiKey();
  if (!apiKey) {
    return NextResponse.json({ error: "governance_feed_unavailable" }, { status: 503 });
  }

  try {
    const upstreamResponse = await fetch(`${apiBaseUrl.replace(/\/$/, "")}${GOVERNANCE_LIVE_SNAPSHOT_PATH}`, {
      method: "GET",
      headers: {
        "X-API-Key": apiKey,
      },
      cache: "no-store",
    });

    if (!upstreamResponse.ok) {
      return NextResponse.json({ error: "governance_feed_unavailable" }, { status: upstreamResponse.status });
    }

    const payload = normalizeGovernanceReportPayload((await upstreamResponse.json()) as unknown);
    if (!payload) {
      return NextResponse.json({ error: "invalid_governance_feed_payload" }, { status: 502 });
    }

    return NextResponse.json(payload, { status: 200 });
  } catch {
    return NextResponse.json({ error: "governance_feed_unavailable" }, { status: 503 });
  }
}
