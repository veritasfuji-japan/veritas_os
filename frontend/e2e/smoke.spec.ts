import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("console/audit/governance smoke + a11y", async ({ page }) => {
  await page.route("**/v1/decide", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        decision_status: "rejected",
        chosen: { id: "safe-default" },
        fuji: { status: "rejected", reasons: ["harm_policy"] },
        gate: { status: "rejected" },
        rejection_reason: "harm_policy",
        evidence: [],
        critique: [],
        debate: [],
        alternatives: [],
        options: [],
      }),
    });
  });

  await page.route("**/v1/trust/logs**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [{ request_id: "req-123", stage: "fuji", created_at: "2026-02-12T00:00:00Z" }],
        cursor: "0",
        next_cursor: null,
        limit: 50,
        has_more: false,
      }),
    });
  });

  await page.route("**/v1/trust/req-123", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        request_id: "req-123",
        items: [{ request_id: "req-123", stage: "fuji", created_at: "2026-02-12T00:00:00Z" }],
        count: 1,
        chain_ok: true,
        verification_result: "ok",
      }),
    });
  });

  await page.route("**/v1/governance/policy", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          fuji_enabled: true,
          risk_threshold: 0.55,
          auto_stop_conditions: ["fuji_rejected"],
          log_retention_days: 90,
          audit_intensity: "standard",
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        fuji_enabled: false,
        risk_threshold: 0.8,
        auto_stop_conditions: ["manual_override"],
        log_retention_days: 45,
        audit_intensity: "strict",
      }),
    });
  });

  await page.goto("/console");
  await page.getByPlaceholder("API key").fill("test-key");
  await page.getByPlaceholder("意思決定したい問いを入力").fill("安全拒否を確認");
  await page.getByRole("button", { name: "実行" }).click();
  await expect(page.getByText("fuji/gate")).toBeVisible();
  await expect(page.getByText("rejected")).toBeVisible();

  await page.goto("/audit");
  await page.getByLabel("X-API-Key").fill("test-key");
  await page.getByRole("button", { name: "最新ログを読み込み" }).click();
  await expect(page.getByText("fuji")).toBeVisible();
  await page.getByPlaceholder("request_id").fill("req-123");
  await page.getByRole("button", { name: "検索" }).click();
  await expect(page.getByText(/count: 1/)).toBeVisible();

  await page.goto("/governance");
  await page.getByLabel("X-API-Key").fill("test-key");
  await page.getByRole("button", { name: "現在のpolicyを取得" }).click();
  await page.getByLabel("FUJIルール有効化").uncheck();
  await page.getByRole("button", { name: "policyを更新" }).click();
  await expect(page.getByText(/"audit_intensity": "strict"/)).toBeVisible();

  for (const target of ["/console", "/audit", "/governance"]) {
    await page.goto(target);
    const accessibility = await new AxeBuilder({ page }).analyze();
    expect(accessibility.violations).toEqual([]);
  }
});
