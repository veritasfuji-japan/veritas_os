import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DecisionConsolePage from "./page";

describe("DecisionConsolePage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders pipeline stages in fixed order", () => {
    render(<DecisionConsolePage />);

    expect(screen.getByText("1.", { exact: false })).not.toBeNull();
    expect(screen.getByText("Evidence")).not.toBeNull();
    expect(screen.getByText("TrustLog")).not.toBeNull();
  });

  it("shows 401 message when api key is missing", async () => {
    render(<DecisionConsolePage />);

    fireEvent.change(screen.getByPlaceholderText("意思決定したい問いを入力"), {
      target: { value: "Test" },
    });

    fireEvent.click(screen.getByRole("button", { name: "実行" }));

    expect(await screen.findByText(/401: APIキー不足/)).not.toBeNull();
  });

  it("renders structured sections from decide response", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        decision_status: "allow",
        chosen: { id: "a1" },
        alternatives: [{ id: "a1" }],
        options: [{ id: "a1" }],
        fuji: { decision_status: "allow" },
        gate: { decision_status: "allow" },
        evidence: [{ source: "doc" }],
        critique: [],
        debate: [],
        telos_score: 0.9,
        values: { utility: 0.8 },
        memory_citations: [{ id: "m1" }],
        memory_used_count: 1,
        trust_log: null,
        extras: { raw: true },
      }),
    } as Response);

    render(<DecisionConsolePage />);

    fireEvent.change(screen.getByPlaceholderText("API key"), {
      target: { value: "test-key" },
    });
    fireEvent.change(screen.getByPlaceholderText("意思決定したい問いを入力"), {
      target: { value: "A/B test" },
    });

    fireEvent.click(screen.getByRole("button", { name: "実行" }));

    await waitFor(() => {
      expect(screen.getByText("decision_status / chosen")).not.toBeNull();
      expect(screen.getByText("memory_citations / memory_used_count")).not.toBeNull();
    });
  });
});
