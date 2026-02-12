import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// ============================================================
// Smoke E2E: 3-minute demo flow
// ============================================================

test.describe("Smoke: 3-minute demo flow", () => {
  // 1. /console — render preset buttons and pipeline stages
  test("Console page renders pipeline and presets", async ({ page }) => {
    await page.goto("/console");
    await expect(page.getByText("Decision Console")).toBeVisible();
    await expect(page.getByText("Pipeline Visualizer")).toBeVisible();
    await expect(page.getByText("Evidence")).toBeVisible();
    await expect(page.getByText("FUJI")).toBeVisible();
    await expect(page.getByText("TrustLog")).toBeVisible();

    // Danger presets are visible
    const presetButtons = page.locator("button").filter({ hasText: "..." });
    await expect(presetButtons.first()).toBeVisible();
  });

  // 2. /audit — TrustLog explorer renders
  test("Audit page renders TrustLog explorer", async ({ page }) => {
    await page.goto("/audit");
    await expect(page.getByText("TrustLog Explorer")).toBeVisible();
    await expect(page.getByText("request_id 検索")).toBeVisible();
    await expect(page.getByText("Timeline")).toBeVisible();
    await expect(page.getByPlaceholder("request_id")).toBeVisible();
  });

  // 3. /governance — load governance UI
  test("Governance page renders controls", async ({ page }) => {
    await page.goto("/governance");
    await expect(page.getByText("Governance Control")).toBeVisible();
    await expect(page.getByText("ポリシーを読み込む")).toBeVisible();

    // Connection inputs
    await expect(page.getByLabel("X-API-Key")).toBeVisible();
  });

  // 4. Navigation works across all pages
  test("Navigation sidebar links work", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Command Dashboard")).toBeVisible();

    // Click Console
    await page.getByRole("link", { name: /Decision Console/i }).click();
    await expect(page).toHaveURL(/\/console/);

    // Click Governance
    await page.getByRole("link", { name: /Governance Control/i }).click();
    await expect(page).toHaveURL(/\/governance/);

    // Click Audit
    await page.getByRole("link", { name: /TrustLog Explorer/i }).click();
    await expect(page).toHaveURL(/\/audit/);
  });
});

// ============================================================
// Accessibility (axe) checks for main pages
// ============================================================

test.describe("Accessibility (axe)", () => {
  const pages = [
    { path: "/", name: "Dashboard" },
    { path: "/console", name: "Console" },
    { path: "/governance", name: "Governance" },
    { path: "/audit", name: "Audit" },
  ];

  for (const { path, name } of pages) {
    test(`${name} page passes axe checks`, async ({ page }) => {
      await page.goto(path);
      // Wait for content to render
      await page.waitForLoadState("networkidle");

      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa"])
        // Exclude color-contrast for dark theme (common false positive with design tokens)
        .disableRules(["color-contrast"])
        .analyze();

      expect(results.violations).toEqual([]);
    });
  }
});
