import { readFile } from "node:fs/promises";
import path from "node:path";

import { NextResponse } from "next/server";

import {
  type AbcdMinimalValidationCase,
  type ActorRecognitionGap,
  type DynamicConditionsValidationCase,
  type GovernanceAttackSurfaceRegistry,
  type GovernanceSafeguardCoverageMatrix,
  type InterventionActionabilityMap,
  type IrreversibilityHorizon,
  type TrajectoryShapingLineage,
} from "../../../../../../components/dashboard-types";
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

function buildAbcdMinimalValidationCase(): AbcdMinimalValidationCase {
  return {
    case_id: "abcd_minimal_trajectory_validation",
    version: "v0",
    purpose:
      "Validate whether preservation degradation, intervention viability loss, and formal bind admissibility separate under minimal A/B/C/D conditions.",
    options: ["A", "B", "C", "D"],
    phases: [
      {
        phase_id: "phase_1_symmetric_exposure",
        phase_label: "Phase 1 — Symmetric exposure",
        exposure_state: "symmetric",
        reinforcement_state: "none",
        divergence_state: "open",
        preservation_state: "open",
        intervention_viability: "high",
        bind_admissibility: "not_evaluated",
        structural_marker: "full_reachable_space",
      },
      {
        phase_id: "phase_2_reinforcement_asymmetry",
        phase_label: "Phase 2 — Gradual reinforcement asymmetry",
        exposure_state: "asymmetric_emerging",
        reinforcement_state: "a_b_reinforced",
        divergence_state: "contracting",
        preservation_state: "degrading",
        intervention_viability: "medium",
        bind_admissibility: "not_evaluated",
        structural_marker: "first_detectable_asymmetry",
      },
      {
        phase_id: "phase_3_divergence_contraction",
        phase_label: "Phase 3 — Measurable divergence contraction",
        exposure_state: "asymmetric",
        reinforcement_state: "a_b_dominant",
        divergence_state: "contracted",
        preservation_state: "degraded",
        intervention_viability: "low",
        bind_admissibility: "not_evaluated",
        structural_marker: "measurable_divergence_contraction",
      },
      {
        phase_id: "phase_4_intervention_viability_loss",
        phase_label: "Phase 4 — First detectable loss of intervention viability",
        exposure_state: "asymmetric",
        reinforcement_state: "trajectory_narrowed",
        divergence_state: "effectively_closed",
        preservation_state: "collapsed",
        intervention_viability: "lost",
        bind_admissibility: "not_evaluated",
        structural_marker: "intervention_viability_loss",
      },
      {
        phase_id: "phase_5_bind_over_narrowed_space",
        phase_label: "Phase 5 — Bind over narrowed space",
        exposure_state: "already_narrowed",
        reinforcement_state: "trajectory_committed",
        divergence_state: "closed",
        preservation_state: "collapsed",
        intervention_viability: "lost",
        bind_admissibility: "formally_valid",
        bind_outcome: "FORMALLY_VALID_OVER_STRUCTURALLY_NARROWED_SPACE",
        structural_marker: "formal_admissibility_after_intervention_loss",
      },
    ],
    separation_points: {
      first_detectable_asymmetry_phase: "phase_2_reinforcement_asymmetry",
      divergence_contraction_phase: "phase_3_divergence_contraction",
      preservation_degradation_phase: "phase_2_reinforcement_asymmetry",
      intervention_viability_loss_phase: "phase_4_intervention_viability_loss",
      formal_admissibility_phase: "phase_5_bind_over_narrowed_space",
    },
    validation_question:
      "Do preservation degradation, intervention viability loss, and formal bind admissibility separate even under minimal A/B/C/D conditions?",
    summary: {
      concise:
        "The A/B/C/D minimal case tests whether formal bind admissibility can remain valid after effective intervention viability has already been structurally lost.",
      operator:
        "The system should show when intervention stopped being realistically preservable before bind evaluated the narrowed space.",
    },
  };
}

