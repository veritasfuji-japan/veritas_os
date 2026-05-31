import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PRE_BIND_GOVERNANCE_VOCABULARY_LABELS } from "./dashboard-types";
import { I18nProvider } from "./i18n-provider";
import { MissionPage } from "./mission-page";

describe("MissionPage", () => {
  it("renders enhanced critical rail and global health summary", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("Global Health Summary")).toBeInTheDocument();
    expect(screen.getByText("Current band:", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Critical Rail")).toBeInTheDocument();
    expect(screen.getByText("FUJI reject")).toBeInTheDocument();
    expect(screen.getByText("Open incidents: 4")).toBeInTheDocument();
    expect(screen.getByText("Mission Control provenance: mixed")).toBeInTheDocument();
  });

  it("renders action-oriented priority cards", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
        />
      </I18nProvider>,
    );

    expect(screen.getAllByText(/Why now/)).toHaveLength(3);
    expect(screen.getAllByText(/Impact window/)).toHaveLength(3);
    expect(screen.getByRole("link", { name: "Decision で triage" })).toHaveAttribute("href", "/console");
  });

  it("surfaces trust-chain, governance, and evidence routing context", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("Trust Chain Integrity")).toBeInTheDocument();
    expect(screen.getByText("Verification:", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Governance approval risk")).toBeInTheDocument();
    expect(screen.getByText("Risk → Decision → Evidence → Report")).toBeInTheDocument();
    expect(screen.getByText("/health security posture (mandatory)")).toBeInTheDocument();
    expect(screen.getByText("Encryption algorithm:", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Authentication mode:", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Direct FUJI API:", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("degraded:", { exact: false })).toBeInTheDocument();
  });

  it("renders pre-bind governance vocabulary and bind separation", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            participation_state: "decision_shaping",
            preservation_state: "degrading",
            intervention_viability: "minimal",
            concise_rationale: "early warning signal indicates reduced intervention headroom.",
            bind_outcome: "ESCALATED",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText(PRE_BIND_GOVERNANCE_VOCABULARY_LABELS.heading)).toBeInTheDocument();
    expect(screen.getByText(/participation_state:/)).toBeInTheDocument();
    expect(screen.getByText("decision_shaping")).toBeInTheDocument();
    expect(screen.getByText(/preservation_state:/)).toBeInTheDocument();
    expect(screen.getByText("degrading")).toBeInTheDocument();
    expect(screen.getByText(/intervention_viability:/)).toBeInTheDocument();
    expect(screen.getByText("minimal")).toBeInTheDocument();
    expect(screen.getByText(/bind_outcome:/)).toBeInTheDocument();
    expect(screen.getByText("ESCALATED")).toBeInTheDocument();
    expect(screen.getByText(/concise_rationale:/)).toBeInTheDocument();
  });

  it("uses shared pre-bind governance vocabulary labels", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            participation_state: "participatory",
            preservation_state: "open",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText(`${PRE_BIND_GOVERNANCE_VOCABULARY_LABELS.participation_state}:`)).toBeInTheDocument();
    expect(screen.getByText(`${PRE_BIND_GOVERNANCE_VOCABULARY_LABELS.preservation_state}:`)).toBeInTheDocument();
  });

  it("omits governance timeline when additive pre-bind fields are absent", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{ bind_outcome: "COMMITTED" }}
        />
      </I18nProvider>,
    );

    expect(screen.queryByText(/Governance layer timeline/)).not.toBeInTheDocument();
    expect(screen.queryByText(/participation_state:/)).not.toBeInTheDocument();
  });

  it("renders governance artifact metadata for operators", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            pre_bind_source: "trustlog_matching_decision",
            pre_bind_detection_summary: { participation_state: "decision_shaping" },
            pre_bind_preservation_summary: { preservation_state: "degrading" },
            bind_reason_code: "AUTHORITY_MISSING",
            bind_failure_reason: "Authority evidence missing",
            target_label: "Governance policy",
            operator_surface: "governance",
            relevant_ui_href: "/governance",
            bind_receipt_id: "br_123",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getAllByText("trustlog_matching_decision").length).toBeGreaterThan(0);
    expect(screen.getAllByText("AUTHORITY_MISSING").length).toBeGreaterThan(0);
    expect(screen.getByText("Authority evidence missing")).toBeInTheDocument();
    expect(screen.getByText("Governance policy")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "/governance" })[0]).toHaveAttribute("href", "/governance");
    expect(screen.getByText("Operator actions")).toBeInTheDocument();
    expect(screen.getByText(/Open target surface:/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "open audit path" })).toBeInTheDocument();
    expect(screen.getByText(/Authority evidence status:/)).toBeInTheDocument();
  });

  it("shows unavailable drilldown without fake links when ids are missing", () => {
    render(
      <I18nProvider>
        <MissionPage title="Command Dashboard" subtitle="Mission overview" chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]} governanceLayerSnapshot={{ pre_bind_source: "none" }} />
      </I18nProvider>,
    );

    expect(screen.getByText(/AML\/KYC evidence drilldown/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "open audit path" })).not.toBeInTheDocument();
    expect(screen.getAllByText("unavailable").length).toBeGreaterThan(0);
    expect(screen.getAllByLabelText("source state: unavailable (missing_payload)").length).toBeGreaterThan(0);
  });

  it("marks static and demo cards with source-state labels", () => {
    render(
      <I18nProvider>
        <MissionPage title="Command Dashboard" subtitle="Mission overview" chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]} />
      </I18nProvider>,
    );

    expect(screen.getAllByText("fixture").length).toBeGreaterThan(3);
    expect(screen.getAllByText("demo").length).toBeGreaterThan(1);
  });

  it("renders pre-boundary collapse demo walkthrough with four phases", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            demo_scenario: "pre_boundary_collapse",
            phase_snapshots: [
              {
                phase_id: "pre_boundary_collapse_phase_1_open",
                phase_label: "Participation / open framing",
                participation_state: "informative",
                preservation_state: "open",
                intervention_viability: "high",
                bind_outcome: "PENDING",
                concise_rationale: "All options are broadly exposed.",
              },
              {
                phase_id: "pre_boundary_collapse_phase_2_iterative_shaping",
                phase_label: "Iterative shaping",
                participation_state: "participatory",
                preservation_state: "degrading",
                intervention_viability: "medium",
                bind_outcome: "PENDING",
                concise_rationale: "Reinforcement narrows practical divergence.",
              },
              {
                phase_id: "pre_boundary_collapse_phase_3_collapse",
                phase_label: "Pre-boundary collapse",
                participation_state: "decision_shaping",
                preservation_state: "collapsed",
                intervention_viability: "minimal",
                bind_outcome: "PENDING",
                concise_rationale: "Effective optionality is nearly exhausted.",
              },
              {
                phase_id: "pre_boundary_collapse_phase_4_bind",
                phase_label: "Bind",
                participation_state: "decision_shaping",
                preservation_state: "collapsed",
                intervention_viability: "minimal",
                bind_outcome: "ALLOWED",
                concise_rationale: "Bind remains formally admissible.",
              },
            ],
            trajectory_shaping_lineage: {
              scenario_id: "pre_boundary_collapse",
              version: "v0",
              initial_option_space: { options: ["A", "B", "C", "D"], effective_optionality: "full" },
              // sequence is intentionally empty: component renders transition_points/summary only
              sequence: [],
              transition_points: {
                first_detectable_asymmetry_phase: "phase_2_iterative_shaping",
                divergence_contraction_phase: "phase_2_iterative_shaping",
                participation_shift_phase: "phase_3_pre_boundary_collapse",
                preservation_degradation_phase: "phase_2_iterative_shaping",
                intervention_viability_loss_phase: "phase_3_pre_boundary_collapse",
                bind_evaluation_phase: "phase_4_bind",
              },
              evidence_requirements: [],
              summary: {
                concise: "Decision lineage records what was bound; trajectory shaping lineage records how reachable alternatives became structurally unavailable before bind.",
                operator: "Formal admissibility can still hold at bind while effective intervention capacity has already been lost upstream.",
              },
              abcd_minimal_validation_case: {
                case_id: "abcd_minimal_trajectory_validation",
                version: "v0",
                purpose: "Validate whether preservation degradation, intervention viability loss, and formal bind admissibility separate under minimal A/B/C/D conditions.",
                options: ["A", "B", "C", "D"],
                phases: [],
                separation_points: {
                  first_detectable_asymmetry_phase: "phase_2_reinforcement_asymmetry",
                  divergence_contraction_phase: "phase_3_divergence_contraction",
                  preservation_degradation_phase: "phase_2_reinforcement_asymmetry",
                  intervention_viability_loss_phase: "phase_4_intervention_viability_loss",
                  formal_admissibility_phase: "phase_5_bind_over_narrowed_space",
                },
                validation_question: "Do preservation degradation, intervention viability loss, and formal bind admissibility separate even under minimal A/B/C/D conditions?",
                summary: {
                  concise: "The A/B/C/D minimal case tests whether formal bind admissibility can remain valid after effective intervention viability has already been structurally lost.",
                  operator: "The system should show when intervention stopped being realistically preservable before bind evaluated the narrowed space.",
                },
              },
              dynamic_conditions_validation_case: {
                case_id: "dynamic_conditions_trajectory_validation",
                version: "v0",
                purpose: "Validate whether preservation degradation, intervention viability loss, and formal bind admissibility remain structurally separable when reinforcement, exposure asymmetry, time pressure, and adaptive behavior interact.",
                base_case: "abcd_minimal_trajectory_validation",
                options: ["A", "B", "C", "D"],
                dynamic_factors: [
                  "reinforcement",
                  "exposure_asymmetry",
                  "time_pressure",
                  "adaptive_system_behavior",
                ],
                phases: [],
                separation_points: {
                  first_dynamic_asymmetry_phase: "phase_2_reinforcement_exposure_asymmetry",
                  intervention_window_compression_phase: "phase_3_time_pressure_compression",
                  adaptive_narrowing_phase: "phase_4_adaptive_narrowing",
                  intervention_viability_loss_phase: "phase_4_adaptive_narrowing",
                  formal_admissibility_phase: "phase_5_bind_over_dynamically_narrowed_space",
                },
                validation_question: "Do preservation degradation, intervention viability loss, and formal bind admissibility remain structurally separable when reinforcement, exposure asymmetry, time pressure, and adaptive behavior interact?",
                summary: {
                  concise: "The dynamic conditions case tests whether governability degradation remains observable when multiple trajectory-shaping forces interact before bind.",
                  operator: "The system should show whether formal admissibility can remain intact while meaningful intervention capacity has already degraded under dynamic pressure.",
                },
                irreversibility_horizon: {
                  version: "v0",
                  purpose: "Mark when structurally meaningful governability degradation becomes visible before operational irreversibility stabilizes.",
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
                      meaning: "The intervention window begins compressing under time pressure while meaningful intervention remains possible.",
                      intervention_status: "still_meaningful_but_compressing",
                    },
                    last_meaningful_intervention: {
                      phase_id: "phase_3_time_pressure_compression",
                      meaning: "The last representative phase where intervention remains meaningfully available before adaptive stabilization.",
                      intervention_status: "last_meaningful",
                    },
                    irreversibility_horizon: {
                      phase_id: "phase_4_adaptive_narrowing",
                      meaning: "Adaptive behavior stabilizes the narrowed trajectory and recovery becomes operationally hard.",
                      intervention_status: "operationally_hard_to_reverse",
                    },
                    bind_after_horizon: {
                      phase_id: "phase_5_bind_over_dynamically_narrowed_space",
                      meaning: "Bind evaluates a formally admissible trajectory after the irreversibility horizon has already been crossed.",
                      intervention_status: "post_horizon",
                    },
                  },
                  validation_question: "How early can structurally meaningful degradation become visible before operational irreversibility stabilizes?",
                  summary: {
                    concise: "Irreversibility Horizon v0 marks the representative point where intervention remains formally possible but becomes operationally hard to recover before bind.",
                    operator: "The system should show the last meaningful intervention phase before adaptive narrowing stabilizes the trajectory.",
                  },
                  actor_recognition_gap: {
                    version: "v0",
                    purpose: "Mark the representative gap between structurally visible degradation and actor recognition of intervention capacity loss.",
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
                        meaning: "The visibility of remaining intervention capacity begins degrading as time pressure compresses the intervention window.",
                        actor_visibility_status: "intervention_visibility_degrading",
                      },
                      recognition_gap: {
                        phase_id: "phase_3_time_pressure_compression",
                        meaning: "A representative gap emerges between structural degradation and actor recognition of reduced intervention capacity.",
                        actor_visibility_status: "recognition_lag",
                      },
                      recognition_alignment: {
                        phase_id: "phase_4_adaptive_narrowing",
                        meaning: "The actor may begin recognizing the narrowed trajectory as adaptive behavior stabilizes it, but meaningful divergence is already operationally hard to recover.",
                        actor_visibility_status: "late_alignment",
                      },
                      bind_after_recognition_gap: {
                        phase_id: "phase_5_bind_over_dynamically_narrowed_space",
                        meaning: "Bind evaluates a formally admissible trajectory after the recognition gap has already occurred upstream.",
                        actor_visibility_status: "post_gap_bind",
                      },
                    },
                    validation_question: "When did the visibility of remaining intervention capacity begin degrading before actors fully recognized the loss?",
                    summary: {
                      concise: "Actor Recognition Gap v0 marks the representative gap between structurally visible governability degradation and actor recognition of reduced intervention capacity.",
                      operator: "The system should show when intervention capacity visibility began degrading before the actor fully recognized the loss.",
                    },
                  },
                },
              },
            },
            governance_attack_surface_registry: {
              version: "v0",
              purpose: "Identify representative governance attack surfaces and map them to structural safeguards.",
              registry_model: "deterministic_representative_visibility_registry",
              scope: {
                included: ["governance_self_authorization"],
                excluded: ["complete_security_proof"],
              },
              failure_classes: [
                {
                  id: "self_authorization",
                  label: "Self-authorization",
                  description: "The governed component appears to authorize itself.",
                  representative_risk: "A component may make its own action appear admissible.",
                  safeguard_refs: ["separation_of_decision_and_governance_authority"],
                },
                {
                  id: "evidence_chain_manipulation",
                  label: "Evidence-chain manipulation",
                  description: "Evidence is altered after the fact.",
                  representative_risk: "The decision path may look safer than it was at bind time.",
                  safeguard_refs: ["immutable_evidence_chain"],
                },
                {
                  id: "approval_receipt_spoofing",
                  label: "Approval receipt spoofing",
                  description: "Approval proof appears valid without provenance.",
                  representative_risk: "A bind path may appear human-approved without valid scope.",
                  safeguard_refs: ["approval_receipt_provenance"],
                },
                {
                  id: "policy_snapshot_drift",
                  label: "Policy snapshot drift",
                  description: "Bind-time policy cannot be reproduced later.",
                  representative_risk: "Review may use the wrong policy version.",
                  safeguard_refs: ["policy_snapshot_hashing"],
                },
                {
                  id: "escalation_suppression",
                  label: "Escalation suppression",
                  description: "Required escalation is not preserved.",
                  representative_risk: "Intervention evidence may be suppressed.",
                  safeguard_refs: ["replayable_escalation_trace"],
                },
                {
                  id: "replay_trace_tampering",
                  label: "Replay trace tampering",
                  description: "Replayable audit traces are missing or reordered.",
                  representative_risk: "Reviewers cannot reconstruct the sequence to bind.",
                  safeguard_refs: ["append_only_governance_log"],
                },
                {
                  id: "recognition_gap_masking",
                  label: "Recognition gap masking",
                  description: "Actor recognition gap visibility is not preserved.",
                  representative_risk: "The system may look governable after intervention capacity degraded.",
                  safeguard_refs: ["recognition_gap_visibility_marker"],
                },
              ],
              structural_safeguards: [
                {
                  id: "separation_of_decision_and_governance_authority",
                  label: "Separation of decision and governance authority",
                  description: "Decision producers should not validate their own authority.",
                  visibility_role: "Shows independent governance authority.",
                },
                {
                  id: "immutable_evidence_chain",
                  label: "Immutable evidence chain",
                  description: "Evidence should remain ordered and append-only.",
                  visibility_role: "Shows bind-time replayability.",
                },
                {
                  id: "policy_snapshot_hashing",
                  label: "Policy snapshot hashing",
                  description: "Policy state should be versioned and hashable.",
                  visibility_role: "Shows exact policy reconstruction.",
                },
                {
                  id: "approval_receipt_provenance",
                  label: "Approval receipt provenance",
                  description: "Approval receipts should preserve actor, source, timestamp, and scope.",
                  visibility_role: "Shows whether approval evidence is in scope.",
                },
                {
                  id: "replayable_escalation_trace",
                  label: "Replayable escalation trace",
                  description: "Escalations should remain replayable.",
                  visibility_role: "Shows intervention opportunities.",
                },
                {
                  id: "append_only_governance_log",
                  label: "Append-only governance log",
                  description: "Governance outcomes should be appended rather than overwritten.",
                  visibility_role: "Shows governance auditability.",
                },
                {
                  id: "recognition_gap_visibility_marker",
                  label: "Recognition gap visibility marker",
                  description: "Actor Recognition Gap v0 markers should remain visible.",
                  visibility_role: "Shows perceived governability against structural degradation.",
                },
              ],
              safeguard_coverage_matrix: {
                version: "v0",
                purpose: "Map representative governance attack surfaces to structural safeguards and the evidence required to make coverage visible.",
                coverage_model: "deterministic_representative_visibility_matrix",
                scope: {
                  included: ["failure_class_to_safeguard_mapping"],
                  excluded: ["complete_prevention_claim"],
                },
                rows: [
                  {
                    failure_class_id: "self_authorization",
                    primary_safeguard_id: "separation_of_decision_and_governance_authority",
                    supporting_safeguard_ids: ["append_only_governance_log"],
                    evidence_requirement: "independent_governance_authority_marker",
                    visibility_question: "Can reviewers see whether authority is separate?",
                    coverage_state: "representative_visibility_only",
                    limitation: "does_not_claim_complete_prevention_or_runtime_enforcement",
                  },
                  {
                    failure_class_id: "evidence_chain_manipulation",
                    primary_safeguard_id: "immutable_evidence_chain",
                    supporting_safeguard_ids: ["append_only_governance_log"],
                    evidence_requirement: "ordered_append_only_evidence_chain",
                    visibility_question: "Can reviewers replay evidence?",
                    coverage_state: "representative_visibility_only",
                    limitation: "does_not_claim_tamper_proof_storage_or_formal_verification",
                  },
                  {
                    failure_class_id: "approval_receipt_spoofing",
                    primary_safeguard_id: "approval_receipt_provenance",
                    supporting_safeguard_ids: ["separation_of_decision_and_governance_authority"],
                    evidence_requirement: "actor_source_timestamp_scope_validity_context",
                    visibility_question: "Can reviewers distinguish approval provenance?",
                    coverage_state: "representative_visibility_only",
                    limitation: "does_not_claim_identity_proof_or_production_authentication",
                  },
                  {
                    failure_class_id: "policy_snapshot_drift",
                    primary_safeguard_id: "policy_snapshot_hashing",
                    supporting_safeguard_ids: ["immutable_evidence_chain"],
                    evidence_requirement: "bind_time_policy_hash_and_version",
                    visibility_question: "Can reviewers reconstruct bind-time policy?",
                    coverage_state: "representative_visibility_only",
                    limitation: "does_not_claim_policy_correctness_or_regulatory_certification",
                  },
                  {
                    failure_class_id: "recognition_gap_masking",
                    primary_safeguard_id: "recognition_gap_visibility_marker",
                    supporting_safeguard_ids: ["replayable_escalation_trace"],
                    evidence_requirement: "actor_recognition_gap_marker_sequence",
                    visibility_question: "Can reviewers compare perceived governability with degradation?",
                    coverage_state: "representative_visibility_only",
                    limitation: "does_not_infer_actor_psychology_or_intent",
                  },
                ],
                validation_question: "Which structural safeguard covers which governance attack surface, and what evidence makes that coverage visible?",
                summary: {
                  concise: "Governance Safeguard Coverage Matrix v0 maps each representative governance attack surface to structural safeguards and the evidence required to inspect coverage.",
                  operator: "Show coverage visibility without prevention claims.",
                },
              },
              validation_question: "What structural safeguards prevent the governance process itself from becoming the attack surface?",
              summary: {
                concise: "Governance Attack Surface Registry v0 identifies representative governance-process attack surfaces.",
                operator: "Show safeguards without enforcement claims.",
              },
            },
            intervention_actionability_map: {
              version: "v0",
              purpose: "Map visible governance markers to representative intervention categories without claiming automatic enforcement.",
              actionability_model: "deterministic_representative_intervention_guidance",
              scope: {
                included: ["marker_to_actionability_mapping"],
                excluded: ["automatic_enforcement"],
              },
              intervention_categories: [
                { id: "observe", label: "Observe", description: "Record the visible marker." },
                { id: "annotate", label: "Annotate", description: "Add explanatory context." },
                { id: "warn", label: "Warn", description: "Surface a warning." },
                { id: "preserve_evidence", label: "Preserve evidence", description: "Preserve marker evidence." },
                { id: "reframe", label: "Reframe", description: "Rebalance option framing." },
                { id: "pause", label: "Pause", description: "Hold progression before bind." },
                { id: "escalate", label: "Escalate", description: "Route to review." },
                { id: "require_explicit_approval", label: "Require explicit approval", description: "Require scope-bound approval." },
                { id: "freeze_bind_path", label: "Freeze bind path", description: "Preserve the current bind path." },
                { id: "post_horizon_review", label: "Post-horizon review", description: "Flag post-horizon review." },
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
              validation_question: "When a governance marker becomes visible, what representative intervention category becomes actionable?",
              summary: {
                concise: "Intervention Actionability Map v0 connects visible governance markers to representative intervention categories and evidence preservation guidance.",
                operator: "Show representative action category without automatic enforcement claims.",
              },
            },
            governance_evidence_packet: {
              version: "v0",
              packet_id: "pre_boundary_collapse_governance_evidence_packet_v0",
              packet_model: "deterministic_representative_reviewer_packet",
              purpose: "Summarize the governance trace, evidence refs, safeguards, and representative intervention categories for reviewer inspection.",
              generated_from: {
                scenario_id: "pre_boundary_collapse",
                source_payload: "governance_layer_snapshot",
              },
              decision_context_summary: {
                bind_outcome: "FORMALLY_VALID_STRUCTURALLY_COLLAPSED",
                participation_signal: "decision_shaping",
                preservation_state: "collapsed",
                intervention_viability: "lost",
                decision_space_state: "structurally_narrowed_before_bind",
                summary: "The bind outcome remains formally valid while governance evidence indicates decision-space narrowing and intervention viability loss occurred upstream.",
              },
              packet_sections: [
                {
                  id: "trajectory_summary",
                  source_layer: "trajectory_shaping_lineage_v0",
                  title: "Trajectory shaping summary",
                  key_points: ["Decision-space transformation occurred before bind."],
                  evidence_refs: ["governance_layer_snapshot.trajectory_shaping_lineage"],
                },
                {
                  id: "dynamic_degradation_summary",
                  source_layer: "dynamic_conditions_validation_v0",
                  title: "Dynamic degradation summary",
                  key_points: ["The intervention window compresses before bind."],
                  evidence_refs: ["governance_layer_snapshot.trajectory_shaping_lineage.dynamic_conditions_validation_case"],
                },
                {
                  id: "irreversibility_summary",
                  source_layer: "irreversibility_horizon_v0",
                  title: "Irreversibility horizon summary",
                  key_points: ["Bind occurs after the representative horizon."],
                  evidence_refs: ["governance_layer_snapshot.trajectory_shaping_lineage.dynamic_conditions_validation_case.irreversibility_horizon"],
                },
                {
                  id: "recognition_gap_summary",
                  source_layer: "actor_recognition_gap_v0",
                  title: "Actor recognition gap summary",
                  key_points: ["Bind occurs after the recognition gap."],
                  evidence_refs: ["governance_layer_snapshot.trajectory_shaping_lineage.dynamic_conditions_validation_case.irreversibility_horizon.actor_recognition_gap"],
                },
                {
                  id: "governance_attack_surface_summary",
                  source_layer: "governance_attack_surface_registry_v0",
                  title: "Governance attack surface summary",
                  key_points: ["The governance process itself can become an attack surface."],
                  evidence_refs: ["governance_layer_snapshot.governance_attack_surface_registry"],
                },
                {
                  id: "safeguard_coverage_summary",
                  source_layer: "governance_safeguard_coverage_matrix_v0",
                  title: "Safeguard coverage summary",
                  key_points: ["Coverage remains representative visibility only."],
                  evidence_refs: ["governance_layer_snapshot.governance_attack_surface_registry.safeguard_coverage_matrix"],
                },
                {
                  id: "intervention_actionability_summary",
                  source_layer: "intervention_actionability_map_v0",
                  title: "Intervention actionability summary",
                  key_points: ["The map provides guidance without automatic enforcement."],
                  evidence_refs: ["governance_layer_snapshot.intervention_actionability_map"],
                },
              ],
              reviewer_questions: [
                "What was the bind outcome?",
                "What decision-space narrowing occurred before bind?",
                "Which intervention categories were representative?",
                "What does this packet not claim?",
              ],
              preserved_evidence_refs: [
                "governance_layer_snapshot.trajectory_shaping_lineage",
                "governance_layer_snapshot.governance_attack_surface_registry",
                "governance_layer_snapshot.governance_attack_surface_registry.safeguard_coverage_matrix",
                "governance_layer_snapshot.intervention_actionability_map",
              ],
              limitations: [
                "not_certification",
                "not_production_security_guarantee",
                "not_automatic_enforcement",
                "not_scoring_model",
              ],
              summary: {
                concise: "Governance Evidence Packet v0 gives reviewers a compact, deterministic summary of the governance trace, evidence refs, safeguards, and representative intervention categories.",
                operator: "Show what evidence a reviewer should inspect without enforcement claims.",
              },
            },
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("Pre-Boundary Collapse Demo · 4 phase walkthrough")).toBeInTheDocument();
    expect(screen.getByText("formally valid, structurally collapsed")).toBeInTheDocument();
    expect(screen.getByText("Participation / open framing")).toBeInTheDocument();
    expect(screen.getByText("Iterative shaping")).toBeInTheDocument();
    expect(screen.getByText("Pre-boundary collapse")).toBeInTheDocument();
    expect(screen.getByText("Bind")).toBeInTheDocument();
    expect(screen.getAllByText(/participation_state:/).length).toBeGreaterThan(1);
    expect(screen.getAllByText("decision_shaping").length).toBeGreaterThan(0);
    expect(screen.getAllByText("collapsed").length).toBeGreaterThan(0);
    expect(screen.getByTestId("trajectory-shaping-lineage-panel")).toBeInTheDocument();
    expect(screen.getByText("Trajectory Shaping Lineage v0")).toBeInTheDocument();
    expect(screen.getByText("Decision-space transformation before bind")).toBeInTheDocument();
    expect(screen.getAllByText(/first detectable asymmetry:/).length).toBeGreaterThan(1);
    expect(screen.getAllByText(/intervention viability loss:/).length).toBeGreaterThan(1);
    expect(screen.getByText(/bind evaluation:/)).toBeInTheDocument();
    expect(screen.getAllByText("A/B/C/D Minimal Validation Case").length).toBeGreaterThan(0);
    expect(screen.getByText("Testing separation between preservation, intervention viability, and formal bind admissibility")).toBeInTheDocument();
    expect(screen.getAllByText(/formal admissibility:/).length).toBeGreaterThan(0);
    expect(screen.getByText("Dynamic Conditions Validation v0")).toBeInTheDocument();
    expect(screen.getByText("Testing separation stability under reinforcement, exposure asymmetry, time pressure, and adaptive behavior")).toBeInTheDocument();
    expect(screen.getByText("reinforcement")).toBeInTheDocument();
    expect(screen.getByText("exposure asymmetry")).toBeInTheDocument();
    expect(screen.getByText("time pressure")).toBeInTheDocument();
    expect(screen.getByText("adaptive behavior")).toBeInTheDocument();
    expect(screen.getByText(/intervention window compression:/)).toBeInTheDocument();
    expect(screen.getByText(/adaptive narrowing:/)).toBeInTheDocument();
    expect(screen.getAllByText(/formal admissibility:/).length).toBeGreaterThan(1);
    expect(screen.getByText("Irreversibility Horizon v0")).toBeInTheDocument();
    expect(screen.getByText("Marking the last meaningful intervention point before operational irreversibility stabilizes")).toBeInTheDocument();
    expect(screen.getByText(/first structural degradation signal:/)).toBeInTheDocument();
    expect(screen.getByText(/early warning:/)).toBeInTheDocument();
    expect(screen.getByText(/last meaningful intervention:/)).toBeInTheDocument();
    expect(screen.getByText(/irreversibility horizon:/)).toBeInTheDocument();
    expect(screen.getByText(/bind after horizon:/)).toBeInTheDocument();
    expect(screen.getByText("Actor Recognition Gap v0")).toBeInTheDocument();
    expect(screen.getByText("Marking the gap between structural degradation and actor recognition of intervention capacity loss")).toBeInTheDocument();
    expect(screen.getByText(/actual degradation visible:/)).toBeInTheDocument();
    expect(screen.getByText(/actor still perceives governable:/)).toBeInTheDocument();
    expect(screen.getByText(/intervention visibility degradation:/)).toBeInTheDocument();
    expect(screen.getAllByText(/recognition gap:/).length).toBeGreaterThan(0);
    expect(screen.getByText(/recognition alignment:/)).toBeInTheDocument();
    expect(screen.getByText(/bind after recognition gap:/)).toBeInTheDocument();
    expect(screen.getByText("Governance Attack Surface Registry v0")).toBeInTheDocument();
    expect(screen.getByText("Making representative governance-process attack surfaces and structural safeguards visible")).toBeInTheDocument();
    expect(screen.getAllByText("self-authorization").length).toBeGreaterThan(0);
    expect(screen.getAllByText("evidence-chain manipulation").length).toBeGreaterThan(0);
    expect(screen.getAllByText("approval receipt spoofing").length).toBeGreaterThan(0);
    expect(screen.getAllByText("policy snapshot drift").length).toBeGreaterThan(0);
    expect(screen.getAllByText("escalation suppression").length).toBeGreaterThan(0);
    expect(screen.getByText("replay trace tampering")).toBeInTheDocument();
    expect(screen.getAllByText("recognition gap masking").length).toBeGreaterThan(0);
    expect(screen.getAllByText("separation of decision and governance authority").length).toBeGreaterThan(0);
    expect(screen.getAllByText("immutable evidence chain").length).toBeGreaterThan(0);
    expect(screen.getByText("append-only governance log")).toBeInTheDocument();
    expect(screen.getByText("Governance Safeguard Coverage Matrix v0")).toBeInTheDocument();
    expect(screen.getByText("Mapping governance attack surfaces to structural safeguards and visibility evidence")).toBeInTheDocument();
    expect(screen.getAllByText("self-authorization").length).toBeGreaterThan(0);
    expect(screen.getAllByText("separation of decision and governance authority").length).toBeGreaterThan(0);
    expect(screen.getByText("independent governance authority marker")).toBeInTheDocument();
    expect(screen.getAllByText("evidence-chain manipulation").length).toBeGreaterThan(0);
    expect(screen.getAllByText("immutable evidence chain").length).toBeGreaterThan(0);
    expect(screen.getAllByText("approval receipt spoofing").length).toBeGreaterThan(0);
    expect(screen.getAllByText("approval receipt provenance").length).toBeGreaterThan(0);
    expect(screen.getAllByText("policy snapshot drift").length).toBeGreaterThan(0);
    expect(screen.getAllByText("policy snapshot hashing").length).toBeGreaterThan(0);
    expect(screen.getAllByText("recognition gap masking").length).toBeGreaterThan(0);
    expect(screen.getAllByText("recognition gap visibility marker").length).toBeGreaterThan(0);
    expect(screen.getByText("Intervention Actionability Map v0")).toBeInTheDocument();
    expect(screen.getByText("Mapping visible governance markers to representative intervention categories")).toBeInTheDocument();
    expect(screen.getByText("first structural degradation signal")).toBeInTheDocument();
    expect(screen.getByText("early warning")).toBeInTheDocument();
    expect(screen.getByText("last meaningful intervention")).toBeInTheDocument();
    expect(screen.getAllByText("irreversibility horizon").length).toBeGreaterThan(0);
    expect(screen.getAllByText("actor recognition gap").length).toBeGreaterThan(0);
    expect(screen.getAllByText("self-authorization").length).toBeGreaterThan(0);
    expect(screen.getAllByText("evidence-chain manipulation").length).toBeGreaterThan(0);
    expect(screen.getAllByText("approval receipt spoofing").length).toBeGreaterThan(0);
    expect(screen.getAllByText("escalation suppression").length).toBeGreaterThan(0);
    expect(screen.getAllByText("freeze bind path").length).toBeGreaterThan(0);
    expect(screen.getAllByText("require explicit approval").length).toBeGreaterThan(0);
    expect(screen.getAllByText("post-horizon review").length).toBeGreaterThan(0);
    expect(screen.getAllByText("preserve evidence").length).toBeGreaterThan(0);
    expect(screen.getByText("Governance Evidence Packet v0")).toBeInTheDocument();
    expect(screen.getByText("Reviewer-ready summary of governance trace, evidence refs, safeguards, and representative interventions")).toBeInTheDocument();
    expect(screen.getByText("Trajectory shaping summary")).toBeInTheDocument();
    expect(screen.getByText("Dynamic degradation summary")).toBeInTheDocument();
    expect(screen.getByText("Irreversibility horizon summary")).toBeInTheDocument();
    expect(screen.getByText("Actor recognition gap summary")).toBeInTheDocument();
    expect(screen.getByText("Governance attack surface summary")).toBeInTheDocument();
    expect(screen.getByText("Safeguard coverage summary")).toBeInTheDocument();
    expect(screen.getByText("Intervention actionability summary")).toBeInTheDocument();
    expect(screen.getByText("not certification")).toBeInTheDocument();
    expect(screen.getByText("not production security guarantee")).toBeInTheDocument();
    expect(screen.getByText("not automatic enforcement")).toBeInTheDocument();
  });

  it.each(["/governance", "/governance/receipts/br_123", "/audit?receipt=br_123"])("renders safe relevant_ui_href as link: %s", (href) => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            pre_bind_source: "trustlog_matching_decision",
            relevant_ui_href: href,
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getAllByRole("link", { name: href })[0]).toHaveAttribute("href", href);
  });

  it.each([
    "https://evil.example",
    "http://evil.example",
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "//evil.example",
  ])("does not render external or protocol relevant_ui_href as a link: %s", (href) => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            pre_bind_source: "trustlog_matching_decision",
            relevant_ui_href: href,
          }}
        />
      </I18nProvider>,
    );

    expect(screen.queryByRole("link", { name: href })).not.toBeInTheDocument();
    expect(screen.getByText(href)).toBeInTheDocument();
    expect(screen.getByText(/unsafe or external link not rendered/)).toBeInTheDocument();
  });


  it("renders AML/KYC reviewer walkthrough panel with safe links and fail-closed labels", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            demo_scenario: "aml_kyc_reviewer_walkthrough",
            source_state: "fixture",
            scenario_id: "scenario_e_missing_authority",
            scenario_name: "scenario_e_missing_authority",
            action_class: "aml_kyc_customer_risk_escalation",
            requested_action: "create_internal_risk_escalation",
            requested_scope: "create_internal_risk_escalation",
            authority_evidence_status: "missing",
            bind_outcome: "block",
            bind_reason_code: "AUTHORITY_MISSING",
            bind_failure_reason: "authority evidence missing",
            decision_id: "fixture.decision.aml_kyc.scenario_e_missing_authority",
            execution_intent_id: "fixture.execution_intent.aml_kyc.scenario_e_missing_authority",
            bind_receipt_id: "fixture.bind_receipt.aml_kyc.scenario_e_missing_authority",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("AML/KYC Reviewer Walkthrough")).toBeInTheDocument();
    expect(screen.getByText(/Authority Evidence:/)).toBeInTheDocument();
    expect(screen.getAllByText("AUTHORITY_MISSING").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "open audit path" }).length).toBeGreaterThan(0);
  });

  it.each(["/foo\\bar", "/foo\nbar", "/foo\tbar"])("does not render malformed relevant_ui_href as a link: %s", (href) => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            pre_bind_source: "trustlog_matching_decision",
            relevant_ui_href: href,
          }}
        />
      </I18nProvider>,
    );

    expect(screen.queryByRole("link", { name: href })).not.toBeInTheDocument();
    expect(screen.getByText(/unsafe or external link not rendered/)).toBeInTheDocument();
  });

  it("renders not available when relevant_ui_href is null", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            pre_bind_source: "none",
            relevant_ui_href: null,
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText(/relevant_ui_href:/)).toBeInTheDocument();
    expect(screen.getAllByText("not available").length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: /relevant_ui_href/i })).not.toBeInTheDocument();
    expect(screen.getByText(/Open target surface:/)).toBeInTheDocument();
    expect(screen.getAllByText(/not available/).length).toBeGreaterThan(0);
  });

  it("renders target surface action as link only when relevant_ui_href is safe", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            target_label: "Governance policy",
            relevant_ui_href: "/governance",
            bind_receipt_id: "br_123",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getAllByRole("link", { name: "/governance" })[0]).toHaveAttribute("href", "/governance");
  });

  it("does not render target surface action link when relevant_ui_href is unsafe", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            relevant_ui_href: "https://evil.example",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.queryByRole("link", { name: "https://evil.example" })).not.toBeInTheDocument();
    expect(screen.getByText(/unsafe or external link not rendered/)).toBeInTheDocument();
  });

  it("renders bind receipt id as audit link when id is valid", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            bind_receipt_id: "br_123",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("Review bind receipt:")).toBeInTheDocument();
    expect(screen.getByText("br_123")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "br_123" })).toHaveAttribute("href", "/audit?bind_receipt_id=br_123");
  });

  it("renders decision id as audit link when id is valid", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            decision_id: "dec_123",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("View decision artifact:")).toBeInTheDocument();
    expect(screen.getByText("dec_123")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "dec_123" })).toHaveAttribute("href", "/audit?decision_id=dec_123");
  });

  it("renders execution intent id as audit link when id is valid", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            execution_intent_id: "ei_123",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("View execution intent:")).toBeInTheDocument();
    expect(screen.getByText("ei_123")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "ei_123" })).toHaveAttribute("href", "/audit?execution_intent_id=ei_123");
  });

  it("covers demo-grade Mission Control artifact review actions with safe audit links only", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            decision_id: "dec_demo_001",
            bind_receipt_id: "br_demo_001",
            execution_intent_id: "ei_demo_001",
            pre_bind_source: "trustlog_matching_decision",
            bind_reason_code: "AUTHORITY_MISSING",
            bind_failure_reason: "Authority evidence missing",
            target_label: "Governance policy",
            relevant_ui_href: "/governance",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("Governance artifacts")).toBeInTheDocument();
    expect(screen.getAllByText("trustlog_matching_decision").length).toBeGreaterThan(0);
    expect(screen.getAllByText("AUTHORITY_MISSING").length).toBeGreaterThan(0);
    expect(screen.getByText("Authority evidence missing")).toBeInTheDocument();
    expect(screen.getByText("Governance policy")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "/governance" })[0]).toHaveAttribute("href", "/governance");
    expect(screen.getByRole("link", { name: "br_demo_001" })).toHaveAttribute("href", "/audit?bind_receipt_id=br_demo_001");
    expect(screen.getByRole("link", { name: "dec_demo_001" })).toHaveAttribute("href", "/audit?decision_id=dec_demo_001");
    expect(screen.getByRole("link", { name: "ei_demo_001" })).toHaveAttribute("href", "/audit?execution_intent_id=ei_demo_001");
    expect(screen.queryByRole("link", { name: "/decisions/dec_demo_001" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "/execution-intents/ei_demo_001" })).not.toBeInTheDocument();
    expect(document.querySelector('a[href^="/trustlog"]')).toBeNull();
  });


  it("does not create audit links for invalid artifact ids", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            bind_receipt_id: "../secret",
            decision_id: "javascript:alert(1)",
            execution_intent_id: "ei\n123",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.queryByRole("link", { name: "../secret" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "javascript:alert(1)" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /ei/i })).not.toBeInTheDocument();
    expect(screen.getAllByText(/route unavailable/).length).toBeGreaterThan(0);
  });
