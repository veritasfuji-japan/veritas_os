import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LiveEventStream } from "./live-event-stream";
import { I18nProvider } from "./i18n-provider";

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

    render(
      <I18nProvider>
        <LiveEventStream />
      </I18nProvider>,
    );

    expect(screen.getByText("ライブイベントストリーム")).toBeInTheDocument();
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

    render(
      <I18nProvider>
        <LiveEventStream />
      </I18nProvider>,
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });

    const lastCall = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
    expect(lastCall[0]).toBe("/api/veritas/v1/events");
    expect(lastCall[1]?.headers).toBeUndefined();
    expect(screen.getByText("セキュリティ注記: APIキーはサーバー側で注入され、ブラウザーコードには公開されません。")).toBeInTheDocument();
  });

  it("uses exponential backoff with jitter for reconnect attempts", async () => {
    vi.useFakeTimers();
    vi.spyOn(Math, "random").mockReturnValue(0.5);
    const timeoutSpy = vi.spyOn(globalThis, "setTimeout");

    const fetchMock = vi.fn().mockRejectedValueOnce(new Error("network down"));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <I18nProvider>
        <LiveEventStream />
      </I18nProvider>,
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(timeoutSpy).toHaveBeenLastCalledWith(expect.any(Function), 1000);

    vi.useRealTimers();
  });

  it("pauses retries and shows re-auth guidance after 401/403", async () => {
    vi.useFakeTimers();
    const timeoutSpy = vi.spyOn(globalThis, "setTimeout");
    vi.spyOn(Date, "now").mockReturnValue(1_000_000);

    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      body: null,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <I18nProvider>
        <LiveEventStream />
      </I18nProvider>,
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(timeoutSpy).toHaveBeenLastCalledWith(expect.any(Function), 60000);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "認証エラー (401/403) を検知しました。再認証後に再接続してください。",
    );
    expect(screen.getByText(/17:40/)).toBeInTheDocument();

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

    render(
      <I18nProvider>
        <LiveEventStream />
      </I18nProvider>,
    );

    await act(async () => {
      await Promise.resolve();
    });

    fireEvent.click(screen.getByRole("button", { name: "イベントをクリア" }));

    expect(screen.getByText("イベント待機中...")).toBeInTheDocument();
  });

  it("does not render raw i18n keys in the UI", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: createReadableStream([]),
      }),
    );

    render(
      <I18nProvider>
        <LiveEventStream />
      </I18nProvider>,
    );

    const untranslatedKeys = [
      "clearEvents",
      "liveEventStreamTitle",
      "streamSecurityNote",
      "streamAuthRecoveryHint",
      "streamAuthRetryPausedUntil",
    ];
    for (const key of untranslatedKeys) {
      expect(screen.queryByText(key)).not.toBeInTheDocument();
    }
  });

});
