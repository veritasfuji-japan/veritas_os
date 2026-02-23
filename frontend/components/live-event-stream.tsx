"use client";

import { Card } from "@veritas/design-system";
import { useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "./i18n";

const DEFAULT_API_BASE = process.env.NEXT_PUBLIC_VERITAS_API_BASE_URL ?? "http://localhost:8000";
const ENV_API_KEY = process.env.NEXT_PUBLIC_VERITAS_API_KEY ?? "";

interface StreamEvent {
  id: number;
  type: string;
  ts: string;
  payload: Record<string, unknown>;
}

/**
 * Build the SSE endpoint URL from operator-provided connection settings.
 * Returns `null` when the base URL is malformed so that the caller can
 * surface validation feedback without crashing rendering.
 */
function buildEventUrl(apiBase: string, apiKey: string): string | null {
  const base = apiBase.trim().replace(/\/$/, "");
  if (!base) {
    return null;
  }

  try {
    const url = new URL(`${base}/v1/events`);
    if (apiKey.trim()) {
      url.searchParams.set("api_key", apiKey.trim());
    }
    return url.toString();
  } catch {
    return null;
  }
}

export function LiveEventStream(): JSX.Element {
  const { t } = useI18n();
  const [apiBase, setApiBase] = useState(DEFAULT_API_BASE);
  const [apiKey, setApiKey] = useState(ENV_API_KEY);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const streamUrl = useMemo(() => buildEventUrl(apiBase, apiKey), [apiBase, apiKey]);
  const hasInvalidApiBase = apiBase.trim().length > 0 && streamUrl === null;
  const streamStatus = hasInvalidApiBase
    ? t("stream.invalid")
    : connected
      ? t("stream.connected")
      : t("stream.reconnecting");

  useEffect(() => {
    if (!streamUrl) {
      setConnected(false);
      return;
    }

    let source: EventSource | null = null;
    let mounted = true;

    const connect = (): void => {
      if (!mounted) {
        return;
      }
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current);
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
    <Card title={t("stream.title")} className="border-primary/40 bg-surface/80">
      <div className="mb-3 grid gap-3 md:grid-cols-2">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          {t("stream.apiBase")}
          <input
            value={apiBase}
            onChange={(event) => setApiBase(event.target.value)}
            className="rounded-md border border-border bg-background px-2 py-1 text-sm text-foreground"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          {t("stream.apiKey")}
          <input
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="X-API-Key"
            type="password"
            autoComplete="off"
            className="rounded-md border border-border bg-background px-2 py-1 text-sm text-foreground"
          />
        </label>
      </div>

      <p className="mb-2 text-xs text-muted-foreground">
        {t("stream.status")}: <span aria-live="polite">{streamStatus}</span>
      </p>
      {hasInvalidApiBase ? (
        <p className="mb-2 text-xs text-destructive">{t("stream.invalidUrl")}</p>
      ) : null}
      {apiKey.trim().length > 0 ? (
        <p className="mb-2 text-xs text-amber-600">
          {t("stream.securityWarning")}
        </p>
      ) : null}

      <div className="mb-3">
        <button
          type="button"
          onClick={() => setEvents([])}
          className="rounded-md border border-border/80 bg-background px-3 py-1 text-xs text-foreground hover:border-primary/70"
        >
          {t("stream.clear")}
        </button>
      </div>

      <div className="max-h-72 space-y-2 overflow-auto pr-1">
        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("stream.waiting")}</p>
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
