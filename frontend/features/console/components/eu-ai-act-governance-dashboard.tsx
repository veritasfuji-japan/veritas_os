"use client";

import { useEffect, useMemo, useState } from "react";
import { veritasFetch } from "../../../lib/api-client";

interface ComplianceConfig {
  eu_ai_act_mode: boolean;
  safety_threshold: number;
}

interface TrustLogEvent {
  id?: number;
  type: string;
  ts: string;
  payload: Record<string, unknown>;
}

interface SSEEventPayload {
  type?: string;
  ts?: string;
  payload?: Record<string, unknown>;
  id?: number;
}

const PIPELINE_STAGES = ["Evidence", "Debate", "Critique", "Safety"];

function riskLabel(enabled: boolean, threshold: number): "Low" | "High" | "Unacceptable" {
  if (!enabled) {
    return "Low";
  }
  if (threshold < 0.4) {
    return "Unacceptable";
  }
  return "High";
}

export function EUAIActGovernanceDashboard(): JSX.Element {
  const [config, setConfig] = useState<ComplianceConfig>({
    eu_ai_act_mode: false,
    safety_threshold: 0.8,
  });
  const [logs, setLogs] = useState<TrustLogEvent[]>([]);
  const [activeStageIndex, setActiveStageIndex] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setActiveStageIndex((prev) => (prev + 1) % PIPELINE_STAGES.length);
    }, 900);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (typeof EventSource === "undefined") {
      return () => undefined;
    }
    const stream = new EventSource("/api/veritas/v1/events");
    const acceptedTypes = new Set([
      "trustlog.debate",
      "trustlog.critique",
      "trustlog.appended",
      "compliance.pending_review",
    ]);

    stream.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data) as SSEEventPayload;
        const type = String(parsed.type || "");
        if (!acceptedTypes.has(type)) {
          return;
        }
        const nextEntry: TrustLogEvent = {
          id: typeof parsed.id === "number" ? parsed.id : undefined,
          type,
          ts: String(parsed.ts || new Date().toISOString()),
          payload: parsed.payload ?? {},
        };
        setLogs((prev) => [nextEntry, ...prev].slice(0, 40));
      } catch {
        // ignore malformed event frames
      }
    };

    stream.onerror = () => {
      stream.close();
    };

    return () => {
      stream.close();
    };
  }, []);

  const label = useMemo(
    () => riskLabel(config.eu_ai_act_mode, config.safety_threshold),
    [config.eu_ai_act_mode, config.safety_threshold],
  );

  const gaugePercent = label === "Low" ? 20 : label === "High" ? 65 : 95;

  const toggleMode = async (): Promise<void> => {
    const nextConfig = {
      ...config,
      eu_ai_act_mode: !config.eu_ai_act_mode,
    };
    setConfig(nextConfig);
    const response = await veritasFetch("/api/veritas/v1/compliance/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(nextConfig),
    });
    if (!response.ok) {
      setConfig(config);
      return;
    }
    const payload = await response.json();
    if (payload?.config) {
      setConfig(payload.config as ComplianceConfig);
    }
  };

  return (
    <section className="space-y-4 rounded-xl border border-border bg-card p-4" aria-label="EU AI Act dashboard">
      <header className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">EU AI Act Mode</h2>
        <button
          type="button"
          role="switch"
          aria-checked={config.eu_ai_act_mode}
          aria-label="EU AI Act Mode"
          className={[
            "rounded-full px-3 py-1 text-xs font-semibold transition-colors",
            config.eu_ai_act_mode ? "bg-emerald-600 text-white" : "bg-muted text-foreground",
          ].join(" ")}
          onClick={() => {
            void toggleMode();
          }}
        >
          {config.eu_ai_act_mode ? "ON" : "OFF"}
        </button>
      </header>

      <div>
        <h3 className="mb-2 text-xs font-semibold text-muted-foreground">Pipeline Visualizer</h3>
        <ol className="grid grid-cols-2 gap-2 text-xs md:grid-cols-4">
          {PIPELINE_STAGES.map((stage, index) => (
            <li
              key={stage}
              className={[
                "rounded-md border px-2 py-2 text-center transition-all",
                index === activeStageIndex ? "animate-pulse border-primary bg-primary/10" : "border-border",
              ].join(" ")}
            >
              {stage}
            </li>
          ))}
        </ol>
      </div>

      <div>
        <h3 className="mb-2 text-xs font-semibold text-muted-foreground">Risk Gauge</h3>
        <div className="h-3 w-full overflow-hidden rounded-full bg-muted">
          <div className="h-full bg-amber-500 transition-all" style={{ width: `${gaugePercent}%` }} />
        </div>
        <p className="mt-1 text-xs">Current Risk: {label}</p>
      </div>

      <div>
        <h3 className="mb-2 text-xs font-semibold text-muted-foreground">TrustLog Stream</h3>
        <div className="space-y-2">
          {logs.map((entry, index) => (
            <details key={`${entry.ts}-${index}`} className="rounded-md border border-border p-2 text-xs">
              <summary className="cursor-pointer font-medium">
                {entry.type} @ {entry.ts}
              </summary>
              <pre className="mt-2 overflow-auto whitespace-pre-wrap break-all">
                {JSON.stringify(entry.payload, null, 2)}
              </pre>
            </details>
          ))}
          {logs.length === 0 ? <p className="text-xs text-muted-foreground">No logs yet.</p> : null}
        </div>
      </div>
    </section>
  );
}
