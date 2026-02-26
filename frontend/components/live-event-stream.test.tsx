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

  it("shows validation error and avoids connecting when API base URL is invalid", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: createReadableStream([]),
      }),
    );

    render(<LiveEventStream />);

    fireEvent.change(screen.getByLabelText("API Base URL"), { target: { value: "not a url" } });

    expect(screen.getByText("有効な API Base URL を入力してください。")).toBeInTheDocument();
    expect(screen.getByText("🔴 invalid url")).toBeInTheDocument();
    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    });
  });

  it("sends API key in the X-API-Key header", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      body: createReadableStream([]),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<LiveEventStream />);

    const apiKeyInput = screen.getByLabelText("API Key");
    fireEvent.change(apiKeyInput, { target: { value: "secret-token" } });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });

    const lastCall = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
    expect(apiKeyInput).toHaveAttribute("type", "password");
    expect(lastCall[1]?.headers).toEqual({ "X-API-Key": "secret-token" });
    expect(screen.getByText("Security note: API key is sent in the X-API-Key header.")).toBeInTheDocument();
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
