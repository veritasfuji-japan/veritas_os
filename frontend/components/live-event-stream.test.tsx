import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LiveEventStream } from "./live-event-stream";

function createReadableStream(chunks: string[]): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

describe("LiveEventStream", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders and prepends incoming SSE events", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: createReadableStream([
          "data: {\"id\": 1, \"type\": \"decide.completed\", \"ts\": \"2026-01-01T00:00:00Z\", \"payload\": {\"ok\": true}}\n\n",
        ]),
      }),
    );

    render(<LiveEventStream />);

    expect(screen.getByText("Live Event Stream")).toBeInTheDocument();
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);

    expect(await screen.findByText("decide.completed")).toBeInTheDocument();
    expect(screen.getByText(/"ok": true/)).toBeInTheDocument();
  });


  it("calls internal proxy stream endpoint without exposing API key headers", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      body: createReadableStream([]),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<LiveEventStream />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });

    const lastCall = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
    expect(lastCall[0]).toBe("/api/veritas/v1/events");
    expect(lastCall[1]?.headers).toBeUndefined();
    expect(screen.getByText("Security note: API key is injected server-side and never exposed to browser code.")).toBeInTheDocument();
  });

  it("clears rendered events when clear button is pressed", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: createReadableStream([
          "data: {\"id\": 1, \"type\": \"decide.completed\", \"ts\": \"2026-01-01T00:00:00Z\", \"payload\": {\"ok\": true}}\n\n",
        ]),
      }),
    );

    render(<LiveEventStream />);

    await act(async () => {
      await Promise.resolve();
    });

    fireEvent.click(screen.getByRole("button", { name: "Clear events" }));

    expect(screen.getByText("イベント待機中...")).toBeInTheDocument();
  });
});