function buildActorRecognitionGapV0(): ActorRecognitionGap {
  return {
    version: "v0",
    purpose:
      "Mark the representative gap between structurally visible degradation and actor recognition of intervention capacity loss.",
    base_case: "irreversibility_horizon_v0",
    recognition_model: "deterministic_representative_marker",
    markers: {
      actual_degradation_visible_phase: "phase_2_reinforcement_exposure_asymmetry",
      actor_still_perceives_governable_phase: "phase_2_reinforcement_exposure_asymmetry",
      visibility_degradation_phase: "phase_3_time_pressure_compression",
      recognition_gap_phase: "phase_3_time_pressure_compression",
      recognition_alignment_phase: "phase_4_adaptive_narrowing",
      bind_after_recognition_gap_phase: "phase_5_bind_over_dynamically_narrowed_space",
    },
    phase_interpretation: {
      actual_degradation_visible: {
        phase_id: "phase_2_reinforcement_exposure_asymmetry",
        meaning: "Structural degradation first becomes visible through reinforcement and exposure asymmetry.",
        actor_visibility_status: "may_appear_governable",
      },
      actor_still_perceives_governable: {
        phase_id: "phase_2_reinforcement_exposure_asymmetry",
        meaning: "The system may still appear formally open and procedurally coherent to the actor.",
        actor_visibility_status: "governable_apparent",
      },
      visibility_degradation: {
        phase_id: "phase_3_time_pressure_compression",
        meaning:
          "The visibility of remaining intervention capacity begins degrading as time pressure compresses the intervention window.",
        actor_visibility_status: "intervention_visibility_degrading",
      },
      recognition_gap: {
        phase_id: "phase_3_time_pressure_compression",
        meaning:
          "A representative gap emerges between structural degradation and actor recognition of reduced intervention capacity.",
        actor_visibility_status: "recognition_lag",
      },
      recognition_alignment: {
        phase_id: "phase_4_adaptive_narrowing",
        meaning:
          "The actor may begin recognizing the narrowed trajectory as adaptive behavior stabilizes it, but meaningful divergence is already operationally hard to recover.",
        actor_visibility_status: "late_alignment",
      },
      bind_after_recognition_gap: {
        phase_id: "phase_5_bind_over_dynamically_narrowed_space",
        meaning: "Bind evaluates a formally admissible trajectory after the recognition gap has already occurred upstream.",
        actor_visibility_status: "post_gap_bind",
      },
    },
    validation_question:
      "When did the visibility of remaining intervention capacity begin degrading before actors fully recognized the loss?",
    summary: {
      concise:
        "Actor Recognition Gap v0 marks the representative gap between structurally visible governability degradation and actor recognition of reduced intervention capacity.",
      operator: "The system should show when intervention capacity visibility began degrading before the actor fully recognized the loss.",
    },
  };
}

