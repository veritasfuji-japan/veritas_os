import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LiveEventStream } from "./live-event-stream";

class MockEventSource {
  static instances: MockEventSource[] = [];

  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  close(): void {
    // no-op
  }
}

describe("LiveEventStream", () => {
  afterEach(() => {
    MockEventSource.instances = [];
    vi.unstubAllGlobals();
  });

  it("renders and prepends incoming SSE events", async () => {
    vi.stubGlobal("EventSource", MockEventSource);

    render(<LiveEventStream />);

    expect(screen.getByText("Live Event Stream")).toBeInTheDocument();
    expect(MockEventSource.instances.length).toBe(1);

    const source = MockEventSource.instances[0];
    await act(async () => {
      source.onmessage?.({
        data: JSON.stringify({
          id: 1,
          type: "decide.completed",
          ts: "2026-01-01T00:00:00Z",
          payload: { ok: true },
        }),
      } as MessageEvent<string>);
    });

    expect(await screen.findByText("decide.completed")).toBeInTheDocument();
    expect(screen.getByText(/"ok": true/)).toBeInTheDocument();
  });

  it("shows validation error and avoids connecting when API base URL is invalid", () => {
    vi.stubGlobal("EventSource", MockEventSource);

    render(<LiveEventStream />);

    fireEvent.change(screen.getByLabelText("API Base URL"), { target: { value: "not a url" } });

    expect(screen.getByText("有効な API Base URL を入力してください。")).toBeInTheDocument();
    expect(screen.getByText("🔴 invalid url")).toBeInTheDocument();
    expect(MockEventSource.instances.length).toBe(1);
  });

  it("shows a security warning when API key is configured", () => {
    vi.stubGlobal("EventSource", MockEventSource);

    render(<LiveEventStream />);

    const apiKeyInput = screen.getByLabelText("API Key");
    fireEvent.change(apiKeyInput, { target: { value: "secret-token" } });

    expect(apiKeyInput).toHaveAttribute("type", "password");
    expect(
      screen.getByText(
        "Security note: API key is sent in the query string for EventSource compatibility. Avoid using production secrets in shared logs.",
      ),
    ).toBeInTheDocument();
  });

  it("clears rendered events when clear button is pressed", async () => {
    vi.stubGlobal("EventSource", MockEventSource);

    render(<LiveEventStream />);

    const source = MockEventSource.instances[0];
    await act(async () => {
      source.onmessage?.({
        data: JSON.stringify({
          id: 1,
          type: "decide.completed",
          ts: "2026-01-01T00:00:00Z",
          payload: { ok: true },
        }),
      } as MessageEvent<string>);
    });

    fireEvent.click(screen.getByRole("button", { name: "Clear events" }));

    expect(screen.getByText("イベント待機中...")).toBeInTheDocument();
  });
});
