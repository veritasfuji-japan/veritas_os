import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getReconnectDelayMs, LiveEventStream } from "./live-event-stream";

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
    vi.useRealTimers();
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

  it("uses exponential backoff with jitter for reconnect attempts", async () => {
    vi.useFakeTimers();
    vi.spyOn(Math, "random").mockReturnValue(0.5);
    const timeoutSpy = vi.spyOn(globalThis, "setTimeout");

    const fetchMock = vi.fn().mockRejectedValueOnce(new Error("network down"));
    vi.stubGlobal("fetch", fetchMock);

    render(<LiveEventStream />);

    await act(async () => {
      await Promise.resolve();
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(timeoutSpy).toHaveBeenLastCalledWith(expect.any(Function), 1000);

    vi.useRealTimers();
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


describe("getReconnectDelayMs", () => {
  it("applies exponential growth with bounded jitter", () => {
    expect(getReconnectDelayMs(0, 0)).toBe(800);
    expect(getReconnectDelayMs(1, 0.5)).toBe(2000);
    expect(getReconnectDelayMs(2, 1)).toBe(4800);
  });

  it("caps delay at max reconnect delay", () => {
    expect(getReconnectDelayMs(10, 1)).toBe(30000);
  });

  it("clamps invalid inputs", () => {
    expect(getReconnectDelayMs(-1, -5)).toBe(800);
    expect(getReconnectDelayMs(0, 5)).toBe(1200);
  });
});