function buildIrreversibilityHorizonV0(): IrreversibilityHorizon {
  return {
    version: "v0",
    purpose:
      "Mark when structurally meaningful governability degradation becomes visible before operational irreversibility stabilizes.",
    base_case: "dynamic_conditions_trajectory_validation",
    horizon_model: "deterministic_representative_marker",
    markers: {
      first_structural_degradation_signal_phase: "phase_2_reinforcement_exposure_asymmetry",
      early_warning_phase: "phase_3_time_pressure_compression",
      last_meaningful_intervention_phase: "phase_3_time_pressure_compression",
      irreversibility_horizon_phase: "phase_4_adaptive_narrowing",
      bind_after_horizon_phase: "phase_5_bind_over_dynamically_narrowed_space",
    },
    phase_interpretation: {
      first_structural_degradation_signal: {
        phase_id: "phase_2_reinforcement_exposure_asymmetry",
        meaning: "The first detectable dynamic asymmetry appears while intervention remains realistic.",
        intervention_status: "available",
      },
      early_warning: {
        phase_id: "phase_3_time_pressure_compression",
        meaning:
          "The intervention window begins compressing under time pressure while meaningful intervention remains possible.",
        intervention_status: "still_meaningful_but_compressing",
      },
      last_meaningful_intervention: {
        phase_id: "phase_3_time_pressure_compression",
        meaning:
          "The last representative phase where intervention remains meaningfully available before adaptive stabilization.",
        intervention_status: "last_meaningful",
      },
      irreversibility_horizon: {
        phase_id: "phase_4_adaptive_narrowing",
        meaning: "Adaptive behavior stabilizes the narrowed trajectory and recovery becomes operationally hard.",
        intervention_status: "operationally_hard_to_reverse",
      },
      bind_after_horizon: {
        phase_id: "phase_5_bind_over_dynamically_narrowed_space",
        meaning:
          "Bind evaluates a formally admissible trajectory after the irreversibility horizon has already been crossed.",
        intervention_status: "post_horizon",
      },
    },
    validation_question:
      "How early can structurally meaningful degradation become visible before operational irreversibility stabilizes?",
    summary: {
      concise:
        "Irreversibility Horizon v0 marks the representative point where intervention remains formally possible but becomes operationally hard to recover before bind.",
      operator:
        "The system should show the last meaningful intervention phase before adaptive narrowing stabilizes the trajectory.",
    },
    actor_recognition_gap: buildActorRecognitionGapV0(),
  };
}

function buildDynamicConditionsValidationCase(): DynamicConditionsValidationCase {
  return {
    case_id: "dynamic_conditions_trajectory_validation",
    version: "v0",
    purpose:
      "Validate whether preservation degradation, intervention viability loss, and formal bind admissibility remain structurally separable when reinforcement, exposure asymmetry, time pressure, and adaptive behavior interact.",
    base_case: "abcd_minimal_trajectory_validation",
    options: ["A", "B", "C", "D"],
    dynamic_factors: [
      "reinforcement",
      "exposure_asymmetry",
      "time_pressure",
      "adaptive_system_behavior",
    ],
    phases: [
      {
        phase_id: "phase_1_balanced_option_space",
        phase_label: "Phase 1 — Balanced option space",
        exposure_state: "symmetric",
        reinforcement_state: "none",
        time_pressure_state: "none",
        adaptive_behavior_state: "inactive",
        divergence_state: "open",
        preservation_state: "open",
        intervention_viability: "high",
        bind_admissibility: "not_evaluated",
        structural_marker: "full_reachable_space",
      },
      {
        phase_id: "phase_2_reinforcement_exposure_asymmetry",
        phase_label: "Phase 2 — Reinforcement and exposure asymmetry",
        exposure_state: "asymmetric_emerging",
        reinforcement_state: "a_b_reinforced",
        time_pressure_state: "none",
        adaptive_behavior_state: "inactive",
        divergence_state: "contracting",
        preservation_state: "degrading",
        intervention_viability: "medium",
        bind_admissibility: "not_evaluated",
        structural_marker: "first_dynamic_asymmetry",
      },
      {
        phase_id: "phase_3_time_pressure_compression",
        phase_label: "Phase 3 — Time pressure compresses intervention window",
        exposure_state: "asymmetric",
        reinforcement_state: "a_b_dominant",
        time_pressure_state: "active",
        adaptive_behavior_state: "weak",
        divergence_state: "contracted",
        preservation_state: "degraded",
        intervention_viability: "low",
        bind_admissibility: "not_evaluated",
        structural_marker: "intervention_window_compressed",
      },
      {
        phase_id: "phase_4_adaptive_narrowing",
        phase_label: "Phase 4 — Adaptive behavior stabilizes narrowed trajectory",
        exposure_state: "asymmetric",
        reinforcement_state: "trajectory_narrowed",
        time_pressure_state: "active",
        adaptive_behavior_state: "active",
        divergence_state: "effectively_closed",
        preservation_state: "collapsed",
        intervention_viability: "lost",
        bind_admissibility: "not_evaluated",
        structural_marker: "adaptive_structural_narrowing",
      },
      {
        phase_id: "phase_5_bind_over_dynamically_narrowed_space",
        phase_label: "Phase 5 — Bind over dynamically narrowed space",
        exposure_state: "already_narrowed",
        reinforcement_state: "trajectory_committed",
        time_pressure_state: "resolved_at_bind",
        adaptive_behavior_state: "committed",
        divergence_state: "closed",
        preservation_state: "collapsed",
        intervention_viability: "lost",
        bind_admissibility: "formally_valid",
        bind_outcome: "FORMALLY_VALID_OVER_DYNAMICALLY_NARROWED_SPACE",
        structural_marker: "formal_admissibility_after_dynamic_governability_loss",
      },
    ],
    separation_points: {
      first_dynamic_asymmetry_phase: "phase_2_reinforcement_exposure_asymmetry",
      intervention_window_compression_phase: "phase_3_time_pressure_compression",
      adaptive_narrowing_phase: "phase_4_adaptive_narrowing",
      intervention_viability_loss_phase: "phase_4_adaptive_narrowing",
      formal_admissibility_phase: "phase_5_bind_over_dynamically_narrowed_space",
    },
    validation_question:
      "Do preservation degradation, intervention viability loss, and formal bind admissibility remain structurally separable when reinforcement, exposure asymmetry, time pressure, and adaptive behavior interact?",
    summary: {
      concise:
        "The dynamic conditions case tests whether governability degradation remains observable when multiple trajectory-shaping forces interact before bind.",
      operator:
        "The system should show whether formal admissibility can remain intact while meaningful intervention capacity has already degraded under dynamic pressure.",
    },
    irreversibility_horizon: buildIrreversibilityHorizonV0(),
  };
}


