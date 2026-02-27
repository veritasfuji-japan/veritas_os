import { useEffect, useState } from "react";
import { PIPELINE_STAGES } from "../constants";

export function PipelineVisualizer(): JSX.Element {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [stageStatuses, setStageStatuses] = useState<Record<string, "idle" | "pass" | "adjusted">>(
    () =>
      Object.fromEntries(
        PIPELINE_STAGES.map((stage) => [stage, "idle"]),
      ) as Record<string, "idle" | "pass" | "adjusted">,
  );

  useEffect(() => {
    let index = 0;
    const intervalId = setInterval(() => {
      setActiveIndex(index);
      setStageStatuses((prev) => {
        const next = { ...prev };
        const currentStage = PIPELINE_STAGES[index];
        if (currentStage) {
          next[currentStage] =
            currentStage === "Critique" || currentStage === "Value" ? "adjusted" : "pass";
        }
        return next;
      });

      index += 1;
      if (index >= PIPELINE_STAGES.length) {
        index = 0;
        setTimeout(() => {
          setStageStatuses(
            Object.fromEntries(
              PIPELINE_STAGES.map((stage) => [stage, "idle"]),
            ) as Record<string, "idle" | "pass" | "adjusted">,
          );
        }, 500);
      }
    }, 900);

    return () => {
      clearInterval(intervalId);
    };
  }, []);

  return (
    <section aria-label="pipeline visualizer" className="space-y-2">
      <h2 className="text-sm font-semibold text-foreground">Pipeline Visualizer</h2>
      <ol className="grid gap-2 text-xs md:grid-cols-7">
        {PIPELINE_STAGES.map((stage, index) => (
          <li
            key={stage}
            className={[
              "rounded-md border px-2 py-2 text-center text-foreground transition-all duration-300",
              activeIndex === index
                ? "animate-pulse border-primary/60 bg-primary/15"
                : "border-border bg-background/60",
              stageStatuses[stage] === "pass" ? "border-emerald-500/50 bg-emerald-500/10" : "",
              stageStatuses[stage] === "adjusted" ? "border-amber-500/50 bg-amber-500/10" : "",
            ].join(" ")}
          >
            <span className="mr-1 text-muted-foreground">{index + 1}.</span>
            {stage}
            <p className="mt-1 text-[10px] uppercase tracking-wide text-muted-foreground">
              {stageStatuses[stage] === "pass"
                ? "green"
                : stageStatuses[stage] === "adjusted"
                  ? "yellow"
                  : "idle"}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}
