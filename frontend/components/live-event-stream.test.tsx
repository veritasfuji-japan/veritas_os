import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "./i18n-provider";
import { LiveEventStream } from "./live-event-stream";

function createReadableStream(chunks: string[]): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });
}

function createPersistentReadableStream(): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start() {
      // Keep the stream open so reconnection side effects do not race tests.
    },
  });
}

describe("LiveEventStream", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders seeded operations events with required fields", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, body: createPersistentReadableStream() }));

    render(
      <I18nProvider>
        <LiveEventStream />
      </I18nProvider>,
    );

    expect(screen.getByText("Live Event Feed")).toBeInTheDocument();

    expect(screen.getByText("Live Event Feed")).toBeInTheDocument();
    expect(screen.getByText("FUJI reject")).toBeInTheDocument();
    expect(screen.getByText(/request_id:req_9af21/)).toBeInTheDocument();
    expect(screen.getByText(/Owner: Fuji/)).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "critical" })[0]);
    expect(screen.queryByText("policy update pending")).not.toBeInTheDocument();
  });

  it("supports acknowledge mute and pin controls", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, body: createPersistentReadableStream() }));

    render(
      <I18nProvider>
        <LiveEventStream />
      </I18nProvider>,
    );

    expect(screen.getByText("Live Event Feed")).toBeInTheDocument();

    const ackButton = screen.getAllByRole("button", { name: /acknowledge|確認/ })[0];
    fireEvent.click(ackButton);
    expect(screen.getByRole("button", { name: /acknowledged|確認済み/ })).toBeInTheDocument();

    const pinButton = screen.getAllByRole("button", { name: /^pin$|^ピン留め$/ })[0];
    fireEvent.click(pinButton);
    expect(screen.getByRole("button", { name: /pinned|ピン留め済み/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /pinned|ピン留め済み/ })).toHaveAttribute("aria-pressed", "true");

    const muteButton = screen.getAllByRole("button", { name: /mute|ミュート/ })[0];
    fireEvent.click(muteButton);
    expect(screen.queryByText("FUJI reject")).not.toBeInTheDocument();
  });

  it("filters events by search query and keeps pinned event at top", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, body: createPersistentReadableStream() }));

    render(
      <I18nProvider>
        <LiveEventStream />
      </I18nProvider>,
    );

    expect(screen.getByText("Live Event Feed")).toBeInTheDocument();

    const search = screen.getByRole("searchbox", { name: /Search events|イベント検索/ });
    fireEvent.change(search, { target: { value: "sign-off" } });
    expect(screen.queryByText("FUJI reject")).not.toBeInTheDocument();
    expect(screen.getByText("policy update pending")).toBeInTheDocument();

    fireEvent.change(search, { target: { value: "" } });
    const policyCard = screen.getByText("policy update pending").closest("div.rounded-lg");
    expect(policyCard).not.toBeNull();
    fireEvent.click(within(policyCard as HTMLElement).getByRole("button", { name: /^pin$|^ピン留め$/ }));

    const links = screen.getAllByRole("link");
    expect(links[0]).toHaveAttribute("href", "/governance");
  });

  it("appends valid SSE events and keeps clickable route", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: createReadableStream([
          "data: {\"id\":\"evt-004\",\"type\":\"risk_burst\",\"severity\":\"critical\",\"stage\":\"detect\",\"request_id\":\"req_101\",\"decision_id\":\"dec_101\",\"occurred_at\":\"2026-03-09T06:20:00Z\",\"owner\":\"Risk Ops\",\"linked_page\":\"risk\",\"summary\":\"Risk burst crossed alert threshold.\"}\n\n",
        ]),
      }),
    );

    render(
      <I18nProvider>
        <LiveEventStream />
      </I18nProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("risk burst")).toBeInTheDocument();
    });

    const links = screen.getAllByRole("link");
    expect(links[0]).toHaveAttribute("href", "/risk?request_id=req_101");
  });

  it("ignores malformed JSON events and continues parsing next messages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: createReadableStream([
          "data: {\"id\":\"evt-bad\",\"type\":\"risk_burst\",\"summary\":\n\n",
          "data: {\"id\":\"evt-005\",\"type\":\"risk_burst\",\"severity\":\"critical\",\"stage\":\"detect\",\"request_id\":\"req_105\",\"decision_id\":\"dec_105\",\"occurred_at\":\"2026-03-09T06:25:00Z\",\"owner\":\"Risk Ops\",\"linked_page\":\"risk\",\"summary\":\"Valid event after malformed JSON.\"}\n\n",
        ]),
      }),
    );

    render(
      <I18nProvider>
        <LiveEventStream />
      </I18nProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("Valid event after malformed JSON.")).toBeInTheDocument();
    });
    expect(screen.queryByText("evt-bad")).not.toBeInTheDocument();
  });

  it("ignores SSE events with invalid enum fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: createReadableStream([
          "data: {\"id\":\"evt-invalid\",\"type\":\"risk_burst\",\"severity\":\"urgent\",\"stage\":\"detect\",\"request_id\":\"req_invalid\",\"decision_id\":\"dec_invalid\",\"occurred_at\":\"2026-03-09T06:25:00Z\",\"owner\":\"Risk Ops\",\"linked_page\":\"risk\",\"summary\":\"Should be dropped due to invalid severity.\"}\n\n",
          "data: {\"id\":\"evt-007\",\"type\":\"risk_burst\",\"severity\":\"critical\",\"stage\":\"detect\",\"request_id\":\"req_107\",\"decision_id\":\"dec_107\",\"occurred_at\":\"2026-03-09T06:27:00Z\",\"owner\":\"Risk Ops\",\"linked_page\":\"risk\",\"summary\":\"Valid event remains visible.\"}\n\n",
        ]),
      }),
    );

    render(
      <I18nProvider>
        <LiveEventStream />
      </I18nProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("Valid event remains visible.")).toBeInTheDocument();
    });
    expect(screen.queryByText("Should be dropped due to invalid severity.")).not.toBeInTheDocument();
  });

  it("parses an SSE message that arrives in incomplete chunks", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: createReadableStream([
          "data: {\"id\":\"evt-006\",\"type\":\"risk_burst\",",
          "\"severity\":\"critical\",\"stage\":\"detect\",\"request_id\":\"req_106\",\"decision_id\":\"dec_106\",\"occurred_at\":\"2026-03-09T06:26:00Z\",\"owner\":\"Risk Ops\",\"linked_page\":\"risk\",\"summary\":\"Chunked event assembled correctly.\"}\n\n",
        ]),
      }),
    );

    render(
      <I18nProvider>
        <LiveEventStream />
      </I18nProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("Chunked event assembled correctly.")).toBeInTheDocument();
    });
  });

  it("reconnects after network disconnect with backoff delay", async () => {
    vi.spyOn(Math, "random").mockReturnValue(0);
    const setTimeoutSpy = vi.spyOn(globalThis, "setTimeout");
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error("network disconnected"))
      .mockResolvedValue({ ok: true, body: createPersistentReadableStream() });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <I18nProvider>
        <LiveEventStream />
      </I18nProvider>,
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(setTimeoutSpy).toHaveBeenCalledWith(expect.any(Function), 800);
    });
  });

  it("uses exponential reconnect backoff on repeated network failures", async () => {
    vi.spyOn(Math, "random").mockReturnValue(0);
    const setTimeoutSpy = vi.spyOn(globalThis, "setTimeout");
    const fetchMock = vi.fn().mockRejectedValue(new Error("network down"));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <I18nProvider>
        <LiveEventStream />
      </I18nProvider>,
    );

    await Promise.resolve();
    expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(1);
    expect(setTimeoutSpy).toHaveBeenNthCalledWith(1, expect.any(Function), 800);

    const reconnectCallback = setTimeoutSpy.mock.calls[0]?.[0];
    expect(typeof reconnectCallback).toBe("function");
    await (reconnectCallback as () => Promise<void>)();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(setTimeoutSpy).toHaveBeenNthCalledWith(2, expect.any(Function), 1600);
    });
  });

  it("remains stable in StrictMode under replayed render phases", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, body: createPersistentReadableStream() }));

    render(
      <StrictMode>
        <I18nProvider>
          <LiveEventStream />
        </I18nProvider>
      </StrictMode>,
    );

    expect(screen.getByText("Live Event Feed")).toBeInTheDocument();

    expect(screen.getAllByText("FUJI reject")).toHaveLength(1);

    const ackButton = screen.getAllByRole("button", { name: /acknowledge|確認/ })[0];
    fireEvent.click(ackButton);
    expect(screen.getByRole("button", { name: /acknowledged|確認済み/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /acknowledged|確認済み/ }));
    expect(screen.getAllByRole("button", { name: /acknowledge|確認/ })[0]).toHaveAttribute("aria-pressed", "false");
  });

  it("stops reader consumption immediately after unmount", async () => {
    const cancel = vi.fn().mockResolvedValue(undefined);
    const read = vi.fn().mockImplementation(
      () =>
        new Promise<ReadableStreamReadResult<Uint8Array>>((resolve) => {
          setTimeout(() => {
            resolve({
              done: false,
              value: new TextEncoder().encode(
                "data: {\"id\":\"evt-999\",\"type\":\"risk_burst\",\"severity\":\"critical\",\"stage\":\"detect\",\"request_id\":\"req_stop\",\"decision_id\":\"dec_stop\",\"occurred_at\":\"2026-03-09T06:30:00Z\",\"owner\":\"Risk Ops\",\"linked_page\":\"risk\",\"summary\":\"Should not be processed after unmount.\"}\n\n",
              ),
            });
          }, 0);
        }),
    );
    const getReader = vi.fn(() => ({ read, cancel }));

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body: { getReader },
      }),
    );

    const rendered = render(
      <I18nProvider>
        <LiveEventStream />
      </I18nProvider>,
    );

    await waitFor(() => {
      expect(getReader).toHaveBeenCalledTimes(1);
    });
    rendered.unmount();

    await waitFor(() => {
      expect(cancel).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByText("Should not be processed after unmount.")).not.toBeInTheDocument();
  });
});