function buildGovernanceSafeguardCoverageMatrixV0(): GovernanceSafeguardCoverageMatrix {
  return {
    version: "v0",
    purpose:
      "Map representative governance attack surfaces to structural safeguards and the evidence required to make coverage visible.",
    coverage_model: "deterministic_representative_visibility_matrix",
    scope: {
      included: [
        "failure_class_to_safeguard_mapping",
        "visibility_evidence_requirements",
        "representative_coverage_state",
        "coverage_limitations",
      ],
      excluded: [
        "complete_prevention_claim",
        "production_security_guarantee",
        "automatic_attack_detection",
        "scoring_model",
        "certification_claim",
        "formal_verification_claim",
      ],
    },
    rows: [
      {
        failure_class_id: "self_authorization",
        primary_safeguard_id: "separation_of_decision_and_governance_authority",
        supporting_safeguard_ids: ["append_only_governance_log"],
        evidence_requirement: "independent_governance_authority_marker",
        visibility_question:
          "Can reviewers see whether the decision-producing component was structurally separate from the governance-validating component?",
        coverage_state: "representative_visibility_only",
        limitation: "does_not_claim_complete_prevention_or_runtime_enforcement",
      },
      {
        failure_class_id: "evidence_chain_manipulation",
        primary_safeguard_id: "immutable_evidence_chain",
        supporting_safeguard_ids: ["append_only_governance_log"],
        evidence_requirement: "ordered_append_only_evidence_chain",
        visibility_question: "Can reviewers replay the evidence sequence without relying on mutable post-hoc state?",
        coverage_state: "representative_visibility_only",
        limitation: "does_not_claim_tamper_proof_storage_or_formal_verification",
      },
      {
        failure_class_id: "approval_receipt_spoofing",
        primary_safeguard_id: "approval_receipt_provenance",
        supporting_safeguard_ids: ["separation_of_decision_and_governance_authority"],
        evidence_requirement: "actor_source_timestamp_scope_validity_context",
        visibility_question: "Can reviewers distinguish valid approval provenance from spoofed or out-of-scope approval?",
        coverage_state: "representative_visibility_only",
        limitation: "does_not_claim_identity_proof_or_production_authentication",
      },
      {
        failure_class_id: "policy_snapshot_drift",
        primary_safeguard_id: "policy_snapshot_hashing",
        supporting_safeguard_ids: ["immutable_evidence_chain"],
        evidence_requirement: "bind_time_policy_hash_and_version",
        visibility_question:
          "Can reviewers reconstruct the policy state used at bind time rather than a later policy version?",
        coverage_state: "representative_visibility_only",
        limitation: "does_not_claim_policy_correctness_or_regulatory_certification",
      },
      {
        failure_class_id: "escalation_suppression",
        primary_safeguard_id: "replayable_escalation_trace",
        supporting_safeguard_ids: ["append_only_governance_log"],
        evidence_requirement: "warning_pause_review_escalation_sequence",
        visibility_question: "Can reviewers see whether warning, pause, review, or escalation opportunities were preserved?",
        coverage_state: "representative_visibility_only",
        limitation: "does_not_claim_automatic_escalation_or_blocking",
      },
      {
        failure_class_id: "replay_trace_tampering",
        primary_safeguard_id: "append_only_governance_log",
        supporting_safeguard_ids: ["immutable_evidence_chain", "replayable_escalation_trace"],
        evidence_requirement: "append_only_replayable_governance_sequence",
        visibility_question:
          "Can reviewers reconstruct the governance sequence without hidden mutation or ordering ambiguity?",
        coverage_state: "representative_visibility_only",
        limitation: "does_not_claim_tamper_proof_infrastructure",
      },
      {
        failure_class_id: "recognition_gap_masking",
        primary_safeguard_id: "recognition_gap_visibility_marker",
        supporting_safeguard_ids: ["replayable_escalation_trace"],
        evidence_requirement: "actor_recognition_gap_marker_sequence",
        visibility_question:
          "Can reviewers compare perceived governability with structurally visible degradation over time?",
        coverage_state: "representative_visibility_only",
        limitation: "does_not_infer_actor_psychology_or_intent",
      },
    ],
    validation_question:
      "Which structural safeguard covers which governance attack surface, and what evidence makes that coverage visible?",
    summary: {
      concise:
        "Governance Safeguard Coverage Matrix v0 maps each representative governance attack surface to structural safeguards and the evidence required to inspect coverage.",
      operator:
        "The system should show which safeguard makes each failure class visible without claiming complete prevention, certification, or production security.",
    },
  };
}

