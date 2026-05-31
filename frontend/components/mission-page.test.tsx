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
              validation_question: "What structural safeguards prevent the governance process itself from becoming the attack surface?",
              summary: {
                concise: "Governance Attack Surface Registry v0 identifies representative governance-process attack surfaces.",
                operator: "Show safeguards without enforcement claims.",
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
    expect(screen.getByText("self-authorization")).toBeInTheDocument();
    expect(screen.getByText("evidence-chain manipulation")).toBeInTheDocument();
    expect(screen.getByText("approval receipt spoofing")).toBeInTheDocument();
    expect(screen.getByText("policy snapshot drift")).toBeInTheDocument();
    expect(screen.getByText("escalation suppression")).toBeInTheDocument();
    expect(screen.getByText("replay trace tampering")).toBeInTheDocument();
    expect(screen.getByText("recognition gap masking")).toBeInTheDocument();
    expect(screen.getByText("separation of decision and governance authority")).toBeInTheDocument();
    expect(screen.getByText("immutable evidence chain")).toBeInTheDocument();
    expect(screen.getByText("append-only governance log")).toBeInTheDocument();
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
