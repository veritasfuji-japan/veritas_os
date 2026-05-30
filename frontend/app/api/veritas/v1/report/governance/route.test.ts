import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("/api/veritas/v1/report/governance", () => {
  it("does not return deterministic main payload from query when e2e scenarios are disabled", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network"));

    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance?e2e_governance_scenario=main"));

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({ error: "governance_feed_unavailable" });
  });

  it("does not return deterministic main payload from header when e2e scenarios are disabled", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network"));

    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance", {
      headers: { "x-veritas-e2e-governance-scenario": "main" },
    }));

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({ error: "governance_feed_unavailable" });
  });

  it("returns deterministic main scenario payload when e2e scenarios are explicitly enabled", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_ENABLE_E2E_SCENARIOS", "1");

    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance", {
      headers: { "x-veritas-e2e-governance-scenario": "main" },
    }));

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      governance_layer_snapshot: {
        participation_state: "decision_shaping",
        preservation_state: "degrading",
        intervention_viability: "minimal",
        bind_outcome: "ESCALATED",
      },
    });
  });

  it("returns deterministic fallback scenario payload in test environment", async () => {
    vi.stubEnv("NODE_ENV", "test");

    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance?e2e_governance_scenario=fallback"));

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      governance_layer_snapshot: {
        participation_state: "participatory",
        preservation_state: "open",
        intervention_viability: "high",
        bind_outcome: "BLOCKED",
      },
    });
  });

  it("returns governance_layer_snapshot as backend-fed main path", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          governance_layer_snapshot: {
            participation_state: "decision_shaping",
            preservation_state: "degrading",
            bind_outcome: "ESCALATED",
          },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance"));

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      governance_layer_snapshot: {
        participation_state: "decision_shaping",
        preservation_state: "degrading",
        bind_outcome: "ESCALATED",
      },
    });
  });


  it("preserves enriched governance_layer_snapshot metadata fields", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          governance_layer_snapshot: {
            bind_outcome: "ESCALATED",
            bind_receipt_id: "br_123",
            execution_intent_id: "ei_123",
            bind_summary: { bind_outcome: "ESCALATED" },
            pre_bind_source: "trustlog_matching_decision",
            pre_bind_detection_summary: { participation_state: "decision_shaping" },
            pre_bind_preservation_summary: { preservation_state: "degrading" },
            pre_bind_detection_detail: { artifact: "detection" },
            pre_bind_preservation_detail: { artifact: "preservation" },
            bind_reason_code: "AUTHORITY_MISSING",
            bind_failure_reason: "Authority evidence missing",
            target_label: "Governance policy",
            operator_surface: "governance",
            relevant_ui_href: "/governance",
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
          },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance"));

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      governance_layer_snapshot: {
        bind_outcome: "ESCALATED",
        bind_receipt_id: "br_123",
        execution_intent_id: "ei_123",
        bind_summary: { bind_outcome: "ESCALATED" },
        pre_bind_source: "trustlog_matching_decision",
        pre_bind_detection_summary: { participation_state: "decision_shaping" },
        pre_bind_preservation_summary: { preservation_state: "degrading" },
        pre_bind_detection_detail: { artifact: "detection" },
        pre_bind_preservation_detail: { artifact: "preservation" },
        bind_reason_code: "AUTHORITY_MISSING",
        bind_failure_reason: "Authority evidence missing",
        target_label: "Governance policy",
        operator_surface: "governance",
        relevant_ui_href: "/governance",
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
      },
    });
  });

  it("keeps compatibility with pre_bind_governance_snapshot payloads", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          pre_bind_governance_snapshot: {
            participation_state: "participatory",
            preservation_state: "open",
          },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance"));

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      pre_bind_governance_snapshot: {
        participation_state: "participatory",
        preservation_state: "open",
      },
    });
  });

  it("calls /v1/governance/live-snapshot when scenarios are not used", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ governance_layer_snapshot: { bind_outcome: "UNKNOWN" } }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await GET(new Request("http://localhost/api/veritas/v1/report/governance"));

    expect(fetchSpy).toHaveBeenCalledWith("http://internal-api:8000/v1/governance/live-snapshot", expect.any(Object));
  });

  it("returns unavailable when upstream live snapshot is unavailable", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 503 }));

    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance"));

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({ error: "governance_feed_unavailable" });
  });

  it("returns pre-boundary collapse demo scenario payload from query seam", async () => {
    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance?demo_scenario=pre_boundary_collapse"));

    expect(response.status).toBe(200);
    const payload = await response.json() as {
      governance_layer_snapshot: {
        participation_state: string;
        preservation_state: string;
        intervention_viability: string;
        bind_outcome: string;
        phase_snapshots: Array<Record<string, unknown>>;
        trajectory_shaping_lineage: {
          scenario_id: string;
          version: string;
          initial_option_space: { options: string[] };
          sequence: Array<Record<string, unknown>>;
          transition_points: Record<string, string>;
          evidence_requirements: string[];
          summary: Record<string, string>;
          abcd_minimal_validation_case: {
            case_id: string;
            version: string;
            options: string[];
            phases: Array<Record<string, unknown>>;
            separation_points: Record<string, string>;
          };
          dynamic_conditions_validation_case: {
            case_id: string;
            version: string;
            base_case: string;
            options: string[];
            dynamic_factors: string[];
            phases: Array<Record<string, unknown>>;
            separation_points: Record<string, string>;
          };
        };
      };
    };
    expect(payload.governance_layer_snapshot.phase_snapshots).toHaveLength(4);
    expect(payload.governance_layer_snapshot).toMatchObject({
      participation_state: "decision_shaping",
      preservation_state: "collapsed",
      intervention_viability: "low",
      bind_outcome: "FORMALLY_VALID_STRUCTURALLY_COLLAPSED",
    });
    expect(payload.governance_layer_snapshot.phase_snapshots[0]).toMatchObject({
      phase_id: "pre_boundary_collapse_phase_1_open",
      phase_label: "Phase 1 — Participation / open framing",
      participation_state: "informative",
      preservation_state: "open",
      intervention_viability: "high",
      bind_outcome: "FORMALLY_VALID_UPSTREAM_OPEN",
      concise_rationale: expect.any(String),
      lineage_evidence: expect.any(Object),
      effective_optionality: "full",
      option_exposure_summary: "A:high, B:high, C:high, D:high",
      reinforcement_asymmetry_summary: "none",
    });
    expect(payload.governance_layer_snapshot.trajectory_shaping_lineage).toMatchObject({
      scenario_id: "pre_boundary_collapse",
      version: "v0",
      initial_option_space: { options: ["A", "B", "C", "D"] },
    });
    expect(
      payload.governance_layer_snapshot.trajectory_shaping_lineage.summary,
    ).toMatchObject({
      concise: expect.any(String),
      operator: expect.any(String),
    });
    expect(
      payload.governance_layer_snapshot.trajectory_shaping_lineage.evidence_requirements,
    ).toHaveLength(7);
    expect(payload.governance_layer_snapshot.trajectory_shaping_lineage.sequence).toHaveLength(4);
    expect(payload.governance_layer_snapshot.trajectory_shaping_lineage.transition_points).toMatchObject({
      first_detectable_asymmetry_phase: "phase_2_iterative_shaping",
      intervention_viability_loss_phase: "phase_3_pre_boundary_collapse",
      bind_evaluation_phase: "phase_4_bind",
    });
    expect(payload.governance_layer_snapshot.trajectory_shaping_lineage.abcd_minimal_validation_case).toMatchObject({
      case_id: "abcd_minimal_trajectory_validation",
      version: "v0",
      options: ["A", "B", "C", "D"],
      separation_points: {
        intervention_viability_loss_phase: "phase_4_intervention_viability_loss",
        formal_admissibility_phase: "phase_5_bind_over_narrowed_space",
      },
    });
    expect(
      payload.governance_layer_snapshot.trajectory_shaping_lineage.abcd_minimal_validation_case.phases,
    ).toHaveLength(5);
    expect(payload.governance_layer_snapshot.trajectory_shaping_lineage.dynamic_conditions_validation_case).toMatchObject({
      case_id: "dynamic_conditions_trajectory_validation",
      version: "v0",
      base_case: "abcd_minimal_trajectory_validation",
      options: ["A", "B", "C", "D"],
      separation_points: {
        intervention_viability_loss_phase: "phase_4_adaptive_narrowing",
        formal_admissibility_phase: "phase_5_bind_over_dynamically_narrowed_space",
      },
    });
    expect(
      payload.governance_layer_snapshot.trajectory_shaping_lineage.dynamic_conditions_validation_case.dynamic_factors,
    ).toEqual(expect.arrayContaining([
      "reinforcement",
      "exposure_asymmetry",
      "time_pressure",
      "adaptive_system_behavior",
    ]));
    expect(
      payload.governance_layer_snapshot.trajectory_shaping_lineage.dynamic_conditions_validation_case.phases,
    ).toHaveLength(5);
    expect(payload.governance_layer_snapshot.trajectory_shaping_lineage.dynamic_conditions_validation_case.irreversibility_horizon).toMatchObject({
      version: "v0",
      base_case: "dynamic_conditions_trajectory_validation",
      horizon_model: "deterministic_representative_marker",
      markers: {
        first_structural_degradation_signal_phase: "phase_2_reinforcement_exposure_asymmetry",
        early_warning_phase: "phase_3_time_pressure_compression",
        last_meaningful_intervention_phase: "phase_3_time_pressure_compression",
        irreversibility_horizon_phase: "phase_4_adaptive_narrowing",
        bind_after_horizon_phase: "phase_5_bind_over_dynamically_narrowed_space",
      },
    });

  });

  it("returns pre-boundary collapse demo scenario payload from header seam", async () => {
    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance", {
      headers: { "x-veritas-demo-scenario": "pre_boundary_collapse" },
    }));

    expect(response.status).toBe(200);
    const payload = await response.json() as { governance_layer_snapshot: { bind_outcome: string; phase_snapshots: Array<Record<string, unknown>> } };
    expect(payload.governance_layer_snapshot.bind_outcome).toBe("FORMALLY_VALID_STRUCTURALLY_COLLAPSED");
    expect(payload.governance_layer_snapshot.phase_snapshots.map((phase) => phase.phase_id)).toEqual([
      "pre_boundary_collapse_phase_1_open",
      "pre_boundary_collapse_phase_2_iterative_shaping",
      "pre_boundary_collapse_phase_3_collapse",
      "pre_boundary_collapse_phase_4_bind",
    ]);
  });


  it("returns AML/KYC reviewer walkthrough payload from query seam", async () => {
    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance?demo_scenario=aml_kyc_reviewer_walkthrough"));
    expect(response.status).toBe(200);
    const payload = await response.json() as { governance_layer_snapshot: Record<string, unknown> };
    expect(payload.governance_layer_snapshot).toMatchObject({
      demo_scenario: "aml_kyc_reviewer_walkthrough",
      source_state: "fixture",
      scenario_id: "scenario_e_missing_authority",
      authority_evidence_status: "missing",
      bind_outcome: "block",
      bind_reason_code: "AUTHORITY_MISSING",
    });
  });

  it("returns AML/KYC reviewer walkthrough payload from header seam", async () => {
    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance", {
      headers: { "x-veritas-demo-scenario": "aml_kyc_reviewer_walkthrough" },
    }));
    expect(response.status).toBe(200);
    const payload = await response.json() as { governance_layer_snapshot: { audit_trace: Array<{ event: string }> } };
    expect(payload.governance_layer_snapshot.audit_trace.map((item) => item.event)).toEqual([
      "decision_created",
      "execution_intent_requested",
      "authority_evidence_validation_failed",
      "bind_boundary_blocked",
      "bind_receipt_recorded",
    ]);
  });

  it("falls back to upstream path when demo scenario is invalid", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ governance_layer_snapshot: { bind_outcome: "UNKNOWN" } }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance?demo_scenario=unknown"));

    expect(response.status).toBe(200);
    expect(fetchSpy).toHaveBeenCalledOnce();
  });

});