function buildGovernanceAttackSurfaceRegistryV0(): GovernanceAttackSurfaceRegistry {
  return {
    version: "v0",
    purpose:
      "Identify representative failure classes where the governance process itself can become an attack surface and map them to structural safeguards.",
    registry_model: "deterministic_representative_visibility_registry",
    scope: {
      included: [
        "governance_self_authorization",
        "evidence_integrity",
        "approval_provenance",
        "policy_snapshot_replayability",
        "escalation_trace_visibility",
        "actor_recognition_gap_visibility",
      ],
      excluded: [
        "complete_security_proof",
        "production_threat_model",
        "automatic_attack_detection",
        "certification_claim",
        "formal_verification_claim",
      ],
    },
    failure_classes: [
      {
        id: "self_authorization",
        label: "Self-authorization",
        description:
          "The governance process or governed component appears to authorize its own action without independent governance authority.",
        representative_risk: "A decision-producing component may make its own action appear admissible.",
        safeguard_refs: [
          "separation_of_decision_and_governance_authority",
          "append_only_governance_log",
        ],
      },
      {
        id: "evidence_chain_manipulation",
        label: "Evidence-chain manipulation",
        description: "Evidence used to justify a decision is altered, reordered, omitted, or replaced after the fact.",
        representative_risk: "The decision path may look safer or more justified than it was at bind time.",
        safeguard_refs: ["immutable_evidence_chain", "append_only_governance_log"],
      },
      {
        id: "approval_receipt_spoofing",
        label: "Approval receipt spoofing",
        description: "A human approval receipt or authorization proof appears valid without reliable provenance.",
        representative_risk: "A bind path may appear human-approved even when the approval scope or source is invalid.",
        safeguard_refs: [
          "approval_receipt_provenance",
          "separation_of_decision_and_governance_authority",
        ],
      },
      {
        id: "policy_snapshot_drift",
        label: "Policy snapshot drift",
        description:
          "The policy used at decision time cannot be reproduced because later policy state differs from the bind-time snapshot.",
        representative_risk: "A later review may evaluate the decision against the wrong policy version.",
        safeguard_refs: ["policy_snapshot_hashing", "immutable_evidence_chain"],
      },
      {
        id: "escalation_suppression",
        label: "Escalation suppression",
        description: "A condition requiring warning, pause, review, or escalation is not preserved in the governance trace.",
        representative_risk:
          "The governance process may appear orderly while suppressing evidence that intervention was needed.",
        safeguard_refs: ["replayable_escalation_trace", "append_only_governance_log"],
      },
      {
        id: "replay_trace_tampering",
        label: "Replay trace tampering",
        description:
          "Replayable audit traces are missing, reordered, overwritten, or no longer reproduce the observed governance sequence.",
        representative_risk: "Reviewers cannot reliably reconstruct the sequence that led to bind.",
        safeguard_refs: [
          "immutable_evidence_chain",
          "replayable_escalation_trace",
          "append_only_governance_log",
        ],
      },
      {
        id: "recognition_gap_masking",
        label: "Recognition gap masking",
        description:
          "The visibility gap between structural degradation and actor recognition is not preserved as governance evidence.",
        representative_risk:
          "The system may look governable even while meaningful intervention capacity was already becoming nonviable upstream.",
        safeguard_refs: [
          "recognition_gap_visibility_marker",
          "replayable_escalation_trace",
        ],
      },
    ],
    structural_safeguards: [
      {
        id: "separation_of_decision_and_governance_authority",
        label: "Separation of decision and governance authority",
        description:
          "Decision-producing components should not be able to independently validate their own authority or admissibility.",
        visibility_role:
          "Shows whether governance authority is structurally independent from the governed decision path.",
      },
      {
        id: "immutable_evidence_chain",
        label: "Immutable evidence chain",
        description: "Evidence should be preserved as an ordered, append-only chain that cannot be silently rewritten.",
        visibility_role: "Shows whether bind-time evidence can be replayed without relying on mutable post-hoc state.",
      },
      {
        id: "policy_snapshot_hashing",
        label: "Policy snapshot hashing",
        description: "Policy state used at decision or bind time should be versioned and hashable.",
        visibility_role: "Shows whether the exact policy context can be reconstructed later.",
      },
      {
        id: "approval_receipt_provenance",
        label: "Approval receipt provenance",
        description: "Approval receipts should preserve actor, source, timestamp, scope, and validity context.",
        visibility_role:
          "Shows whether human approval evidence can be distinguished from spoofed or out-of-scope approval.",
      },
      {
        id: "replayable_escalation_trace",
        label: "Replayable escalation trace",
        description: "Warnings, pauses, reviews, and escalations should be preserved in replayable order.",
        visibility_role: "Shows whether intervention opportunities and escalation decisions remain inspectable.",
      },
      {
        id: "append_only_governance_log",
        label: "Append-only governance log",
        description: "Governance validation, exceptions, and marker outputs should be appended rather than overwritten.",
        visibility_role: "Shows whether governance outcomes can be audited without hidden mutation.",
      },
      {
        id: "recognition_gap_visibility_marker",
        label: "Recognition gap visibility marker",
        description: "Actor Recognition Gap v0 markers should remain visible as part of the governance evidence record.",
        visibility_role:
          "Shows whether perceived governability and structural degradation can be compared over time.",
      },
    ],
    safeguard_coverage_matrix: buildGovernanceSafeguardCoverageMatrixV0(),
    validation_question: "What structural safeguards prevent the governance process itself from becoming the attack surface?",
    summary: {
      concise:
        "Governance Attack Surface Registry v0 identifies representative failure classes where governance evidence, approval, policy, escalation, or replay traces could be manipulated or made self-authorizing.",
      operator:
        "The system should show which structural safeguard makes each governance attack surface visible without claiming complete security or certification.",
    },
  };
}


