import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// ============================================================
// Smoke E2E: 3-minute demo flow
// ============================================================

test.describe("Smoke: 3-minute demo flow", () => {
  // 1. /console — render preset buttons and pipeline stages
  test("Console page renders pipeline and presets", async ({ page }) => {
    await page.goto("/console");
    // Use heading role to avoid strict-mode clash with the sidebar nav text
    await expect(page.getByRole("heading", { name: "Decision Console" })).toBeVisible();
    await expect(page.getByText("Pipeline Visualizer")).toBeVisible();
    await expect(page.getByText("Evidence")).toBeVisible();
    // Scope to <li> so strict mode won't match the separate "FUJI Gate Status" heading
    await expect(page.locator("li", { hasText: "FUJI" })).toBeVisible();
    // Scope to <li> to avoid matching sidebar's "TrustLog Explorer"
    await expect(page.locator("li", { hasText: "TrustLog" })).toBeVisible();

    // Danger presets are visible
    const presetButtons = page.locator("button").filter({ hasText: "..." });
    await expect(presetButtons.first()).toBeVisible();
  });

  // 2. /audit — TrustLog explorer renders
  test("Audit page renders TrustLog explorer", async ({ page }) => {
    await page.goto("/audit");
    await expect(page.getByRole("heading", { name: "TrustLog Explorer" })).toBeVisible();
    await expect(page.getByRole("heading", { name: /request_id (検索|Search)/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Timeline" })).toBeVisible();
    await expect(page.getByPlaceholder("request_id")).toBeVisible();
  });

  // 3. /governance — load governance UI
  test("Governance page renders controls", async ({ page }) => {
    await page.goto("/governance");
    await expect(page.getByRole("heading", { name: "Governance Control" })).toBeVisible();
    await expect(page.getByRole("button", { name: /(ポリシーを読み込む|Load policy)/ })).toBeVisible();
  });

  // 4. Navigation works across all pages
  test("Navigation sidebar links work", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Command Dashboard" })).toBeVisible();

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
  // Rules excluded from assertions:
  // - color-contrast: design-token colours use CSS custom properties that
  //   axe cannot resolve, producing false positives.
  // - region: Next.js injects internal elements (e.g. route-announcer)
  //   outside landmarks that we cannot control.  All *application* content
  //   is inside proper landmark elements.
  const IGNORED_RULES = new Set(["color-contrast", "region"]);

  const pages = [
    { path: "/", name: "Dashboard" },
    { path: "/console", name: "Console" },
    { path: "/governance", name: "Governance" },
    { path: "/audit", name: "Audit" },
  ];

  for (const { path, name } of pages) {
    test(`${name} page passes axe checks`, async ({ page }) => {
      await page.goto(path);
      // Wait for hydration and client-side rendering to finish
      await page.waitForLoadState("networkidle");
      // Extra settle time for React hydration
      await page.waitForTimeout(500);

      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa"])
        .analyze();

      // Filter results in JS — more reliable than disableRules() which
      // can be ignored by certain axe-core/playwright version combinations.
      const violations = results.violations
        .filter((v) => !IGNORED_RULES.has(v.id))
        .map((v) => ({
          id: v.id,
          impact: v.impact,
          description: v.description,
          nodes: v.nodes.map((n) => n.html.slice(0, 200)),
        }));
      expect(violations).toEqual([]);
    });
  }
});
