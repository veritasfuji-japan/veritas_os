import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

interface AxeViolation {
  id: string;
  impact?: string | null;
  description: string;
}

/**
 * Fail only on major a11y issues so smoke remains stable while still enforcing quality.
 */
function assertNoMajorA11yViolations(violations: AxeViolation[]): void {
  const major = violations.filter((item) => item.impact === "critical" || item.impact === "serious");
  expect(major, JSON.stringify(major, null, 2)).toEqual([]);
}

function routeGovernanceApi(page: import("@playwright/test").Page): Promise<void> {
  let policy = {
    fuji_enabled: true,
    risk_threshold: 0.65,
    auto_stop_conditions: ["critical_fuji_violation", "trust_chain_break"],
    log_retention_days: 180,
    audit_intensity: "standard",
  };

  return page.route("**/v1/**", async (route) => {
    const url = route.request().url();
    const method = route.request().method();

    if (url.includes("/v1/decide") && method === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ decision_status: "allow", fuji: { status: "allow" } }),
      });
      return;
    }

    if (url.includes("/v1/trust/logs")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [{ request_id: "req-govern-1", stage: "fuji", created_at: "2026-02-12T00:00:00Z" }],
          cursor: null,
          next_cursor: null,
          limit: 50,
          has_more: false,
        }),
      });
      return;
    }

    if (url.includes("/v1/trust/req-govern-1")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          request_id: "req-govern-1",
          count: 1,
          chain_ok: true,
          verification_result: "ok",
          items: [{ request_id: "req-govern-1", stage: "fuji", created_at: "2026-02-12T00:00:00Z" }],
        }),
      });
      return;
    }

    if (url.includes("/v1/governance/policy") && method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, policy }),
      });
      return;
    }

    if (url.includes("/v1/governance/policy") && method === "PUT") {
      const before = policy;
      const payload = route.request().postDataJSON() as { policy: typeof policy };
      policy = payload.policy;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, before, policy }),
      });
      return;
    }

    await route.fulfill({ status: 404, body: "not mocked" });
  });
}

test("console/audit/governance smoke and a11y", async ({ page }) => {
  await routeGovernanceApi(page);

  await page.goto("/console");
  await page.getByPlaceholder("API key").fill("test-key");
  await page.getByRole("button", { name: "実行" }).click();
  await expect(page.getByText("FUJI")).toBeVisible();

  const consoleA11y = await new AxeBuilder({ page }).analyze();
  assertNoMajorA11yViolations(consoleA11y.violations as AxeViolation[]);

  await page.goto("/audit");
  await page.getByLabel("X-API-Key").fill("test-key");
  await page.getByRole("button", { name: "最新ログを読み込み" }).click();
  await page.getByPlaceholder("request_id").fill("req-govern-1");
  await page.getByRole("button", { name: "検索" }).click();
  await expect(page.getByText(/chain_ok: true/)).toBeVisible();

  const auditA11y = await new AxeBuilder({ page }).analyze();
  assertNoMajorA11yViolations(auditA11y.violations as AxeViolation[]);

  await page.goto("/governance");
  await page.getByLabel("X-API-Key").fill("test-key");
  await page.getByRole("button", { name: "現在ポリシー取得" }).click();
  await page.getByLabel("FUJI rule switch").selectOption("disabled");
  await page.getByLabel("Log retention days").fill("90");
  await page.getByLabel("Audit intensity").selectOption("strict");
  await page.getByRole("button", { name: "ポリシー更新" }).click();
  await expect(page.getByText(/"audit_intensity": "strict"/)).toBeVisible();

  const governanceA11y = await new AxeBuilder({ page }).analyze();
  assertNoMajorA11yViolations(governanceA11y.violations as AxeViolation[]);
});
