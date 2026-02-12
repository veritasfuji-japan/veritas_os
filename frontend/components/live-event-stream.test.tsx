import React from "react";
import { render, screen } from "@testing-library/react";
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

    expect(screen.getByText("Live Event Stream")).not.toBeNull();
    expect(MockEventSource.instances.length).toBe(1);

    const source = MockEventSource.instances[0];
    source.onmessage?.({
      data: JSON.stringify({ id: 1, type: "decide.completed", ts: "2026-01-01T00:00:00Z", payload: { ok: true } }),
    } as MessageEvent<string>);

    expect(await screen.findByText("decide.completed")).not.toBeNull();
    expect(screen.getByText(/"ok": true/)).not.toBeNull();
  });
});
