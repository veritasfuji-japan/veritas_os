import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EUAIActGovernanceDashboard } from "./eu-ai-act-governance-dashboard";

class MockEventSource {
  public onmessage: ((event: MessageEvent<string>) => void) | null = null;
  public onerror: (() => void) | null = null;

  constructor(_url: string) {}

  close(): void {}
}

describe("EUAIActGovernanceDashboard", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ({ config: { eu_ai_act_mode: false, safety_threshold: 0.8 } }),
    })));
    vi.stubGlobal("EventSource", MockEventSource as unknown as typeof EventSource);
  });

  it("renders toggle and risk gauge", async () => {
    render(<EUAIActGovernanceDashboard />);
    expect(await screen.findByRole("switch", { name: /eu ai act mode/i })).toBeInTheDocument();
    expect(screen.getByText(/Current Risk:/i)).toBeInTheDocument();
  });

  it("renders pipeline stages", () => {
    render(<EUAIActGovernanceDashboard />);
    expect(screen.getByText("Evidence")).toBeInTheDocument();
    expect(screen.getByText("Debate")).toBeInTheDocument();
    expect(screen.getByText("Critique")).toBeInTheDocument();
    expect(screen.getByText("Safety")).toBeInTheDocument();
  });

  it("renders empty log state", () => {
    render(<EUAIActGovernanceDashboard />);
    expect(screen.getByText("No logs yet.")).toBeInTheDocument();
  });

  it("shows OFF label when eu_ai_act_mode is false", () => {
    render(<EUAIActGovernanceDashboard />);
    expect(screen.getByText("OFF")).toBeInTheDocument();
  });

  it("toggles mode on button click and reverts on API failure", async () => {
    let callCount = 0;
    vi.stubGlobal("fetch", vi.fn(async () => {
      callCount++;
      if (callCount === 1) {
        return {
          ok: true,
          json: async () => ({ config: { eu_ai_act_mode: false, safety_threshold: 0.8 } }),
        };
      }
      return { ok: false, json: async () => ({}) };
    }));

    render(<EUAIActGovernanceDashboard />);
    const toggle = await screen.findByRole("switch", { name: /eu ai act mode/i });

    // Click to toggle - it should optimistically show ON then revert
    await act(async () => {
      toggle.click();
      await new Promise((r) => setTimeout(r, 50));
    });

    // After failure, it should revert back to OFF
    expect(screen.getByText("OFF")).toBeInTheDocument();
  });

  it("toggles mode on button click and updates on API success", async () => {
    let callCount = 0;
    vi.stubGlobal("fetch", vi.fn(async () => {
      callCount++;
      if (callCount === 1) {
        return {
          ok: true,
          json: async () => ({ config: { eu_ai_act_mode: false, safety_threshold: 0.8 } }),
        };
      }
      // PUT success - return updated config
      return {
        ok: true,
        json: async () => ({ config: { eu_ai_act_mode: true, safety_threshold: 0.8 } }),
      };
    }));

    render(<EUAIActGovernanceDashboard />);
    const toggle = await screen.findByRole("switch", { name: /eu ai act mode/i });

    await act(async () => {
      toggle.click();
      await new Promise((r) => setTimeout(r, 50));
    });

    expect(screen.getByText("ON")).toBeInTheDocument();
  });

  it("shows Low risk when eu_ai_act_mode is disabled", () => {
    render(<EUAIActGovernanceDashboard />);
    expect(screen.getByText(/Current Risk: Low/)).toBeInTheDocument();
  });

  it("shows High risk when eu_ai_act_mode is enabled with threshold >= 0.4", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ({ config: { eu_ai_act_mode: true, safety_threshold: 0.8 } }),
    })));

    render(<EUAIActGovernanceDashboard />);
    // Wait for fetch to complete
    await act(async () => { await new Promise((r) => setTimeout(r, 50)); });

    expect(screen.getByText(/Current Risk: High/)).toBeInTheDocument();
  });

  it("shows Unacceptable risk when threshold < 0.4", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ({ config: { eu_ai_act_mode: true, safety_threshold: 0.3 } }),
    })));

    render(<EUAIActGovernanceDashboard />);
    await act(async () => { await new Promise((r) => setTimeout(r, 50)); });

    expect(screen.getByText(/Current Risk: Unacceptable/)).toBeInTheDocument();
  });

  it("handles fetch failure gracefully and keeps defaults", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new Error("Network error");
    }));

    render(<EUAIActGovernanceDashboard />);
    await act(async () => { await new Promise((r) => setTimeout(r, 50)); });

    // Should still render with defaults
    expect(screen.getByText("OFF")).toBeInTheDocument();
    expect(screen.getByText(/Current Risk: Low/)).toBeInTheDocument();
  });
});
