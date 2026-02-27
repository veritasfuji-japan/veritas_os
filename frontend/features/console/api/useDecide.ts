import { useEffect, useRef, useState } from "react";
import { type DecideResponse, isDecideResponse } from "@veritas/types";
import { toAssistantMessage } from "../analytics/utils";
import { type ChatMessage } from "../types";
import { type LocaleKey } from "../../../locales/ja";

interface UseDecideParams {
  t: (ja: string, en: string) => string;
  tk: (key: LocaleKey) => string;
  query: string;
  setQuery: (query: string) => void;
  setResult: (result: DecideResponse | null) => void;
  setChatMessages: (updater: (prev: ChatMessage[]) => ChatMessage[]) => void;
}

interface UseDecideResult {
  loading: boolean;
  error: string | null;
  setError: (error: string | null) => void;
  runDecision: (nextQuery?: string) => Promise<void>;
}

/**
 * Encapsulates decide API communication and user-facing error handling.
 *
 * Uses AbortController and a monotonic request id to prevent stale responses
 * from overwriting the newest UI state during rapid submissions or unmount.
 */
export function useDecide({
  t,
  tk,
  query,
  setQuery,
  setResult,
  setChatMessages,
}: UseDecideParams): UseDecideResult {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const activeControllerRef = useRef<AbortController | null>(null);
  const requestSequenceRef = useRef(0);
  const latestRequestIdRef = useRef(0);

  useEffect(() => {
    return () => {
      activeControllerRef.current?.abort();
    };
  }, []);

  const runDecision = async (nextQuery?: string): Promise<void> => {
    const queryToUse = (nextQuery ?? query).trim();
    setQuery(queryToUse);
    setError(null);

    if (!queryToUse) {
      setError(tk("queryRequired"));
      return;
    }

    setChatMessages((prev) => [...prev, { id: Date.now(), role: "user", content: queryToUse }]);
    activeControllerRef.current?.abort();
    const controller = new AbortController();
    activeControllerRef.current = controller;
    const requestId = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestId;
    latestRequestIdRef.current = requestId;
    const isLatestRequest = (): boolean => latestRequestIdRef.current === requestId;
    setLoading(true);

    try {
      const response = await fetch("/api/veritas/v1/decide", {
        method: "POST",
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query: queryToUse,
          context: {},
        }),
      });

      if (!isLatestRequest()) {
        return;
      }

      if (response.status === 401) {
        const authError = tk("authError");
        setError(authError);
        setChatMessages((prev) => [
          ...prev,
          {
            id: Date.now() + 1,
            role: "assistant",
            content: tk("authErrorAssistant"),
          },
        ]);
        setResult(null);
        return;
      }

      if (response.status === 503) {
        const unavailable = tk("serviceUnavailable");
        setError(unavailable);
        setChatMessages((prev) => [
          ...prev,
          {
            id: Date.now() + 1,
            role: "assistant",
            content: tk("serviceUnavailableAssistant"),
          },
        ]);
        setResult(null);
        return;
      }

      if (!response.ok) {
        const bodyText = await response.text();
        const nextError = `HTTP ${response.status}: ${bodyText || "unknown error"}`;
        setError(nextError);
        setChatMessages((prev) => [...prev, { id: Date.now() + 1, role: "assistant", content: nextError }]);
        setResult(null);
        return;
      }

      const payload: unknown = await response.json();
      if (!isDecideResponse(payload)) {
        const schemaError = tk("schemaMismatch");
        setError(schemaError);
        setChatMessages((prev) => [...prev, { id: Date.now() + 1, role: "assistant", content: schemaError }]);
        setResult(null);
        return;
      }

      setResult(payload);
      setChatMessages((prev) => [
        ...prev,
        { id: Date.now() + 1, role: "assistant", content: toAssistantMessage(payload, t) },
      ]);
    } catch (caught: unknown) {
      if (caught instanceof DOMException && caught.name === "AbortError") {
        return;
      }
      if (!isLatestRequest()) {
        return;
      }
      const networkError = tk("networkError");
      setError(networkError);
      setChatMessages((prev) => [...prev, { id: Date.now() + 1, role: "assistant", content: networkError }]);
      setResult(null);
    } finally {
      if (isLatestRequest()) {
        setLoading(false);
      }
    }
  };

  return { loading, error, setError, runDecision };
}
