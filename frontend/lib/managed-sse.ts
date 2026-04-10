"use client";

const BASE_RECONNECT_DELAY_MS = 1_000;
const MAX_RECONNECT_DELAY_MS = 30_000;
const AUTH_RETRY_PAUSE_MS = 60_000;

export interface ManagedSseOptions {
  onMessage: (event: MessageEvent<string>) => void;
  onOpen?: () => void;
  onDisconnected?: () => void;
  onAuthPause?: (untilEpochMs: number | null) => void;
  authRetryPauseMs?: number;
}

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
 * Start a managed SSE connection with retry/backoff and auth pause handling.
 *
 * Concurrency safety:
 * - Ignores stale async probe responses when multiple connect attempts overlap.
 * - Ensures EventSource error handlers only act on their own instance.
 */
export function startManagedEventStream(
  url: string,
  options: ManagedSseOptions,
): () => void {
  let disposed = false;
  let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  let eventSource: EventSource | null = null;
  let reconnectAttempt = 0;
  let connectSequence = 0;

  const authPauseMs = options.authRetryPauseMs ?? AUTH_RETRY_PAUSE_MS;

  const clearReconnectTimeout = (): void => {
    if (!reconnectTimeout) {
      return;
    }
    clearTimeout(reconnectTimeout);
    reconnectTimeout = null;
  };

  const closeEventSource = (): void => {
    if (!eventSource) {
      return;
    }
    eventSource.close();
    eventSource = null;
    options.onDisconnected?.();
  };

  const scheduleReconnect = (delayMs: number): void => {
    if (disposed) {
      return;
    }
    clearReconnectTimeout();
    reconnectTimeout = setTimeout(() => {
      void connect();
    }, delayMs);
  };

  const connect = async (): Promise<void> => {
    if (disposed) {
      return;
    }

    const currentConnectSequence = connectSequence + 1;
    connectSequence = currentConnectSequence;

    clearReconnectTimeout();
    closeEventSource();

    try {
      const probe = await fetch(url, {
        credentials: "same-origin",
        method: "GET",
      });

      if (disposed || currentConnectSequence !== connectSequence) {
        return;
      }

      if (probe.status === 401 || probe.status === 403) {
        options.onAuthPause?.(Date.now() + authPauseMs);
        scheduleReconnect(authPauseMs);
        return;
      }

      if (!probe.ok) {
        throw new Error(`sse probe failed: ${probe.status}`);
      }
    } catch {
      if (disposed || currentConnectSequence !== connectSequence) {
        return;
      }
      const delayMs = getReconnectDelayMs(reconnectAttempt);
      reconnectAttempt += 1;
      scheduleReconnect(delayMs);
      return;
    }

    if (disposed || currentConnectSequence !== connectSequence) {
      return;
    }

    options.onAuthPause?.(null);
    reconnectAttempt = 0;

    const nextEventSource = new EventSource(url, { withCredentials: true });
    eventSource = nextEventSource;
    nextEventSource.onopen = () => {
      reconnectAttempt = 0;
      options.onOpen?.();
    };
    nextEventSource.onmessage = options.onMessage;
    nextEventSource.onerror = () => {
      if (eventSource !== nextEventSource) {
        return;
      }
      closeEventSource();
      const delayMs = getReconnectDelayMs(reconnectAttempt);
      reconnectAttempt += 1;
      scheduleReconnect(delayMs);
    };
  };

  void connect();

  return () => {
    disposed = true;
    clearReconnectTimeout();
    closeEventSource();
    options.onAuthPause?.(null);
  };
}
