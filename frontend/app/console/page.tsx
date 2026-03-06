"use client";

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

  const { loading, error, runDecision } = useDecide({
    t,
    tk,
    query,
    setQuery,
    setResult,
    setChatMessages,
  });

  return (
    <div className="space-y-6">
      <Card
        title="Decision Console"
        description={tk("consoleDescription")}
        variant="glass"
        accent="primary"
        className="border-primary/20"
      >
        <div />
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

      <PipelineVisualizer />

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
            <ResultSection
              title="decision_status / chosen"
              value={{ decision_status: result.decision_status, chosen: result.chosen }}
            />
            <ResultSection
              title="alternatives/options"
              value={{ alternatives: toArray(result.alternatives), options: toArray(result.options) }}
            />
            <ResultSection
              title="fuji/gate"
              value={{ fuji: result.fuji, gate: result.gate, rejection_reason: result.rejection_reason }}
            />
            <ResultSection
              title="evidence/critique/debate"
              value={{
                evidence: toArray(result.evidence),
                critique: toArray(result.critique),
                debate: toArray(result.debate),
              }}
            />
            <CostBenefitPanel result={result} />
            <ResultSection
              title="telos_score/values"
              value={{ telos_score: result.telos_score, values: result.values }}
            />
            <ResultSection
              title="memory_citations / memory_used_count"
              value={{
                memory_citations: toArray(result.memory_citations),
                memory_used_count: result.memory_used_count,
              }}
            />
            <ResultSection title="trust_log" value={result.trust_log ?? null} />
            <details>
              <summary className="cursor-pointer text-sm font-semibold text-foreground">extras</summary>
              <pre className="mt-3 overflow-x-auto rounded-lg border border-border/50 bg-muted/30 p-3 text-xs leading-relaxed text-foreground">
                {renderValue(result.extras ?? {})}
              </pre>
            </details>
          </div>
        ) : (
          <div className="flex items-center gap-3 py-2 text-muted-foreground">
            <span className="h-2 w-2 rounded-full bg-muted-foreground/30 status-dot-live" aria-hidden="true" />
            <p className="text-sm">{tk("noResultsYet")}</p>
          </div>
        )}
      </Card>
    </div>
  );
}
