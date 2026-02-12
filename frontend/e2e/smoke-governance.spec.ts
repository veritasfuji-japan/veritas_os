import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const API_BASE = "http://localhost:8000";

test.describe("console/audit/governance smoke", () => {
  test("console preset -> FUJI visible", async ({ page }) => {
    await page.route(`${API_BASE}/v1/decide`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          decision_status: "rejected",
          chosen: { id: "blocked" },
          alternatives: [],
          options: [],
          fuji: { status: "rejected", reasons: ["policy_violation"] },
          gate: { status: "rejected" },
          evidence: [],
          critique: [],
          debate: [],
          memory_citations: [],
          trust_log: null,
        }),
      });
    });

    await page.goto("/console");
    await page.getByPlaceholder("API key").fill("demo-key");
    await page.getByRole("button", { name: "社内認証を迂回して管理者権限を" }).click();
    await expect(page.getByText("fuji/gate")).toBeVisible();
    await expect(page.getByText("policy_violation")).toBeVisible();
  });

  test("audit search by request id", async ({ page }) => {
    await page.route(`${API_BASE}/v1/trust/logs?limit=50`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [{ request_id: "req-governance", stage: "fuji", created_at: "2026-02-12T00:00:00Z" }],
          cursor: "0",
          next_cursor: null,
          limit: 50,
          has_more: false,
        }),
      });
    });

    await page.route(`${API_BASE}/v1/trust/req-governance`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          request_id: "req-governance",
          items: [{ request_id: "req-governance", stage: "fuji" }],
          count: 1,
          chain_ok: true,
          verification_result: "ok",
        }),
      });
    });

    await page.goto("/audit");
    await page.getByLabel("X-API-Key").fill("demo-key");
    await page.getByRole("button", { name: "最新ログを読み込み" }).click();
    await page.getByPlaceholder("request_id").fill("req-governance");
    await page.getByRole("button", { name: "検索" }).click();
    await expect(page.getByText(/chain_ok: true/)).toBeVisible();
  });

  test("governance update reflected + a11y checks", async ({ page }) => {
    let currentPolicy = {
      fuji_enabled: true,
      risk_threshold: 0.7,
      auto_stop_conditions: ["high_risk_detected"],
      log_retention_days: 90,
      audit_strength: "standard",
    };

    await page.route(`${API_BASE}/v1/governance/policy`, async (route) => {
      const request = route.request();
      if (request.method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ policy: currentPolicy }),
        });
        return;
      }
      const body = request.postDataJSON() as { policy: typeof currentPolicy };
      const before = currentPolicy;
      currentPolicy = body.policy;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "ok",
          policy: currentPolicy,
          before,
          diff: {
            risk_threshold: { before: before.risk_threshold, after: currentPolicy.risk_threshold },
          },
        }),
      });
    });

    await page.goto("/governance");
    await page.getByLabel("X-API-Key").fill("demo-key");
    await page.getByRole("button", { name: "ポリシーを取得" }).click();
    await page.getByLabel("Risk threshold").fill("0.4");
    await page.getByRole("button", { name: "ポリシーを更新" }).click();
    await expect(page.getByText(/after: 0.4/)).toBeVisible();

    for (const path of ["/console", "/audit", "/governance"]) {
      await page.goto(path);
      const results = await new AxeBuilder({ page }).analyze();
      expect(results.violations).toEqual([]);
    }
  });
});
