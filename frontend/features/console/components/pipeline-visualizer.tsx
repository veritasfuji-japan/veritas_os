import { type DecideResponse } from "@veritas/types";
import { useEffect, useMemo, useState } from "react";
import { PIPELINE_STAGES } from "../constants";

type StageState = "idle" | "running" | "complete" | "warning" | "failed";

interface PipelineVisualizerProps {
  loading: boolean;
  result: DecideResponse | null;
  error: string | null;
}

interface StageCard {
  name: string;
  status: StageState;
  latencyMs: number | null;
  summary: string;
  rawDetail: Record<string, unknown>;
}


function extractStageCards(result: DecideResponse | null, error: string | null): StageCard[] {
  const metrics = ((result?.extras?.stage_metrics ?? {}) as Record<string, unknown>);

  return PIPELINE_STAGES.map((stage) => {
    const key = stage.toLowerCase();
    const row = (metrics[key] ?? metrics[stage] ?? {}) as Record<string, unknown>;
    const latencyMs = typeof row.latency_ms === "number" ? row.latency_ms : null;
    const health = typeof row.health === "string" ? row.health : "unknown";

    let status: StageState = "idle";
    if (result) {
      status = "complete";
    }
    if (health === "warning") {
      status = "warning";
    }
    if (health === "failed") {
      status = "failed";
    }

    if (error && !result && stage === "Evidence") {
      status = "failed";
    }

    const summary = typeof row.summary === "string"
      ? row.summary
      : status === "complete"
        ? "Stage finished"
        : status === "failed"
          ? "Execution stopped"
          : "Waiting";

    return {
      name: stage,
      status,
      latencyMs,
      summary,
      rawDetail: row,
    };
  });
}

/**
 * Renders live decision pipeline cards and per-stage details.
 * While loading, cards progress sequentially so operators can track execution.
 */
export function PipelineVisualizer({ loading, result, error }: PipelineVisualizerProps): JSX.Element {
  const [activeIndex, setActiveIndex] = useState(0);
  const [selectedStage, setSelectedStage] = useState(PIPELINE_STAGES[0]);

  const cards = useMemo(() => extractStageCards(result, error), [result, error]);

  useEffect(() => {
    if (!loading) {
      return;
    }

    const intervalId = window.setInterval(() => {
      setActiveIndex((previous) => (previous + 1) % PIPELINE_STAGES.length);
    }, 650);

    return () => window.clearInterval(intervalId);
  }, [loading]);

  const selected = cards.find((card) => card.name === selectedStage) ?? cards[0];

  return (
    <section aria-label="pipeline visualizer" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">Pipeline Operations View</h2>
        <span className="text-xs text-muted-foreground">
          {loading ? "Live execution in progress" : "Latest execution snapshot"}
        </span>
      </div>
      <ol className="grid gap-2 text-xs md:grid-cols-7">
        {cards.map((card, index) => {
          const live = loading && activeIndex === index;
          const color = card.status === "failed"
            ? "border-danger/50 bg-danger/10"
            : card.status === "warning"
              ? "border-amber-500/50 bg-amber-500/10"
              : card.status === "complete"
                ? "border-emerald-500/50 bg-emerald-500/10"
                : "border-border bg-background/60";

          return (
            <li key={card.name}>
              <button
                type="button"
                className={[
                  "w-full rounded-md border px-2 py-2 text-left text-foreground transition-all duration-300",
                  color,
                  live ? "animate-pulse border-primary/60" : "",
                  selectedStage === card.name ? "ring-1 ring-primary/60" : "",
                ].join(" ")}
                onClick={() => setSelectedStage(card.name)}
              >
                <p className="font-semibold">{index + 1}. {card.name}</p>
                <p className="mt-1 text-[10px] uppercase tracking-wide text-muted-foreground">{card.status}</p>
              </button>
            </li>
          );
        })}
      </ol>
      {selected && (
        <div className="rounded-md border border-border bg-background/70 p-3 text-xs">
          <p className="font-semibold text-foreground">{selected.name} details</p>
          <p className="mt-1 text-muted-foreground">status: {selected.status}</p>
          <p className="text-muted-foreground">latency: {selected.latencyMs !== null ? `${selected.latencyMs.toFixed(0)} ms` : "n/a"}</p>
          <p className="mt-2 text-foreground">{selected.summary}</p>
          <details className="mt-2">
            <summary className="cursor-pointer text-muted-foreground">raw detail</summary>
            <pre className="mt-1 overflow-x-auto rounded-md border border-border bg-background/80 p-2 text-[11px] text-foreground">
              {JSON.stringify(selected.rawDetail, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </section>
  );
}
