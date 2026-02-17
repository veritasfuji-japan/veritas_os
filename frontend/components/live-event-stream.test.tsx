import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
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
    source.onmessage?.({
      data: JSON.stringify({ id: 1, type: "decide.completed", ts: "2026-01-01T00:00:00Z", payload: { ok: true } }),
    } as MessageEvent<string>);

    expect(await screen.findByText("decide.completed")).toBeInTheDocument();
    expect(screen.getByText(/"ok": true/)).toBeInTheDocument();
  });

  it("shows a security warning when API key is configured", () => {
    vi.stubGlobal("EventSource", MockEventSource);

    render(<LiveEventStream />);

    fireEvent.change(screen.getByLabelText("API Key"), { target: { value: "secret-token" } });

    expect(
      screen.getByText(
        "Security note: API key is sent in the query string for EventSource compatibility. Avoid using production secrets in shared logs.",
      ),
    ).toBeInTheDocument();
  });

  it("does not crash when EventSource is unavailable", () => {
    vi.stubGlobal("EventSource", undefined);

    render(<LiveEventStream />);

    expect(screen.getByText("Live Event Stream")).toBeInTheDocument();
    expect(screen.getByText("Status: 🟡 reconnecting")).toBeInTheDocument();
  });
});
