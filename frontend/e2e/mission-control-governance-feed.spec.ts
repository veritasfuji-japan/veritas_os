import { expect, test } from "@playwright/test";

const GOVERNANCE_ENDPOINT = "**/api/veritas/v1/report/governance";

test.describe("Mission Control: governance feed frontend E2E", () => {
  test("main path reaches UI from /api/veritas/v1/report/governance", async ({ page }) => {
    await page.route(GOVERNANCE_ENDPOINT, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          governance_layer_snapshot: {
            participation_state: "decision_shaping",
            preservation_state: "degrading",
            intervention_viability: "minimal",
            bind_outcome: "ESCALATED",
          },
        }),
      });
    });

    await page.goto("/");

    await expect(
      page.getByRole("heading", { name: /コマンドダッシュボード|Command Dashboard/i }),
    ).toBeVisible();

    await expect(page.getByText("participation_state:")).toBeVisible();
    await expect(page.getByText("decision_shaping")).toBeVisible();

    await expect(page.getByText("preservation_state:")).toBeVisible();
    await expect(page.getByText(/degrading/)).toBeVisible();

    await expect(page.getByText("intervention_viability:")).toBeVisible();
    await expect(page.getByText("minimal")).toBeVisible();

    await expect(page.getByText("bind_outcome:")).toBeVisible();
    await expect(page.getByText("ESCALATED")).toBeVisible();
  });

  test("endpoint unavailable path renders fallback safety snapshot without breaking page", async ({ page }) => {
    await page.route(GOVERNANCE_ENDPOINT, async (route) => {
      await route.abort("failed");
    });

    await page.goto("/");

    await expect(
      page.getByRole("heading", { name: /コマンドダッシュボード|Command Dashboard/i }),
    ).toBeVisible();

    await expect(page.getByText("participation_state:")).toBeVisible();
    await expect(page.getByText("participatory")).toBeVisible();

    await expect(page.getByText("preservation_state:")).toBeVisible();
    await expect(page.getByText(/open/)).toBeVisible();

    await expect(page.getByText("intervention_viability:")).toBeVisible();
    await expect(page.getByText("high")).toBeVisible();

    await expect(page.getByText("bind_outcome:")).toBeVisible();
    await expect(page.getByText("BLOCKED")).toBeVisible();
  });
});
