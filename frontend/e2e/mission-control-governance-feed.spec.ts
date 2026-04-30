import { expect, type Locator, test, type Page } from "@playwright/test";

const E2E_SCENARIO_HEADER = "x-veritas-e2e-governance-scenario";

async function openScenario(page: Page, scenario: "main" | "fallback"): Promise<Locator> {
  await page.setExtraHTTPHeaders({ [E2E_SCENARIO_HEADER]: scenario });
  await page.goto(`/?e2e_governance_scenario=${scenario}`);

  const governanceTimeline = page.getByRole("region", {
    name: "governance layer timeline",
  });
  await expect(
    page.getByRole("heading", { name: /コマンドダッシュボード|Command Dashboard/i }),
  ).toBeVisible();
  await expect(governanceTimeline).toBeVisible();

  // CI occasionally renders a stale fallback snapshot on first SSR response.
  // Reload once to force no-store governance fetch under the explicit scenario.
  if (scenario === "main" && (await governanceTimeline.getByText("decision_shaping").count()) === 0) {
    await page.reload();
    await expect(governanceTimeline).toBeVisible();
  }

  return governanceTimeline;
}

test.describe("Mission Control: governance feed frontend E2E", () => {
  test("main path reaches UI from /api/veritas/v1/report/governance", async ({ page }) => {
    const governanceTimeline = await openScenario(page, "main");

    await expect(governanceTimeline.getByText("participation_state:")).toBeVisible();
    await expect(governanceTimeline.getByText("decision_shaping")).toBeVisible();
    await expect(governanceTimeline.getByText("preservation_state:")).toBeVisible();
    await expect(governanceTimeline.getByText("degrading")).toBeVisible();
    await expect(governanceTimeline.getByText("intervention_viability:")).toBeVisible();
    await expect(governanceTimeline.getByText("minimal")).toBeVisible();
    await expect(governanceTimeline.getByText("bind_outcome:")).toBeVisible();
    await expect(governanceTimeline.getByText("ESCALATED")).toBeVisible();
  });

  test("endpoint unavailable path renders fallback safety snapshot without breaking page", async ({ page }) => {
    const governanceTimeline = await openScenario(page, "fallback");

    await expect(governanceTimeline.getByText("participation_state:")).toBeVisible();
    await expect(governanceTimeline.getByText("participatory")).toBeVisible();
    await expect(governanceTimeline.getByText("preservation_state:")).toBeVisible();
    await expect(governanceTimeline.getByText("open")).toBeVisible();
    await expect(governanceTimeline.getByText("intervention_viability:")).toBeVisible();
    await expect(governanceTimeline.getByText("high")).toBeVisible();
    await expect(governanceTimeline.getByText("bind_outcome:")).toBeVisible();
    await expect(governanceTimeline.getByText("BLOCKED")).toBeVisible();
  });
});
