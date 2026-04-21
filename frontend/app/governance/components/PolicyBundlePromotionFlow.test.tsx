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
  StatusBadge: ({ label }: { label: string }) => <span data-testid="status-badge">{label}</span>,
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
    expect(await screen.findByText("bundle_id と bundle_dir_name は同時に指定できません。")).toBeInTheDocument();
  });

  it("sends promote request with expected payload shape", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        ok: true,
        bind_outcome: "success",
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

  it("renders blocked outcome and bind identifiers", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        ok: true,
        bind_outcome: "blocked",
        bind_failure_reason: "risk gate denied",
        bind_reason_code: "RISK_BLOCK",
        bind_receipt_id: "br-777",
        execution_intent_id: "ei-777",
      }),
    });

    render(<PolicyBundlePromotionFlow canOperate />);
    fillRequiredFields();
    fireEvent.click(screen.getByRole("button", { name: "promote bundle" }));

    expect(await screen.findByText("Promotion Result")).toBeInTheDocument();
    expect(screen.getByText("bind_outcome:")).toBeInTheDocument();
    expect(screen.getByText("risk gate denied")).toBeInTheDocument();
    expect(screen.getByText("RISK_BLOCK")).toBeInTheDocument();
    expect(screen.getByText("br-777")).toBeInTheDocument();
    expect(screen.getByText("ei-777")).toBeInTheDocument();
  });

  it("loads bind receipt detail through existing endpoint", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ok: true, bind_outcome: "success", bind_receipt_id: "br-100", execution_intent_id: "ei-100" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ok: true, bind_receipt: { bind_receipt_id: "br-100", final_outcome: "success" } }),
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

    expect(await screen.findByText("bind receipt detail")).toBeInTheDocument();
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
});
