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

    const timeline = page.locator('section[aria-label="governance layer timeline"]');
    await expect(timeline).toBeVisible();
    await expect(timeline).toContainText("bind_outcome:");
  });

});
