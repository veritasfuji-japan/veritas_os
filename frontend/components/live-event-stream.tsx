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

const BASE_RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_DELAY_MS = 30000;

function getReconnectDelayMs(attempt: number): number {
  const boundedAttempt = Math.max(0, attempt);
  const exponentialDelay = Math.min(
    BASE_RECONNECT_DELAY_MS * (2 ** boundedAttempt),
    MAX_RECONNECT_DELAY_MS,
  );
  const jitterFactor = 0.8 + (Math.random() * 0.4);
  return Math.round(exponentialDelay * jitterFactor);
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

/** Maps event type prefixes to a colour-class pair */
function getEventTypeStyle(type: string): { dot: string; label: string } {
  const lower = type.toLowerCase();
  if (lower.includes("error") || lower.includes("fail") || lower.includes("deny")) {
    return { dot: "bg-danger", label: "text-danger" };
  }
  if (lower.includes("warn") || lower.includes("alert") || lower.includes("drift")) {
    return { dot: "bg-warning", label: "text-warning" };
  }
  if (lower.includes("success") || lower.includes("pass") || lower.includes("allow")) {
    return { dot: "bg-success", label: "text-success" };
  }
  if (lower.includes("policy") || lower.includes("sync") || lower.includes("update")) {
    return { dot: "bg-violet-500", label: "text-violet-400" };
  }
  return { dot: "bg-primary", label: "text-primary" };
}

export function LiveEventStream(): JSX.Element {
  const { t } = useI18n();
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptRef = useRef(0);

  const streamUrl = "/api/veritas/v1/events";

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
        reconnectAttemptRef.current = 0;
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
        const delayMs = getReconnectDelayMs(reconnectAttemptRef.current);
        reconnectAttemptRef.current += 1;
        reconnectRef.current = setTimeout(connect, delayMs);
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

  const clearAction = (
    <button
      type="button"
      onClick={() => setEvents([])}
      className="rounded-md border border-border/70 bg-muted/50 px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
    >
      Clear events
    </button>
  );

  return (
    <Card
      title="Live Event Stream"
      titleSize="md"
      variant="glass"
      actions={clearAction}
      className="border-primary/20"
    >
      {/* Connection status */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className={[
              "h-2 w-2 rounded-full",
              connected ? "bg-emerald-500 status-dot-live" : "bg-amber-500",
            ].join(" ")}
            aria-hidden="true"
          />
          <span
            aria-live="polite"
            className={[
              "text-xs font-medium",
              connected ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400",
            ].join(" ")}
          >
            {connected ? t("接続済み", "Connected") : t("再接続中...", "Reconnecting...")}
          </span>
        </div>
        <p className="text-xs text-emerald-700 dark:text-emerald-500">
          Security note: API key is injected server-side and never exposed to browser code.
        </p>
      </div>

      {/* Event list */}
      <div
        className="max-h-72 space-y-1.5 overflow-auto pr-0.5"
        aria-label={t("ライブイベントフィード", "Live event feed")}
      >
        {events.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <span className="h-2 w-2 rounded-full bg-muted-foreground/30 status-dot-live" aria-hidden="true" />
            <p className="text-sm text-muted-foreground">{t("イベント待機中...", "Waiting for events...")}</p>
          </div>
        ) : (
          events.map((event) => {
            const style = getEventTypeStyle(event.type);
            return (
              <article
                key={`${event.id}-${event.ts}`}
                className="animate-fade-in rounded-lg border border-border/50 bg-background/60 px-3 py-2 shadow-xs transition-colors"
              >
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${style.dot}`} aria-hidden="true" />
                    <span className={`text-xs font-semibold ${style.label}`}>{event.type}</span>
                  </div>
                  <span className="font-mono text-[10px] text-muted-foreground">{event.ts}</span>
                </div>
                <pre className="overflow-auto text-[11px] leading-relaxed text-foreground/80">
                  {JSON.stringify(event.payload, null, 2)}
                </pre>
              </article>
            );
          })
        )}
      </div>
    </Card>
  );
}
