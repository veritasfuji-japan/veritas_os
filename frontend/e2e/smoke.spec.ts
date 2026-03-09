import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * Navigates to a path and waits for hydration/network to settle to reduce CI flakes.
 */
async function gotoAndSettle(page: Page, path: string): Promise<void> {
  await page.goto(path, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle");
}

// ============================================================
// Smoke E2E: 3-minute demo flow
// ============================================================

test.describe("Smoke: 3-minute demo flow", () => {
  // 1. /console — render preset buttons and pipeline stages
  test("Console page renders pipeline and presets", async ({ page }) => {
    await gotoAndSettle(page, "/console");
    // Use heading role to avoid strict-mode clash with sidebar/nav duplicate text.
    await expect(
      page.getByRole("heading", { name: /Decision Console|意思決定コンソール/i }),
    ).toBeVisible();
    await expect(
      page.getByText(/Pipeline Operations View|パイプライン運用ビュー/i),
    ).toBeVisible();
    await expect(page.locator("li", { hasText: "Evidence" })).toBeVisible();
    await expect(page.locator("li", { hasText: "FUJI" })).toBeVisible();
    await expect(page.locator("li", { hasText: "TrustLog" })).toBeVisible();

    const presetButtons = page.locator("button").filter({ hasText: "..." });
    const hasDangerPresets = process.env.NEXT_PUBLIC_ENABLE_DANGER_PRESETS === "true";
    if (hasDangerPresets) {
      await expect(presetButtons.first()).toBeVisible();
    } else {
      await expect(presetButtons).toHaveCount(0);
    }
  });

  // 2. /audit — TrustLog explorer renders
  test("Audit page renders TrustLog explorer", async ({ page }) => {
    await gotoAndSettle(page, "/audit");
    await expect(page.getByRole("heading", { name: /TrustLog Explorer/i })).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /request_id (検索|Search)/ }),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: /Timeline/i })).toBeVisible();
    await expect(page.getByPlaceholder("request_id")).toBeVisible();
  });

  // 3. /governance — load governance UI
  test("Governance page renders controls", async ({ page }) => {
    await gotoAndSettle(page, "/governance");
    await expect(
      page.getByRole("heading", { name: /Governance Control|ガバナンス制御/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /(ポリシーを読み込む|Load policy)/ }),
    ).toBeVisible();
  });

  // 4. Navigation works across all pages
  test("Navigation sidebar links work", async ({ page }) => {
    await gotoAndSettle(page, "/");
    await expect(
      page.getByRole("heading", { name: /Command Dashboard|コマンドダッシュボード/i }),
    ).toBeVisible();

    // Click Console
    await page.getByRole("link", { name: /Decision Console|意思決定コンソール/i }).click();
    await expect(page).toHaveURL(/\/console/);

    // Click Governance
    await page.getByRole("link", { name: /Governance Control|ガバナンス制御/i }).click();
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
  //   outside landmarks that we cannot control.
  const IGNORED_RULES = new Set(["color-contrast", "region"]);

  const pages = [
    { path: "/", name: "Dashboard" },
    { path: "/console", name: "Console" },
    { path: "/governance", name: "Governance" },
    { path: "/audit", name: "Audit" },
  ];

  for (const { path, name } of pages) {
    test(`${name} page passes axe checks`, async ({ page }) => {
      await gotoAndSettle(page, path);
      await page.waitForTimeout(500);

      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa"])
        .analyze();

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
