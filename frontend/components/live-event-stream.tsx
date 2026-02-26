"use client";

import { Card } from "@veritas/design-system";
import { useI18n } from "./i18n-provider";
import { useEffect, useRef, useState } from "react";

interface StreamEvent {
  id: string | number;
  type: string;
  ts: string;
  payload: unknown;
}

/**
 * Parse and dispatch SSE payload chunks emitted by the backend stream.
 *
 * We only consume `data:` lines and ignore heartbeat/comments, then emit a
 * complete event each time a blank line terminator is observed.
 */
function processSseChunk(
  chunk: string,
  carry: string,
  onData: (payload: string) => void,
): string {
  let buffer = `${carry}${chunk}`;

  while (true) {
    const terminatorIndex = buffer.indexOf("\n\n");
    if (terminatorIndex === -1) {
      break;
    }

    const rawEvent = buffer.slice(0, terminatorIndex);
    buffer = buffer.slice(terminatorIndex + 2);

    const data = rawEvent
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n")
      .trim();

    if (data) {
      onData(data);
    }
  }

  return buffer;
}

export function LiveEventStream(): JSX.Element {
  const { t } = useI18n();
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const streamUrl = "/api/veritas/v1/events";
  const streamStatus = connected ? "🟢 connected" : "🟡 reconnecting";

  useEffect(() => {
    let mounted = true;
    let controller: AbortController | null = null;

    const connect = async (): Promise<void> => {
      if (!mounted) {
        return;
      }
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current);
      }

      controller?.abort();
      controller = new AbortController();

      try {
        const response = await fetch(streamUrl, {
          signal: controller.signal,
        });

        if (!response.ok || !response.body) {
          throw new Error(`stream connection failed: ${response.status}`);
        }

        setConnected(true);
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let carry = "";

        while (mounted) {
          const { value, done } = await reader.read();
          if (done) {
            break;
          }

          carry = processSseChunk(decoder.decode(value, { stream: true }), carry, (payload) => {
            try {
              const parsed = JSON.parse(payload) as StreamEvent;
              setEvents((prev) => [parsed, ...prev].slice(0, 30));
            } catch {
              // no-op: ignore malformed event payload
            }
          });
        }
      } catch {
        // no-op: reconnection handled below
      }

      if (mounted) {
        setConnected(false);
        reconnectRef.current = setTimeout(connect, 1500);
      }
    };

    void connect();

    return () => {
      mounted = false;
      controller?.abort();
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current);
      }
    };
  }, [streamUrl]);

  return (
    <Card title="Live Event Stream" className="border-primary/40 bg-surface/80">
      <p className="mb-2 text-xs text-muted-foreground">
        Status: <span aria-live="polite">{streamStatus}</span>
      </p>
      <p className="mb-2 text-xs text-emerald-700">Security note: API key is injected server-side and never exposed to browser code.</p>

      <div className="mb-3">
        <button
          type="button"
          onClick={() => setEvents([])}
          className="rounded-md border border-border/80 bg-background px-3 py-1 text-xs text-foreground hover:border-primary/70"
        >
          Clear events
        </button>
      </div>

      <div className="max-h-72 space-y-2 overflow-auto pr-1">
        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("イベント待機中...", "Waiting for events...")}</p>
        ) : (
          events.map((event) => (
            <article key={`${event.id}-${event.ts}`} className="rounded-md border border-border/60 bg-background/60 p-2">
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="font-semibold text-primary">{event.type}</span>
                <span className="text-muted-foreground">{event.ts}</span>
              </div>
              <pre className="overflow-auto text-xs text-foreground">
                {JSON.stringify(event.payload, null, 2)}
              </pre>
            </article>
          ))
        )}
      </div>
    </Card>
  );
}
