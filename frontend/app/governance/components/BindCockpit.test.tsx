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
  items: [
    {
      bind_receipt_id: "br-committed",
      target_path: "/v1/governance/policy",
      final_outcome: "COMMITTED",
      bind_reason_code: "OK",
      decision_id: "decision-1",
      execution_intent_id: "exec-1",
      occurred_at: "2026-04-22T10:00:00Z",
    },
    {
      bind_receipt_id: "br-blocked",
      target_path: "/v1/compliance/config",
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
    final_outcome: "BLOCKED",
    bind_failure_reason: "policy denied",
    bind_reason_code: "POLICY_DENY",
    decision_id: "decision-2",
    execution_intent_id: "exec-2",
    authority_check_result: { passed: true },
    constraint_check_result: { passed: false },
    drift_check_result: { result: "ok" },
    risk_check_result: { result: "deny" },
  },
};

describe("BindCockpit", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({ ok: true, items: [] }) });
  });

  it("renders empty state when no receipts", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, items: [] }) });
    render(<BindCockpit />);
    expect(await screen.findByText(/No bind receipts matched filters/i)).toBeInTheDocument();
  });

  it("reflects filter state into server-side bind receipt query", async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => LIST_PAYLOAD })
      .mockResolvedValue({ ok: true, json: async () => ({ ok: true, items: [LIST_PAYLOAD.items[1]] }) });

    render(<BindCockpit />);
    await screen.findByText("br-blocked");

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
      expect(calledUrls.some((url) => url.includes("limit=200"))).toBe(true);
    });
  });


  it("renders no match state for filtered server response", async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => LIST_PAYLOAD })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, items: [] }) });

    render(<BindCockpit />);
    await screen.findByText("br-blocked");

    fireEvent.change(screen.getByLabelText("bind-outcome"), { target: { value: "SNAPSHOT_FAILED" } });

    expect(await screen.findByText(/No bind receipts matched filters/i)).toBeInTheDocument();
  });

  it("supports drill-down and related lineage navigation", async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => LIST_PAYLOAD })
      .mockResolvedValueOnce({ ok: true, json: async () => DETAIL_PAYLOAD })
      .mockResolvedValueOnce({ ok: true, json: async () => DETAIL_PAYLOAD });

    render(<BindCockpit />);
    await screen.findByText("br-blocked");

    fireEvent.click(screen.getByText("br-blocked"));

    await waitFor(() => {
      const calledUrls = mockFetch.mock.calls.map((call) => String(call[0]));
      expect(calledUrls).toContain("/api/veritas/v1/governance/bind-receipts/br-blocked");
    });

    expect(await screen.findByText("Receipt Drill-down")).toBeInTheDocument();
    expect(screen.getByText(/Next operator step/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "related decision" })).toHaveAttribute("href", "/audit?decision_id=decision-2");
    expect(screen.getByRole("link", { name: "related execution intent" })).toHaveAttribute("href", "/audit?cross=exec-2");
    expect(screen.getByRole("link", { name: "related bind receipt" })).toHaveAttribute("href", "/audit?bind_receipt_id=br-blocked");
  });
});
