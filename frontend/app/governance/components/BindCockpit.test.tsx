import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("@veritas/design-system", () => ({
  Card: ({ children, title }: { children: React.ReactNode; title?: string }) => (
    <div>
      {title ? <h3>{title}</h3> : null}
      {children}
    </div>
  ),
}));

vi.mock("../../../components/ui", () => ({
  StatusBadge: ({ label, variant }: { label: string; variant: string }) => (
    <span data-testid="status-badge" data-variant={variant}>{label}</span>
  ),
}));

const mockFetch = vi.fn();
vi.mock("../../../lib/api-client", () => ({
  veritasFetch: (...args: unknown[]) => mockFetch(...args),
}));

import { BindCockpit } from "./BindCockpit";

const LIST_PAYLOAD = {
  ok: true,
  count: 2,
  returned_count: 2,
  has_more: false,
  next_cursor: null,
  sort: "newest",
  limit: 50,
  applied_filters: {},
  total_count: 2,
  target_catalog: [
    {
      target_path: "/v1/governance/policy",
      target_type: "governance_policy",
      target_path_type: "governance_policy_update",
      label: "governance policy update",
      operator_surface: "governance",
      relevant_ui_href: "/governance",
      supports_filtering: true,
    },
    {
      target_path: "/v1/governance/policy-bundles/promote",
      target_type: "policy_bundle",
      target_path_type: "policy_bundle_promotion",
      label: "policy bundle promotion",
      operator_surface: "governance",
      relevant_ui_href: "/governance",
      supports_filtering: true,
    },
    {
      target_path: "/v1/compliance/config",
      target_type: "compliance_config",
      target_path_type: "compliance_config_update",
      label: "compliance config update",
      operator_surface: "compliance",
      relevant_ui_href: "/system",
      supports_filtering: true,
    },
  ],
  items: [
    {
      bind_receipt_id: "br-committed",
      target_path: "/v1/governance/policy",
      target_path_type: "governance_policy_update",
      target_label: "governance policy update canonical",
      relevant_ui_href: "/governance/policy",
      operator_surface: "governance",
      final_outcome: "COMMITTED",
      bind_reason_code: "OK",
      decision_id: "decision-1",
      execution_intent_id: "exec-1",
      occurred_at: "2026-04-22T10:00:00Z",
    },
    {
      bind_receipt_id: "br-blocked",
      target_path: "/v1/compliance/config",
      target_path_type: "compliance_config_update",
      target_label: "compliance config update",
      relevant_ui_href: "/system",
      final_outcome: "BLOCKED",
      bind_reason_code: "POLICY_DENY",
      decision_id: "decision-2",
      execution_intent_id: "exec-2",
      occurred_at: "2026-04-22T11:00:00Z",
    },
  ],
};

const DETAIL_PAYLOAD = {
  ok: true,
  bind_receipt: {
    bind_receipt_id: "br-blocked",
    target_path: "/v1/compliance/config",
    target_path_type: "compliance_config_update",
    target_label: "compliance config update",
    relevant_ui_href: "/system",
    final_outcome: "BLOCKED",
    bind_failure_reason: "policy denied",
    bind_reason_code: "POLICY_DENY",
    decision_id: "decision-2",
    execution_intent_id: "exec-2",
    authority_check_result: { passed: true },
    constraint_check_result: { passed: false },
    drift_check_result: { result: "ok" },
    risk_check_result: { result: "deny" },
    action_contract_id: "ac-9",
    authority_evidence_id: "ae-9",
    authority_evidence_hash: "hash-9",
    authority_validation_status: "invalid",
    commit_boundary_result: "block",
    failed_predicates: [{ predicate_id: "p-fail" }],
    stale_predicates: [{ predicate_id: "p-stale" }],
    missing_predicates: [{ predicate_id: "p-missing" }],
    refusal_basis: ["authority_indeterminate"],
    escalation_basis: ["manual_review_required"],
    irreversibility_boundary_id: "ib-9",
  },
};

