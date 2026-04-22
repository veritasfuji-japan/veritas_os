import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
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

import { PolicyBundlePromotionFlow } from "./PolicyBundlePromotionFlow";

function fillRequiredFields(): void {
  fireEvent.change(screen.getByLabelText("bundle_id"), { target: { value: "bundle-001" } });
  fireEvent.change(screen.getByLabelText("decision_id"), { target: { value: "decision-001" } });
  fireEvent.change(screen.getByLabelText("request_id"), { target: { value: "request-001" } });
  fireEvent.change(screen.getByLabelText("policy_snapshot_id"), { target: { value: "snapshot-001" } });
  fireEvent.change(screen.getByLabelText("decision_hash"), { target: { value: "hash-001" } });
}

describe("PolicyBundlePromotionFlow", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("renders compact promotion form", () => {
    render(<PolicyBundlePromotionFlow canOperate />);
    expect(screen.getByText("Policy Bundle Promotion")).toBeInTheDocument();
    expect(screen.getByText(/Bind-oriented promotion cockpit/i)).toBeInTheDocument();
    expect(screen.getByLabelText("bundle_id")).toBeInTheDocument();
    expect(screen.getByLabelText("bundle_dir_name")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "promote bundle" })).toBeInTheDocument();
  });

  it("validates exactly one selector", async () => {
    render(<PolicyBundlePromotionFlow canOperate />);
    fireEvent.change(screen.getByLabelText("bundle_id"), { target: { value: "bundle-001" } });
    fireEvent.change(screen.getByLabelText("bundle_dir_name"), { target: { value: "dir-001" } });

    fireEvent.click(screen.getByRole("button", { name: "promote bundle" }));

    expect(mockFetch).not.toHaveBeenCalled();
    expect(await screen.findByText("bundle_id と bundle_dir_name は同時に指定できません。"))
      .toBeInTheDocument();
  });

  it("sends promote request with expected payload shape", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        ok: true,
        bind_outcome: "COMMITTED",
        bind_receipt_id: "br-001",
        execution_intent_id: "ei-001",
      }),
    });

    render(<PolicyBundlePromotionFlow canOperate />);
    fillRequiredFields();
    fireEvent.change(screen.getByLabelText("approval_context"), { target: { value: '{"ticket":"GOV-1"}' } });

    fireEvent.click(screen.getByRole("button", { name: "promote bundle" }));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/veritas/v1/governance/policy-bundles/promote",
        expect.objectContaining({ method: "POST" }),
      );
    });

    const requestInit = mockFetch.mock.calls[0][1] as { body: string };
    expect(JSON.parse(requestInit.body)).toEqual({
      bundle_id: "bundle-001",
      decision_id: "decision-001",
      request_id: "request-001",
      policy_snapshot_id: "snapshot-001",
      decision_hash: "hash-001",
      approval_context: { ticket: "GOV-1" },
    });
  });

  it("renders canonical COMMITTED outcome with success variant", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        ok: true,
        bind_outcome: "COMMITTED",
        bind_receipt_id: "br-777",
        execution_intent_id: "ei-777",
      }),
    });

    render(<PolicyBundlePromotionFlow canOperate />);
    fillRequiredFields();
    fireEvent.click(screen.getByRole("button", { name: "promote bundle" }));

    expect(await screen.findByText("Promotion Result")).toBeInTheDocument();
    expect(screen.getByTestId("status-badge")).toHaveTextContent("COMMITTED");
    expect(screen.getByTestId("status-badge")).toHaveAttribute("data-variant", "success");
  });

  it.each([
    ["BLOCKED", "warning"],
    ["ROLLED_BACK", "warning"],
    ["ESCALATED", "danger"],
    ["APPLY_FAILED", "danger"],
    ["SNAPSHOT_FAILED", "danger"],
    ["PRECONDITION_FAILED", "warning"],
  ])("renders representative canonical outcome %s", async (outcome, variant) => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        ok: true,
        bind_outcome: outcome,
        bind_failure_reason: "reason",
        bind_reason_code: "CODE",
      }),
    });

    render(<PolicyBundlePromotionFlow canOperate />);
    fillRequiredFields();
    fireEvent.click(screen.getByRole("button", { name: "promote bundle" }));

    await screen.findByText("Promotion Result");
    expect(screen.getByTestId("status-badge")).toHaveTextContent(outcome);
    expect(screen.getByTestId("status-badge")).toHaveAttribute("data-variant", variant);
  });

  it("renders UNKNOWN outcome with muted variant when bind_outcome is non-canonical", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        ok: true,
        bind_outcome: "done",
      }),
    });

    render(<PolicyBundlePromotionFlow canOperate />);
    fillRequiredFields();
    fireEvent.click(screen.getByRole("button", { name: "promote bundle" }));

    expect(await screen.findByTestId("status-badge")).toHaveTextContent("UNKNOWN");
    expect(screen.getByTestId("status-badge")).toHaveAttribute("data-variant", "muted");
  });

  it("loads bind receipt detail and renders compact bind breakdown", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ok: true,
          bind_outcome: "BLOCKED",
          bind_receipt_id: "br-100",
          execution_intent_id: "ei-100",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ok: true,
          bind_receipt: {
            bind_receipt_id: "br-100",
            decision_id: "decision-100",
            execution_intent_id: "ei-100",
            policy_snapshot_id: "snapshot-100",
            final_outcome: "BLOCKED",
            authority_check_result: { passed: true },
            constraint_check_result: { passed: false },
            drift_check_result: { result: "ok" },
            risk_check_result: { result: "deny" },
          },
        }),
      });

    render(<PolicyBundlePromotionFlow canOperate />);
    fillRequiredFields();
    fireEvent.click(screen.getByRole("button", { name: "promote bundle" }));

    const loadButton = await screen.findByRole("button", { name: "load bind receipt detail" });
    fireEvent.click(loadButton);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenNthCalledWith(
        2,
        "/api/veritas/v1/governance/bind-receipts/br-100",
      );
    });

    expect(await screen.findByText("bind receipt detail loaded")).toBeInTheDocument();
    expect(screen.getByText(/^authority:/)).toBeInTheDocument();
    expect(screen.getByText(/^constraints:/)).toBeInTheDocument();
    expect(screen.getByText(/^drift:/)).toBeInTheDocument();
    expect(screen.getByText(/^risk:/)).toBeInTheDocument();
    expect(screen.getAllByText("PASS")).toHaveLength(2);
    expect(screen.getAllByText("FAIL")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "decision-100" })).toHaveAttribute("href", "/audit?decision_id=decision-100");
    expect(screen.getByRole("link", { name: "ei-100" })).toHaveAttribute("href", "/audit?cross=ei-100");
    expect(screen.getByRole("link", { name: "snapshot-100" })).toHaveAttribute("href", "/audit?cross=snapshot-100");
    expect(screen.getByRole("link", { name: "bind_receipt/br-100" })).toHaveAttribute("href", "/audit?bind_receipt_id=br-100");
    expect(screen.getByText(/failure triage guidance/i)).toBeInTheDocument();
    expect(screen.getByText(/Policy gate triage/i)).toBeInTheDocument();
  });

  it("falls back to bind_receipt.final_outcome when bind_outcome is absent", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ok: true,
          bind_outcome: "COMMITTED",
          bind_receipt_id: "br-101",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ok: true,
          bind_receipt: {
            final_outcome: "ESCALATED",
          },
        }),
      });

    render(<PolicyBundlePromotionFlow canOperate />);
    fillRequiredFields();
    fireEvent.click(screen.getByRole("button", { name: "promote bundle" }));
    fireEvent.click(await screen.findByRole("button", { name: "load bind receipt detail" }));

    expect(await screen.findByText("bind receipt detail loaded")).toBeInTheDocument();
  });

  it("treats malformed bind check payloads as UNKNOWN", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ok: true,
          bind_outcome: "BLOCKED",
          bind_receipt_id: "br-102",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ok: true,
          bind_receipt: {
            authority_check_result: "pass",
            constraint_check_result: { unexpected: true },
          },
        }),
      });

    render(<PolicyBundlePromotionFlow canOperate />);
    fillRequiredFields();
    fireEvent.click(screen.getByRole("button", { name: "promote bundle" }));
    fireEvent.click(await screen.findByRole("button", { name: "load bind receipt detail" }));

    await screen.findByText("bind receipt detail loaded");
    expect(screen.getAllByText("UNKNOWN").length).toBeGreaterThanOrEqual(2);
  });

  it("normalizes legacy success outcome into canonical COMMITTED", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        ok: true,
        bind_outcome: "success",
      }),
    });

    render(<PolicyBundlePromotionFlow canOperate />);
    fillRequiredFields();
    fireEvent.click(screen.getByRole("button", { name: "promote bundle" }));

    expect(await screen.findByTestId("status-badge")).toHaveTextContent("COMMITTED");
    expect(screen.getByTestId("status-badge")).toHaveAttribute("data-variant", "success");
    expect(screen.getByText(/No triage required/i)).toBeInTheDocument();
  });

  it("shows escalation triage guidance for ESCALATED outcome", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        ok: true,
        bind_outcome: "ESCALATED",
      }),
    });

    render(<PolicyBundlePromotionFlow canOperate />);
    fillRequiredFields();
    fireEvent.click(screen.getByRole("button", { name: "promote bundle" }));

    expect(await screen.findByText(/Escalation handoff/i)).toBeInTheDocument();
  });

  it("handles promote endpoint error response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ ok: false, error: "backend failure" }),
    });

    render(<PolicyBundlePromotionFlow canOperate />);
    fillRequiredFields();
    fireEvent.click(screen.getByRole("button", { name: "promote bundle" }));

    expect(await screen.findByText("backend failure")).toBeInTheDocument();
  });

  it("handles malformed promote response payload", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ ok: "yes" }),
    });

    render(<PolicyBundlePromotionFlow canOperate />);
    fillRequiredFields();
    fireEvent.click(screen.getByRole("button", { name: "promote bundle" }));

    expect(await screen.findByText("promotion レスポンスの形式が不正です。")).toBeInTheDocument();
  });
});