function buildInterventionActionabilityMapV0(): InterventionActionabilityMap {
  return {
    version: "v0",
    purpose:
      "Map visible governance markers to representative intervention categories without claiming automatic enforcement.",
    actionability_model: "deterministic_representative_intervention_guidance",
    scope: {
      included: [
        "marker_to_actionability_mapping",
        "representative_intervention_categories",
        "evidence_preservation_guidance",
        "action_limitations",
      ],
      excluded: [
        "automatic_enforcement",
        "automatic_blocking",
        "automatic_escalation",
        "scoring_model",
        "production_decisioning",
        "certification_claim",
      ],
    },
    intervention_categories: [
      { id: "observe", label: "Observe", description: "Record the visible marker without changing the bind path." },
      { id: "annotate", label: "Annotate", description: "Add explanatory context to the governance trace." },
      { id: "warn", label: "Warn", description: "Surface a warning to operators or reviewers." },
      {
        id: "preserve_evidence",
        label: "Preserve evidence",
        description: "Ensure the relevant marker, evidence chain, and replay trace remain inspectable.",
      },
      { id: "reframe", label: "Reframe", description: "Reopen or rebalance option framing before bind." },
      { id: "pause", label: "Pause", description: "Hold progression before bind while review remains meaningful." },
      {
        id: "escalate",
        label: "Escalate",
        description: "Route the marker to human or higher-authority governance review.",
      },
      {
        id: "require_explicit_approval",
        label: "Require explicit approval",
        description: "Require scope-bound approval before continuing toward bind.",
      },
      {
        id: "freeze_bind_path",
        label: "Freeze bind path",
        description: "Preserve the current bind path and prevent silent mutation while reviewing evidence.",
      },
      {
        id: "post_horizon_review",
        label: "Post-horizon review",
        description: "Flag a bind or decision for review after the irreversibility horizon or recognition gap.",
      },
    ],
    mappings: [
      {
        marker_id: "first_structural_degradation_signal",
        source_layer: "irreversibility_horizon_v0",
        representative_phase: "phase_2_reinforcement_exposure_asymmetry",
        recommended_action_ids: ["annotate", "preserve_evidence", "warn"],
        evidence_to_preserve: ["first_structural_degradation_signal_phase", "dynamic_asymmetry_marker"],
        limitation: "does_not_claim_automatic_intervention",
      },
      {
        marker_id: "early_warning",
        source_layer: "irreversibility_horizon_v0",
        representative_phase: "phase_3_time_pressure_compression",
        recommended_action_ids: ["warn", "pause", "reframe", "preserve_evidence"],
        evidence_to_preserve: ["early_warning_phase", "intervention_window_compression_marker"],
        limitation: "does_not_claim_automatic_pause_or_blocking",
      },
      {
        marker_id: "last_meaningful_intervention",
        source_layer: "irreversibility_horizon_v0",
        representative_phase: "phase_3_time_pressure_compression",
        recommended_action_ids: ["pause", "escalate", "require_explicit_approval"],
        evidence_to_preserve: ["last_meaningful_intervention_phase", "intervention_viability_state"],
        limitation: "does_not_claim_intervention_success",
      },
      {
        marker_id: "irreversibility_horizon",
        source_layer: "irreversibility_horizon_v0",
        representative_phase: "phase_4_adaptive_narrowing",
        recommended_action_ids: ["escalate", "require_explicit_approval", "post_horizon_review", "preserve_evidence"],
        evidence_to_preserve: ["irreversibility_horizon_phase", "adaptive_narrowing_marker"],
        limitation: "does_not_claim_reversibility_after_horizon",
      },
      {
        marker_id: "actor_recognition_gap",
        source_layer: "actor_recognition_gap_v0",
        representative_phase: "phase_3_time_pressure_compression",
        recommended_action_ids: ["warn", "annotate", "escalate", "preserve_evidence"],
        evidence_to_preserve: ["recognition_gap_phase", "visibility_degradation_phase"],
        limitation: "does_not_infer_actor_psychology_or_intent",
      },
      {
        marker_id: "bind_after_recognition_gap",
        source_layer: "actor_recognition_gap_v0",
        representative_phase: "phase_5_bind_over_dynamically_narrowed_space",
        recommended_action_ids: ["post_horizon_review", "preserve_evidence", "require_explicit_approval"],
        evidence_to_preserve: ["bind_after_recognition_gap_phase", "post_gap_bind_marker"],
        limitation: "does_not_claim_bind_invalidity",
      },
      {
        marker_id: "self_authorization",
        source_layer: "governance_attack_surface_registry_v0",
        representative_failure_class: "self_authorization",
        recommended_action_ids: ["escalate", "freeze_bind_path", "require_explicit_approval", "preserve_evidence"],
        evidence_to_preserve: ["independent_governance_authority_marker", "append_only_governance_log"],
        limitation: "does_not_claim_complete_prevention_or_runtime_enforcement",
      },
      {
        marker_id: "evidence_chain_manipulation",
        source_layer: "governance_attack_surface_registry_v0",
        representative_failure_class: "evidence_chain_manipulation",
        recommended_action_ids: ["freeze_bind_path", "preserve_evidence", "escalate"],
        evidence_to_preserve: ["ordered_append_only_evidence_chain", "append_only_governance_log"],
        limitation: "does_not_claim_tamper_proof_storage_or_formal_verification",
      },
      {
        marker_id: "approval_receipt_spoofing",
        source_layer: "governance_attack_surface_registry_v0",
        representative_failure_class: "approval_receipt_spoofing",
        recommended_action_ids: ["require_explicit_approval", "escalate", "preserve_evidence"],
        evidence_to_preserve: ["actor_source_timestamp_scope_validity_context", "approval_receipt_provenance"],
        limitation: "does_not_claim_identity_proof_or_production_authentication",
      },
      {
        marker_id: "escalation_suppression",
        source_layer: "governance_attack_surface_registry_v0",
        representative_failure_class: "escalation_suppression",
        recommended_action_ids: ["escalate", "preserve_evidence", "post_horizon_review"],
        evidence_to_preserve: ["warning_pause_review_escalation_sequence", "replayable_escalation_trace"],
        limitation: "does_not_claim_automatic_escalation_or_blocking",
      },
    ],
    validation_question:
      "When a governance marker becomes visible, what representative intervention category becomes actionable?",
    summary: {
      concise:
        "Intervention Actionability Map v0 connects visible governance markers to representative intervention categories and evidence preservation guidance.",
      operator:
        "The system should show what action category becomes representative when a marker is visible, without claiming automatic enforcement.",
    },
  };
}

function buildTrajectoryShapingLineageV0(): TrajectoryShapingLineage {
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
    abcd_minimal_validation_case: buildAbcdMinimalValidationCase(),
    dynamic_conditions_validation_case: buildDynamicConditionsValidationCase(),
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
      governance_attack_surface_registry: buildGovernanceAttackSurfaceRegistryV0(),
      intervention_actionability_map: buildInterventionActionabilityMapV0(),
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
