import { expect, test, type Page } from "@playwright/test";

const E2E_SCENARIO_HEADER = "x-veritas-e2e-governance-scenario";

async function expectGovernanceTimeline(
  page: Page,
  expected: {
    participationState: string;
    preservationState: string;
    interventionViability: string;
    bindOutcome: string;
  },
): Promise<void> {
  const timeline = page.locator('section[aria-label="governance layer timeline"]');
  await expect(timeline).toBeVisible();

  const entries = timeline.locator("li");
  await expect(entries).toHaveCount(3);

  await expect(entries.nth(0)).toContainText("participation_state:");
  await expect(entries.nth(0)).toContainText(expected.participationState);

  await expect(entries.nth(1)).toContainText("preservation_state:");
  await expect(entries.nth(1)).toContainText(expected.preservationState);
  await expect(entries.nth(1)).toContainText("intervention_viability:");
  await expect(entries.nth(1)).toContainText(expected.interventionViability);

  await expect(entries.nth(2)).toContainText("bind_outcome:");
  await expect(entries.nth(2)).toContainText(expected.bindOutcome);
}

test.describe("Mission Control: governance feed frontend E2E", () => {
  test("main path reaches UI from /api/veritas/v1/report/governance", async ({ page }) => {
    await page.setExtraHTTPHeaders({ [E2E_SCENARIO_HEADER]: "main" });

    const apiResponse = await page.request.get("/api/veritas/v1/report/governance?e2e_governance_scenario=main");
    await expect(apiResponse).toBeOK();
    await expect(apiResponse.json()).resolves.toMatchObject({
      governance_layer_snapshot: {
        participation_state: "decision_shaping",
        preservation_state: "degrading",
        intervention_viability: "minimal",
        bind_outcome: "ESCALATED",
      },
    });

    await page.goto("/?e2e_governance_scenario=main");
    await expect(
      page.getByRole("heading", { name: /コマンドダッシュボード|Command Dashboard/i }),
    ).toBeVisible();

    await expectGovernanceTimeline(page, {
      participationState: "decision_shaping",
      preservationState: "degrading",
      interventionViability: "minimal",
      bindOutcome: "ESCALATED",
    });
  });

  test("endpoint unavailable path renders fallback safety snapshot without breaking page", async ({ page }) => {
    await page.setExtraHTTPHeaders({ [E2E_SCENARIO_HEADER]: "fallback" });
    await page.goto("/?e2e_governance_scenario=fallback");

    await expect(
      page.getByRole("heading", { name: /コマンドダッシュボード|Command Dashboard/i }),
    ).toBeVisible();

    await expectGovernanceTimeline(page, {
      participationState: "participatory",
      preservationState: "open",
      interventionViability: "high",
      bindOutcome: "BLOCKED",
    });
  });

  test("pre-boundary collapse demo path renders 4-phase walkthrough and keeps base timeline", async ({ page }) => {
    const apiResponse = await page.request.get(
      "/api/veritas/v1/report/governance?demo_scenario=pre_boundary_collapse",
    );
    await expect(apiResponse).toBeOK();
    const payload = await apiResponse.json();
    expect(payload).toMatchObject({
      governance_layer_snapshot: {
        demo_scenario: "pre_boundary_collapse",
        participation_state: "decision_shaping",
        preservation_state: "collapsed",
        intervention_viability: "low",
        bind_outcome: "FORMALLY_VALID_STRUCTURALLY_COLLAPSED",
      },
    });
    expect(payload.governance_layer_snapshot.phase_snapshots).toHaveLength(4);
    expect(payload.governance_layer_snapshot.trajectory_shaping_lineage.abcd_minimal_validation_case).toMatchObject({
      case_id: "abcd_minimal_trajectory_validation",
      version: "v0",
      options: ["A", "B", "C", "D"],
    });
    expect(payload.governance_layer_snapshot.trajectory_shaping_lineage.dynamic_conditions_validation_case).toMatchObject({
      case_id: "dynamic_conditions_trajectory_validation",
      version: "v0",
      base_case: "abcd_minimal_trajectory_validation",
      irreversibility_horizon: {
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
        actor_recognition_gap: {
          version: "v0",
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
        },
      },
    });

    await page.goto("/?demo_scenario=pre_boundary_collapse");

    await expect(
      page.getByRole("heading", { name: /コマンドダッシュボード|Command Dashboard/i }),
    ).toBeVisible();

    const walkthrough = page.locator(
      'section[aria-label="pre-boundary collapse demo walkthrough"]',
    );
    await expect(walkthrough).toBeVisible();
    await expect(walkthrough).toContainText("Pre-Boundary Collapse Demo · 4 phase walkthrough");
    await expect(walkthrough).toContainText("formally valid, structurally collapsed");
    await expect(walkthrough).toContainText("Phase 1 — Participation / open framing");
    await expect(walkthrough).toContainText("Phase 2 — Iterative shaping");
    await expect(walkthrough).toContainText("Phase 3 — Pre-boundary collapse");
    await expect(walkthrough).toContainText("Phase 4 — Bind");
    await expect(walkthrough).toContainText("participation_state: decision_shaping");
    await expect(walkthrough).toContainText(/preservation_state: (collapsed|degrading)/);
    await expect(walkthrough).toContainText(
      "bind_outcome: FORMALLY_VALID_STRUCTURALLY_COLLAPSED",
    );
    await expect(walkthrough).toContainText("lineage evidence summary");
    await expect(walkthrough).toContainText("Trajectory Shaping Lineage v0");
    await expect(walkthrough).toContainText("Decision-space transformation before bind");
    await expect(walkthrough).toContainText("first detectable asymmetry");
    await expect(walkthrough).toContainText("intervention viability loss");
    await expect(walkthrough).toContainText("bind evaluation");
    await expect(walkthrough).toContainText("A/B/C/D Minimal Validation Case");
    await expect(walkthrough).toContainText("Testing separation between preservation, intervention viability, and formal bind admissibility");
    await expect(walkthrough).toContainText("formal admissibility");
    await expect(walkthrough).toContainText("Irreversibility Horizon v0");
    await expect(walkthrough).toContainText("Marking the last meaningful intervention point before operational irreversibility stabilizes");
    await expect(walkthrough).toContainText("first structural degradation signal");
    await expect(walkthrough).toContainText("last meaningful intervention");
    await expect(walkthrough).toContainText("irreversibility horizon");
    await expect(walkthrough).toContainText("bind after horizon");
    await expect(walkthrough).toContainText("Actor Recognition Gap v0");
    await expect(walkthrough).toContainText("Marking the gap between structural degradation and actor recognition of intervention capacity loss");
    await expect(walkthrough).toContainText("actual degradation visible");
    await expect(walkthrough).toContainText("actor still perceives governable");
    await expect(walkthrough).toContainText("recognition gap");
    await expect(walkthrough).toContainText("recognition alignment");
    await expect(walkthrough).toContainText("bind after recognition gap");
    await expect(walkthrough).toContainText("Dynamic Conditions Validation v0");
    await expect(walkthrough).toContainText("Testing separation stability under reinforcement, exposure asymmetry, time pressure, and adaptive behavior");
    await expect(walkthrough).toContainText("intervention window compression");
    await expect(walkthrough).toContainText("adaptive narrowing");
    await expect(walkthrough).toContainText("formal admissibility");

    const timeline = page.locator('section[aria-label="governance layer timeline"]');
    await expect(timeline).toBeVisible();
    await expect(timeline).toContainText("bind_outcome:");
  });

});