describe("BindCockpit", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({ ok: true, count: 0, returned_count: 0, has_more: false, next_cursor: null, sort: "newest", limit: 50, applied_filters: {}, total_count: 0, items: [] }) });
  });

  it("renders empty state when no receipts", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, count: 0, returned_count: 0, has_more: false, next_cursor: null, sort: "newest", limit: 50, applied_filters: {}, total_count: 0, items: [] }) });
    render(<BindCockpit />);
    expect(await screen.findByText(/No bind receipts matched filters/i)).toBeInTheDocument();
  });

  it("reflects filter state into server-side bind receipt query", async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => LIST_PAYLOAD })
      .mockResolvedValue({ ok: true, json: async () => ({ ok: true, count: 1, returned_count: 1, has_more: false, next_cursor: null, sort: "newest", limit: 50, applied_filters: {}, total_count: 1, items: [LIST_PAYLOAD.items[1]] }) });

    render(<BindCockpit />);
    await screen.findAllByText("br-blocked");
    expect(screen.getByRole("option", { name: "compliance config update" })).toBeInTheDocument();
    expect(screen.getByText("governance policy update canonical")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("bind-path-type"), { target: { value: "compliance_config_update" } });
    fireEvent.change(screen.getByLabelText("bind-outcome"), { target: { value: "BLOCKED" } });
    fireEvent.change(screen.getByLabelText("bind-reason-code"), { target: { value: "POLICY" } });
    fireEvent.change(screen.getByLabelText("bind-lineage-search"), { target: { value: "decision-2" } });
    fireEvent.click(screen.getByLabelText("failed-only"));
    fireEvent.click(screen.getByLabelText("recent-only"));

    await waitFor(() => {
      const calledUrls = mockFetch.mock.calls.map((call) => String(call[0]));
      expect(calledUrls.some((url) => url.includes("target_path=%2Fv1%2Fcompliance%2Fconfig"))).toBe(true);
      expect(calledUrls.some((url) => url.includes("outcome=BLOCKED"))).toBe(true);
      expect(calledUrls.some((url) => url.includes("reason_code=POLICY"))).toBe(true);
      expect(calledUrls.some((url) => url.includes("lineage_query=decision-2"))).toBe(true);
      expect(calledUrls.some((url) => url.includes("failed_only=true"))).toBe(true);
      expect(calledUrls.some((url) => url.includes("recent_only=true"))).toBe(true);
      expect(calledUrls.some((url) => url.includes("sort=newest"))).toBe(true);
      expect(calledUrls.some((url) => url.includes("limit=50"))).toBe(true);
    });
  });


  it("renders no match state for filtered server response", async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => LIST_PAYLOAD })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, count: 0, returned_count: 0, has_more: false, next_cursor: null, sort: "newest", limit: 50, applied_filters: {}, total_count: 0, items: [] }) });

    render(<BindCockpit />);
    await screen.findAllByText("br-blocked");

    fireEvent.change(screen.getByLabelText("bind-outcome"), { target: { value: "SNAPSHOT_FAILED" } });

    expect(await screen.findByText(/No bind receipts matched filters/i)).toBeInTheDocument();
  });

  

  it("supports load more and export parity with current filters", async () => {
    const firstPage = {
      ok: true,
      count: 1,
      returned_count: 1,
      has_more: true,
      next_cursor: "cursor-1",
      sort: "newest",
      limit: 50,
      applied_filters: {},
      total_count: 2,
      items: [LIST_PAYLOAD.items[0]],
    };
    const secondPage = {
      ok: true,
      count: 1,
      returned_count: 1,
      has_more: false,
      next_cursor: null,
      sort: "newest",
      limit: 50,
      applied_filters: {},
      total_count: 2,
      items: [LIST_PAYLOAD.items[1]],
    };

    mockFetch.mockImplementation((url: string) => {
      if (url.includes("/bind-receipts/export")) {
        return Promise.resolve({ ok: true, json: async () => ({ ok: true, items: [] }) });
      }
      if (url.includes("/bind-receipts/br-")) {
        return Promise.resolve({ ok: true, json: async () => DETAIL_PAYLOAD });
      }
      if (url.includes("cursor=cursor-1")) {
        return Promise.resolve({ ok: true, json: async () => secondPage });
      }
      return Promise.resolve({ ok: true, json: async () => firstPage });
    });

    render(<BindCockpit />);
    await screen.findAllByText("br-committed");

    expect(screen.getByText(/has more pages/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /load more receipts/i }));

    await screen.findAllByText("br-blocked");
    expect(screen.getByText(/no more pages/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("bind-outcome"), { target: { value: "BLOCKED" } });

    await waitFor(() => {
      const exportLink = screen.getByRole("link", { name: /export current filtered set/i });
      expect(exportLink.getAttribute("href")).toContain("/api/veritas/v1/governance/bind-receipts/export?");
      expect(exportLink.getAttribute("href")).toContain("outcome=BLOCKED");
    });

    const calledUrls = mockFetch.mock.calls.map((call) => String(call[0]));
    expect(calledUrls.some((url) => url.includes("cursor=cursor-1"))).toBe(true);
  });

  it("supports drill-down and related lineage navigation", async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => LIST_PAYLOAD })
      .mockResolvedValueOnce({ ok: true, json: async () => DETAIL_PAYLOAD })
      .mockResolvedValueOnce({ ok: true, json: async () => DETAIL_PAYLOAD });

    render(<BindCockpit />);
    await screen.findAllByText("br-blocked");

    const blockedDecision = await screen.findByText("decision-2");
    fireEvent.click(blockedDecision.closest("tr") as HTMLElement);

    await waitFor(() => {
      const calledUrls = mockFetch.mock.calls.map((call) => String(call[0]));
      expect(calledUrls.some((url) => url.includes("/api/veritas/v1/governance/bind-receipts/br-blocked"))).toBe(true);
    });

    expect(await screen.findByText("Receipt Drill-down")).toBeInTheDocument();
    expect(screen.getByText("Action Contract")).toBeInTheDocument();
    expect(screen.getByText("Authority Evidence")).toBeInTheDocument();
    expect(screen.getByText("Runtime Authority")).toBeInTheDocument();
    expect(screen.getByText("Predicate Results")).toBeInTheDocument();
    expect(screen.getByText("Commit Boundary Result")).toBeInTheDocument();
    expect(screen.getByText("Refusal Basis")).toBeInTheDocument();
    expect(screen.getByText("Escalation Basis")).toBeInTheDocument();
    expect(screen.getByText("Irreversibility Boundary")).toBeInTheDocument();
    expect(screen.getByText(/Expanded governance detail/i)).toBeInTheDocument();
    expect(screen.getByText(/authority_evidence_hash: hash-9/i)).toBeInTheDocument();
    expect(screen.getByText(/Next operator step/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "related decision" })).toHaveAttribute("href", "/audit?decision_id=decision-2");
    expect(screen.getByRole("link", { name: "related execution intent" })).toHaveAttribute("href", "/audit?cross=exec-2");
    expect(screen.getByRole("link", { name: "related bind receipt" })).toHaveAttribute("href", "/audit?bind_receipt_id=br-blocked");
    expect(screen.getByRole("link", { name: "relevant governance/compliance surface" })).toHaveAttribute("href", "/system");
  });

  it("surfaces blocked/escalated queue with direct reason inspection action", async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => LIST_PAYLOAD })
      .mockResolvedValueOnce({ ok: true, json: async () => DETAIL_PAYLOAD })
      .mockResolvedValueOnce({ ok: true, json: async () => DETAIL_PAYLOAD });

    render(<BindCockpit />);
    expect(await screen.findByText("Blocked / Escalated queue")).toBeInTheDocument();
    expect(screen.getByText("policy denied")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "inspect blocked/escalated reason" }));

    await waitFor(() => {
      const calledUrls = mockFetch.mock.calls.map((call) => String(call[0]));
      expect(calledUrls).toContain("/api/veritas/v1/governance/bind-receipts/br-blocked");
    });
    expect(screen.getByText("Next operator step")).toBeInTheDocument();
  });

  it("derives minimal filter catalog from receipt-level canonical fields when target_catalog is absent", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ...LIST_PAYLOAD,
          target_catalog: [],
        }),
      })
      .mockResolvedValue({ ok: true, json: async () => ({ ok: true, count: 0, returned_count: 0, has_more: false, next_cursor: null, sort: "newest", limit: 50, applied_filters: {}, total_count: 0, target_catalog: [], items: [] }) });

    render(<BindCockpit />);
    await screen.findAllByText("br-blocked");
    expect(screen.getByRole("option", { name: "compliance config update" })).toBeInTheDocument();
  });
});
