"use client";

import { useState } from "react";
import { Card } from "@veritas/design-system";
import { useI18n } from "../../components/i18n-provider";
import { renderValue, toArray } from "../../features/console/analytics/utils";
import { useDecide } from "../../features/console/api/useDecide";
import { ChatPanel } from "../../features/console/components/chat-panel";
import { CostBenefitPanel } from "../../features/console/components/cost-benefit-panel";
import { DriftAlert } from "../../features/console/components/drift-alert";
import { EUAIActDisclosure } from "../../features/console/components/eu-ai-act-disclosure";
import { FujiGateStatusPanel } from "../../features/console/components/fuji-gate-status-panel";
import { PipelineVisualizer } from "../../features/console/components/pipeline-visualizer";
import { ResultSection } from "../../features/console/components/result-section";
import { StepExpansionPanel } from "../../features/console/components/step-expansion-panel";
import { ReplayDiffViewer } from "../../features/console/components/replay-diff-viewer";
import { useConsoleState } from "../../features/console/state/useConsoleState";

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

  const { loading, error, runDecision } = useDecide({
    t,
    tk,
    query,
    setQuery,
    setResult,
    setChatMessages,
  });

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
          Input → pipeline execution → FUJI safety judgment → decision comparison → TrustLog and Replay.
        </div>
      </Card>

      <ChatPanel
        t={t}
        tk={tk}
        chatMessages={chatMessages}
        query={query}
        loading={loading}
        error={error}
        setQuery={setQuery}
        runDecision={runDecision}
      />

      <PipelineVisualizer loading={loading} result={result} error={error} />

      <FujiGateStatusPanel result={result} />

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
            <div className="grid gap-3 md:grid-cols-3">
              <ResultSection title="Chosen" value={result.chosen} />
              <ResultSection title="Alternatives" value={toArray(result.alternatives)} />
              <ResultSection
                title="Rejected reasons"
                value={{ rejection_reason: result.rejection_reason, gate_reason: (result.gate as Record<string, unknown>).reason }}
              />
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <ResultSection title="Evidence sources" value={toArray(result.evidence).map((item) => (item as Record<string, unknown>).source)} />
              <ResultSection title="Critique highlights" value={toArray(result.critique).slice(0, 5)} />
              <ResultSection title="Debate summary" value={toArray(result.debate).slice(0, 5)} />
            </div>
            <CostBenefitPanel result={result} />
            <div className="flex flex-wrap gap-2">
              <span className="rounded-md border border-border px-2 py-1 text-xs">decision_id: {decisionId}</span>
              <a className="rounded-md border border-border px-2 py-1 text-xs" href={`/audit?request_id=${encodeURIComponent(result.request_id)}`}>
                Trust Log
              </a>
              <button type="button" className="rounded-md border border-border px-2 py-1 text-xs" onClick={() => {
                window.location.href = `/console?decision_id=${encodeURIComponent(decisionId)}`;
              }}>
                Replay
              </button>
            </div>
            <div className="space-y-2">
              <div className="flex gap-2 text-xs">
                <button type="button" className="rounded border border-border px-2 py-1" onClick={() => setActiveResultTab("insights")}>Insights</button>
                <button type="button" className="rounded border border-border px-2 py-1" onClick={() => setActiveResultTab("raw")}>Raw JSON</button>
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
            <p className="font-semibold text-foreground">Start with a real decision question.</p>
            <p className="mt-1">You will see live pipeline progression, FUJI safety checks, alternatives trade-offs, and auditable TrustLog links in one run.</p>
          </div>
        )}
      </Card>
    </div>
  );
}
