import { useState } from "react";
import { type DecideResponse, isDecideResponse } from "@veritas/types";
import { toAssistantMessage } from "../analytics/utils";
import { type ChatMessage } from "../types";

interface UseDecideParams {
  t: (ja: string, en: string) => string;
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
 */
export function useDecide({
  t,
  query,
  setQuery,
  setResult,
  setChatMessages,
}: UseDecideParams): UseDecideResult {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runDecision = async (nextQuery?: string): Promise<void> => {
    const queryToUse = (nextQuery ?? query).trim();
    setQuery(queryToUse);
    setError(null);

    if (!queryToUse) {
      setError(t("query を入力してください。", "Please enter query."));
      return;
    }

    setChatMessages((prev) => [...prev, { id: Date.now(), role: "user", content: queryToUse }]);
    setLoading(true);

    try {
      const response = await fetch("/api/veritas/v1/decide", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query: queryToUse,
          context: {},
        }),
      });

      if (response.status === 401) {
        const authError = t("401: APIキー不足、または無効です。", "401: Missing or invalid API key.");
        setError(authError);
        setChatMessages((prev) => [
          ...prev,
          {
            id: Date.now() + 1,
            role: "assistant",
            content: t("401 エラー: APIキー不足、または無効です。", "401 error: Missing or invalid API key."),
          },
        ]);
        setResult(null);
        return;
      }

      if (response.status === 503) {
        const unavailable = t(
          "503: service_unavailable（バックエンド処理を実行できません）。",
          "503: service_unavailable (backend execution unavailable).",
        );
        setError(unavailable);
        setChatMessages((prev) => [
          ...prev,
          {
            id: Date.now() + 1,
            role: "assistant",
            content: t(
              "503 エラー: service_unavailable（バックエンド処理を実行できません）。",
              "503 error: service_unavailable (backend execution unavailable).",
            ),
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
        const schemaError = t(
          "schema不一致: レスポンスがオブジェクトではありません。",
          "Schema mismatch: response is not an object.",
        );
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
    } catch {
      const networkError = t(
        "ネットワークエラー: バックエンドへ接続できません。",
        "Network error: cannot reach backend.",
      );
      setError(networkError);
      setChatMessages((prev) => [...prev, { id: Date.now() + 1, role: "assistant", content: networkError }]);
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  return { loading, error, setError, runDecision };
}
