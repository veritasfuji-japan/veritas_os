import { test, expect, devices } from "@playwright/test";

test.describe("i18n: language toggle", () => {
  const pages = [
    { path: "/", heading: "Command Dashboard" },
    { path: "/console", heading: "Decision Console" },
    { path: "/governance", heading: "Governance Control" },
    { path: "/audit", heading: "TrustLog Explorer" },
  ];

  for (const { path, heading } of pages) {
    test(`${path} renders heading in both languages`, async ({ page }) => {
      await page.goto(path);
      await expect(
        page.getByRole("heading", { name: heading }),
      ).toBeVisible();

      // Toggle language via localStorage and reload
      await page.evaluate(() => {
        window.localStorage.setItem("veritas_language", "en");
      });
      await page.reload();
      await expect(
        page.getByRole("heading", { name: heading }),
      ).toBeVisible();

      // Switch back to Japanese
      await page.evaluate(() => {
        window.localStorage.setItem("veritas_language", "ja");
      });
      await page.reload();
      await expect(
        page.getByRole("heading", { name: heading }),
      ).toBeVisible();
    });
  }
});

test.describe("Mobile viewport: major flows don't break", () => {
  test.use({ viewport: devices["iPhone 13"].viewport });

  const pages = [
    { path: "/", name: "Dashboard" },
    { path: "/console", name: "Console" },
    { path: "/governance", name: "Governance" },
    { path: "/audit", name: "Audit" },
    { path: "/risk", name: "Risk" },
  ];

  for (const { path, name } of pages) {
    test(`${name} page renders on mobile viewport`, async ({ page }) => {
      await page.goto(path);
      // Page should not overflow or show horizontal scrollbar
      const bodyWidth = await page.evaluate(
        () => document.body.scrollWidth,
      );
      const viewportWidth = await page.evaluate(
        () => window.innerWidth,
      );
      // Allow small tolerance for rounding
      expect(bodyWidth).toBeLessThanOrEqual(viewportWidth + 5);

      // Main content should be visible
      await expect(page.locator("main, [role='main'], .space-y-6").first()).toBeVisible();
    });
  }
});
