import { useEffect, useMemo, useRef, useState } from "react";
import { type DecideResponse } from "@veritas/types";
import { buildGovernanceDriftAlert } from "../analytics/pipeline";
import { type ChatMessage } from "../types";

/**
 * Keeps page-level console state and derived drift-alert behavior grouped by concern.
 */
export function useConsoleState() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<DecideResponse | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [showDriftAlert, setShowDriftAlert] = useState(false);
  const driftAlertTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const governanceDriftAlert = useMemo(() => buildGovernanceDriftAlert(result), [result]);

  useEffect(() => {
    if (!governanceDriftAlert) {
      setShowDriftAlert(false);
      if (driftAlertTimerRef.current) {
        clearTimeout(driftAlertTimerRef.current);
      }
      return;
    }

    setShowDriftAlert(true);
    driftAlertTimerRef.current = setTimeout(() => {
      setShowDriftAlert(false);
    }, 8000);

    return () => {
      if (driftAlertTimerRef.current) {
        clearTimeout(driftAlertTimerRef.current);
      }
    };
  }, [governanceDriftAlert]);

  return {
    query,
    setQuery,
    result,
    setResult,
    chatMessages,
    setChatMessages,
    showDriftAlert,
    setShowDriftAlert,
    governanceDriftAlert,
  };
}
