import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EUAIActGovernanceDashboard } from "./eu-ai-act-governance-dashboard";

class MockWebSocket {
  public onmessage: ((event: MessageEvent<string>) => void) | null = null;

  constructor(_url: string) {}

  close(): void {}
}

describe("EUAIActGovernanceDashboard", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ({ config: { eu_ai_act_mode: false, safety_threshold: 0.8 } }),
    })));
    vi.stubGlobal("WebSocket", MockWebSocket as unknown as typeof WebSocket);
  });

  it("renders toggle and risk gauge", async () => {
    render(<EUAIActGovernanceDashboard />);
    expect(await screen.findByRole("switch", { name: /eu ai act mode/i })).toBeInTheDocument();
    expect(screen.getByText(/Current Risk:/i)).toBeInTheDocument();
  });
});