it("shows pre-bind source without creating a fake trustlog route", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            pre_bind_source: "trustlog_matching_decision",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("View pre-bind source:")).toBeInTheDocument();
    expect(screen.getAllByText("trustlog_matching_decision").length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: /trustlog_matching_decision/i })).not.toBeInTheDocument();
  });

  it("renders fallback text for null pre-bind summaries", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            pre_bind_source: "none",
            pre_bind_detection_summary: null,
            pre_bind_preservation_summary: null,
            bind_reason_code: null,
            bind_failure_reason: null,
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getAllByText("none").length).toBeGreaterThan(0);
    expect(screen.getAllByText("No pre-bind summary available").length).toBeGreaterThan(0);
  });

  it("shows degraded pre-bind source markers without crashing", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            pre_bind_source: "malformed_pre_bind_artifact",
            participation_state: "unknown",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getAllByText("malformed_pre_bind_artifact").length).toBeGreaterThan(0);
    expect(screen.getByText(/classification: degraded/)).toBeInTheDocument();
  });

  it("renders governance observation fields when payload includes governance_observation", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            governance_observation: {
              policy_mode: "observe",
              environment: "development",
              would_have_blocked: true,
              would_have_blocked_reason: "policy_violation:missing_authority_evidence",
              effective_outcome: "proceed",
              observed_outcome: "block",
              operator_warning: true,
              audit_required: true,
            },
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("Governance observation")).toBeInTheDocument();
    expect(screen.getByText("observe")).toBeInTheDocument();
    expect(screen.getByText("development")).toBeInTheDocument();
    expect(screen.getByText("would_have_blocked")).toBeInTheDocument();
    expect(screen.getAllByText("true").length).toBeGreaterThan(0);
    expect(screen.getByText("policy_violation:missing_authority_evidence")).toBeInTheDocument();
    expect(screen.getByText("effective_outcome")).toBeInTheDocument();
    expect(screen.getByText("proceed")).toBeInTheDocument();
    expect(screen.getByText("observed_outcome")).toBeInTheDocument();
    expect(screen.getByText("block")).toBeInTheDocument();
    expect(screen.getByText("operator_warning")).toBeInTheDocument();
    expect(screen.getByText("audit_required")).toBeInTheDocument();
  });

  it("does not render governance observation section when governance_observation is absent", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{}}
        />
      </I18nProvider>,
    );

    expect(screen.queryByText("Governance observation")).not.toBeInTheDocument();
    expect(screen.getByText("Governance artifacts")).toBeInTheDocument();
  });

  it("renders enforce mode governance observation fields", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            governance_observation: {
              policy_mode: "enforce",
              environment: "production",
              would_have_blocked: false,
              effective_outcome: "block",
              observed_outcome: "block",
              operator_warning: false,
              audit_required: true,
            },
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("enforce")).toBeInTheDocument();
    expect(screen.getByText("production")).toBeInTheDocument();
    expect(screen.getByText("would_have_blocked")).toBeInTheDocument();
    expect(screen.getAllByText("false").length).toBeGreaterThan(0);
  });
});
