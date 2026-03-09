import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

describe("LiveEventStream", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders seeded operations events with required fields", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, body: createReadableStream([]) }));

    render(
      <I18nProvider>
        <LiveEventStream />
      </I18nProvider>,
    );

    expect(screen.getByText("Live Event Feed")).toBeInTheDocument();
    expect(screen.getByText("FUJI reject")).toBeInTheDocument();
    expect(screen.getByText(/request_id:req_9af21/)).toBeInTheDocument();
    expect(screen.getByText(/Owner: Fuji/)).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "critical" })[0]);
    expect(screen.queryByText("policy update pending")).not.toBeInTheDocument();
  });

  it("supports acknowledge mute and pin controls", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, body: createReadableStream([]) }));

    render(
      <I18nProvider>
        <LiveEventStream />
      </I18nProvider>,
    );

    const ackButton = screen.getAllByRole("button", { name: "acknowledge" })[0];
    fireEvent.click(ackButton);
    expect(screen.getByRole("button", { name: "acknowledged" })).toBeInTheDocument();

    const pinButton = screen.getAllByRole("button", { name: "pin" })[0];
    fireEvent.click(pinButton);
    expect(screen.getByRole("button", { name: "pinned" })).toBeInTheDocument();

    const muteButton = screen.getAllByRole("button", { name: "mute" })[0];
    fireEvent.click(muteButton);
    expect(screen.queryByText("FUJI reject")).not.toBeInTheDocument();
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
});
