"use client";

import { useEffect, useState } from "react";
import { Card } from "@veritas/design-system";
import { useI18n } from "../../components/i18n-provider";
import { renderValue, toArray } from "../../features/console/analytics/utils";
import { useDecide } from "../../features/console/api/useDecide";
import { ChatPanel } from "../../features/console/components/chat-panel";
import { CostBenefitPanel } from "../../features/console/components/cost-benefit-panel";
import { DecisionResultPanel } from "../../features/console/components/decision-result-panel";
import { DriftAlert } from "../../features/console/components/drift-alert";
import { EUAIActDisclosure } from "../../features/console/components/eu-ai-act-disclosure";
import { FujiGateStatusPanel } from "../../features/console/components/fuji-gate-status-panel";
import { PipelineVisualizer } from "../../features/console/components/pipeline-visualizer";
import { ResultSection } from "../../features/console/components/result-section";
import { StepExpansionPanel } from "../../features/console/components/step-expansion-panel";
import { ReplayDiffViewer } from "../../features/console/components/replay-diff-viewer";
import { ContinuationStatusCard } from "../../features/console/components/continuation-status-card";
import { useConsoleState } from "../../features/console/state/useConsoleState";
import { startManagedEventStream } from "../../lib/managed-sse";

export default function DecisionConsolePage(): JSX.Element {
  const { t, tk } = useI18n();
  const {
    query,
    setQuery,
    result,
    setResult,
    chatMessages,
    setChatMessages,
    showDriftAlert,
    setShowDriftAlert,
    governanceDriftAlert,
  } = useConsoleState();
  const [activeResultTab, setActiveResultTab] = useState<"insights" | "raw">("insights");

  const { loading, error, executionStatus, latestEvent, notifySseActivity, runDecision } = useDecide({
    t,
    tk,
    query,
    setQuery,
    setResult,
    setChatMessages,
  });

  useEffect(() => {
    if (typeof EventSource === "undefined") {
      return () => undefined;
    }

    return startManagedEventStream("/api/veritas/v1/events", {
      onMessage: (event) => {
        try {
          const payload = JSON.parse(event.data) as { type?: string; ts?: string; summary?: string };
          const eventType = payload.type ?? "event";
          const eventAt = payload.ts ?? new Date().toISOString();
          const eventSummary = payload.summary ?? eventType;
          notifySseActivity(`${eventType} @ ${eventAt} — ${eventSummary}`);
        } catch {
          // Ignore malformed event payloads.
        }
      },
    });
  }, [notifySseActivity]);

  const decisionId = String((result?.chosen as Record<string, unknown> | undefined)?.id ?? result?.request_id ?? "");

  return (
    <div className="space-y-6">
      <Card
        title="Decision Console"
        description={tk("consoleDescription")}
        variant="glass"
        accent="primary"
        className="border-primary/20"
      >
        <div className="text-sm text-muted-foreground">
          Input → Evidence → Critique → Debate → Plan → Value → FUJI → TrustLog.
        </div>
      </Card>

      <ChatPanel
        t={t}
        tk={tk}
        chatMessages={chatMessages}
        query={query}
        loading={loading}
        executionStatus={executionStatus}
        error={error}
        setQuery={setQuery}
        runDecision={runDecision}
      />

      <PipelineVisualizer
        loading={loading}
        executionStatus={executionStatus}
        latestEvent={latestEvent}
        result={result}
        error={error}
      />

      <FujiGateStatusPanel result={result} />

      {result && <ContinuationStatusCard result={result} />}

      <StepExpansionPanel result={result} />

      <DriftAlert
        alert={governanceDriftAlert}
        showAlert={showDriftAlert}
        setShowAlert={setShowDriftAlert}
      />

      <Card title="Result" titleSize="md" variant="elevated" accent={result ? "success" : undefined}>
        {result ? (
          <div className="space-y-4">
            <EUAIActDisclosure result={result} />
            <DecisionResultPanel result={result} />
            <div className="grid gap-3 md:grid-cols-3">
              <ResultSection title="Evidence sources" value={toArray(result.evidence).map((item) => (item as Record<string, unknown>).source)} />
              <ResultSection title="Critique highlights" value={toArray(result.critique).slice(0, 5)} />
              <ResultSection title="Debate summary" value={toArray(result.debate).slice(0, 5)} />
            </div>
            <CostBenefitPanel result={result} />
            <div className="flex flex-wrap gap-2">
              <span className="rounded-md border border-border px-2 py-1 text-xs">decision_id: {decisionId}</span>
              <a className="rounded-md border border-border px-2 py-1 text-xs" href={`/audit?request_id=${encodeURIComponent(result.request_id)}`}>
                TrustLog
              </a>
              <button
                type="button"
                className="rounded-md border border-border px-2 py-1 text-xs"
                onClick={() => {
                  window.location.href = `/console?decision_id=${encodeURIComponent(decisionId)}`;
                }}
              >
                {tk("replay")}
              </button>
            </div>
            <div className="space-y-2">
              <div role="tablist" className="flex gap-2 text-xs">
                <button type="button" role="tab" aria-selected={activeResultTab === "insights"} className="rounded border border-border px-2 py-1" onClick={() => setActiveResultTab("insights")}>{tk("insights")}</button>
                <button type="button" role="tab" aria-selected={activeResultTab === "raw"} className="rounded border border-border px-2 py-1" onClick={() => setActiveResultTab("raw")}>{tk("rawJson")}</button>
              </div>
              {activeResultTab === "insights" ? (
                <ResultSection title="trust_log" value={result.trust_log ?? null} />
              ) : (
                <pre className="overflow-x-auto rounded-md border border-border bg-muted/20 p-3 text-xs">{renderValue(result)}</pre>
              )}
            </div>
            <ReplayDiffViewer result={result} />
          </div>
        ) : (
          <div className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
            <p className="font-semibold text-foreground">{tk("startPromptTitle")}</p>
            <p className="mt-1">{tk("startPromptHint")}</p>
            <p className="mt-1">{tk("startPromptExplainer")}</p>
          </div>
        )}
      </Card>
    </div>
  );
}
