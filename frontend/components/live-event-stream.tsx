"use client";

import { Card } from "@veritas/design-system";
import { useEffect, useMemo, useRef, useState } from "react";
const ENV_API_KEY = process.env.NEXT_PUBLIC_VERITAS_API_KEY ?? "";

interface StreamEvent {
  id: number;
  type: string;
  ts: string;
  payload: Record<string, unknown>;
}

/**
 * Build a same-origin SSE endpoint URL routed through Next.js rewrites.
 */
function buildEventUrl(apiKey: string): string {
  const params = new URLSearchParams();
  if (apiKey.trim()) {
    params.set("api_key", apiKey.trim());
  }
  const query = params.toString();
  return query ? `/api/v1/events?${query}` : "/api/v1/events";
}

export function LiveEventStream(): JSX.Element {
  const [apiKey, setApiKey] = useState(ENV_API_KEY);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const streamUrl = useMemo(() => buildEventUrl(apiKey), [apiKey]);

  useEffect(() => {
    if (!streamUrl) {
      setConnected(false);
      return;
    }

    if (typeof EventSource === "undefined") {
      setConnected(false);
      return;
    }

    let source: EventSource | null = null;
    let mounted = true;

    const connect = (): void => {
      if (!mounted) {
        return;
      }
      source = new EventSource(streamUrl);

      source.onopen = () => {
        setConnected(true);
      };

      source.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data) as StreamEvent;
          setEvents((prev) => [parsed, ...prev].slice(0, 30));
        } catch {
          // no-op: ignore malformed event payload
        }
      };

      source.onerror = () => {
        setConnected(false);
        source?.close();
        reconnectRef.current = setTimeout(connect, 1500);
      };
    };

    connect();

    return () => {
      mounted = false;
      source?.close();
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current);
      }
    };
  }, [streamUrl]);

  return (
    <Card title="Live Event Stream" className="border-primary/40 bg-surface/80">
      <div className="mb-3 grid gap-3 md:grid-cols-2">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          API Key
          <input
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="X-API-Key"
            className="rounded-md border border-border bg-background px-2 py-1 text-sm text-foreground"
          />
        </label>
      </div>

      <p className="mb-2 text-xs text-muted-foreground">
        Status: {connected ? "🟢 connected" : "🟡 reconnecting"}
      </p>
      {apiKey.trim().length > 0 ? (
        <p className="mb-2 text-xs text-amber-600">
          Security note: API key is sent in the query string for EventSource compatibility. Avoid using production secrets in shared logs.
        </p>
      ) : null}

      <div className="max-h-72 space-y-2 overflow-auto pr-1">
        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground">イベント待機中...</p>
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
