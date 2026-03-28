import { useCallback, useEffect, useRef, useState } from "react";
import { type DecideResponse, isDecideResponse } from "@veritas/types";
import { ApiError, classifyHttpStatus, veritasFetchWithOptions } from "../../../lib/api-client";
import { toAssistantMessage } from "../analytics/utils";
import { type ChatMessage, type ConsoleExecutionStatus } from "../types";
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
  executionStatus: ConsoleExecutionStatus;
  latestEvent: string | null;
  setError: (error: string | null) => void;
  notifySseActivity: (eventSummary: string) => void;
  runDecision: (nextQuery?: string) => Promise<void>;
}

const DECIDE_TIMEOUT_MS = 45_000;

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
  const [executionStatus, setExecutionStatus] = useState<ConsoleExecutionStatus>("idle");
  const [latestEvent, setLatestEvent] = useState<string | null>(null);
  const activeControllerRef = useRef<AbortController | null>(null);
  const requestSequenceRef = useRef(0);
  const latestRequestIdRef = useRef(0);
  const messageIdRef = useRef(0);
  const nextMessageId = (): number => ++messageIdRef.current;

  useEffect(() => {
    return () => {
      activeControllerRef.current?.abort();
    };
  }, []);

  const notifySseActivity = useCallback((eventSummary: string): void => {
    setLatestEvent(eventSummary);
    setExecutionStatus((current) => (current === "submitting" || current === "streaming" ? "streaming" : current));
  }, []);

  const runDecision = async (nextQuery?: string): Promise<void> => {
    const queryToUse = (nextQuery ?? query).trim();
    setQuery(queryToUse);
    setError(null);
    setLatestEvent(null);

    if (!queryToUse) {
      setError(tk("queryRequired"));
      setExecutionStatus("failed");
      return;
    }

    setChatMessages((prev) => [...prev, { id: nextMessageId(), role: "user", content: queryToUse }]);
    activeControllerRef.current?.abort();
    const controller = new AbortController();
    activeControllerRef.current = controller;
    const requestId = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestId;
    latestRequestIdRef.current = requestId;
    const isLatestRequest = (): boolean => latestRequestIdRef.current === requestId;
    setLoading(true);
    setExecutionStatus("submitting");

    try {
      const response = await veritasFetchWithOptions(
        "/api/veritas/v1/decide",
        { 
          init: {
            method: "POST",
            signal: controller.signal,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              query: queryToUse,
              context: {},
            }),
          },
          timeoutMs: DECIDE_TIMEOUT_MS,
        },
      );

      if (!isLatestRequest()) {
        return;
      }

      if (response.status === 401) {
        const authError = tk("authError");
        setError(authError);
        setExecutionStatus("failed");
        setChatMessages((prev) => [
          ...prev,
          {
            id: nextMessageId(),
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
        setExecutionStatus("failed");
        setChatMessages((prev) => [
          ...prev,
          {
            id: nextMessageId(),
            role: "assistant",
            content: tk("serviceUnavailableAssistant"),
          },
        ]);
        setResult(null);
        return;
      }

      if (!response.ok) {
        const errorKind = classifyHttpStatus(response.status);
        const nextError = errorKind === "auth"
          ? tk("authError")
          : errorKind === "validation"
            ? tk("validationError")
            : errorKind === "server"
              ? tk("serverError")
              : t(
                `HTTP ${response.status}: リクエストに失敗しました。時間をおいて再試行してください。`,
                `HTTP ${response.status}: Request failed. Please try again later.`,
              );
        setError(nextError);
        setExecutionStatus("failed");
        setChatMessages((prev) => [...prev, { id: nextMessageId(), role: "assistant", content: nextError }]);
        setResult(null);
        return;
      }

      const payload: unknown = await response.json();
      if (!isDecideResponse(payload)) {
        const schemaError = tk("schemaMismatch");
        setError(schemaError);
        setExecutionStatus("failed");
        setChatMessages((prev) => [...prev, { id: nextMessageId(), role: "assistant", content: schemaError }]);
        setResult(null);
        return;
      }

      setResult(payload);
      setExecutionStatus("completed");
      setChatMessages((prev) => [
        ...prev,
        { id: nextMessageId(), role: "assistant", content: toAssistantMessage(payload, t) },
      ]);
    } catch (caught: unknown) {
      if (caught instanceof ApiError && caught.kind === "cancelled") {
        if (isLatestRequest()) {
          setExecutionStatus("idle");
        }
        return;
      }
      if (caught instanceof ApiError && caught.kind === "timeout") {
        if (isLatestRequest()) {
          const timeoutError = tk("timeoutError");
          setError(timeoutError);
          setExecutionStatus("timeout");
          setChatMessages((prev) => [...prev, { id: nextMessageId(), role: "assistant", content: timeoutError }]);
          setResult(null);
        }
        return;
      }
      if (caught instanceof DOMException && caught.name === "AbortError") {
        if (isLatestRequest()) {
          setExecutionStatus("idle");
        }
        return;
      }
      if (!isLatestRequest()) {
        return;
      }
      const networkError = tk("networkError");
      setError(networkError);
      setExecutionStatus("failed");
      setChatMessages((prev) => [...prev, { id: nextMessageId(), role: "assistant", content: networkError }]);
      setResult(null);
    } finally {
      if (isLatestRequest()) {
        setLoading(false);
      }
    }
  };

  return { loading, error, executionStatus, latestEvent, setError, notifySseActivity, runDecision };
}
