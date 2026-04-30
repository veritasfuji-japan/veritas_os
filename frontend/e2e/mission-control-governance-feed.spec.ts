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
});
