import { test, expect } from "@playwright/test";

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
      page.getByRole("heading", { name: /(コマンドダッシュボード|Command Dashboard)/ }),
    ).toBeVisible();
    await expect(page.getByText("participation_state:", { exact: true })).toBeVisible();
    await expect(page.getByText("decision_shaping", { exact: true })).toBeVisible();
    await expect(page.getByText("preservation_state:", { exact: true })).toBeVisible();
    await expect(page.getByText("degrading", { exact: true })).toBeVisible();
    await expect(page.getByText("intervention_viability:", { exact: true })).toBeVisible();
    await expect(page.getByText("minimal", { exact: true })).toBeVisible();
    await expect(page.getByText("bind_outcome:", { exact: true })).toBeVisible();
    await expect(page.getByText("ESCALATED", { exact: true })).toBeVisible();

    await expect(page.getByText("BLOCKED", { exact: true })).toHaveCount(0);
  });

  test("endpoint unavailable path renders fallback safety snapshot without breaking page", async ({ page }) => {
    await page.route(GOVERNANCE_ENDPOINT, async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ error: "service_unavailable" }),
      });
    });

    await page.goto("/");

    await expect(
      page.getByRole("heading", { name: /(コマンドダッシュボード|Command Dashboard)/ }),
    ).toBeVisible();
    await expect(page.getByText("participation_state:", { exact: true })).toBeVisible();
    await expect(page.getByText("participatory", { exact: true })).toBeVisible();
    await expect(page.getByText("preservation_state:", { exact: true })).toBeVisible();
    await expect(page.getByText("open", { exact: true })).toBeVisible();
    await expect(page.getByText("intervention_viability:", { exact: true })).toBeVisible();
    await expect(page.getByText("high", { exact: true })).toBeVisible();
    await expect(page.getByText("bind_outcome:", { exact: true })).toBeVisible();
    await expect(page.getByText("BLOCKED", { exact: true })).toBeVisible();

    await expect(page.getByText("decision_shaping", { exact: true })).toHaveCount(0);
    await expect(page.getByText("ESCALATED", { exact: true })).toHaveCount(0);
  });
});
