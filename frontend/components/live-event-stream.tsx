"use client";

import { Card } from "@veritas/design-system";
import { type Dispatch, type SetStateAction, useEffect, useMemo, useRef, useState } from "react";
import { cn } from "../lib/utils";
import { useI18n } from "./i18n-provider";

type EventFilter = "all" | "critical" | "degraded" | "health";
type EventSeverity = "critical" | "degraded" | "health";
type EventStage = "detect" | "triage" | "mitigate" | "resolved";
type EventType =
  | "fuji_reject"
  | "replay_mismatch"
  | "policy_update_pending"
  | "broken_hash_chain"
  | "risk_burst";

interface LiveEvent {
  id: string;
  type: EventType;
  severity: EventSeverity;
  stage: EventStage;
  request_id: string;
  decision_id: string;
  occurred_at: string;
  owner: string;
  linked_page: "decision" | "trustlog" | "governance" | "risk";
  summary: string;
}

type FlagRecord = Record<string, true>;

const BASE_RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_DELAY_MS = 30000;
const AUTH_RETRY_PAUSE_MS = 60000;

const FILTERS: EventFilter[] = ["all", "critical", "degraded", "health"];

const EVENT_TYPE_LABEL: Record<EventType, string> = {
  fuji_reject: "FUJI reject",
  replay_mismatch: "replay mismatch",
  policy_update_pending: "policy update pending",
  broken_hash_chain: "broken hash chain",
  risk_burst: "risk burst",
};

const STAGE_LABEL: Record<EventStage, string> = {
  detect: "Detect",
  triage: "Triage",
  mitigate: "Mitigate",
  resolved: "Resolved",
};

const LINKED_PAGE_ROUTE: Record<LiveEvent["linked_page"], string> = {
  decision: "/console",
  trustlog: "/audit",
  governance: "/governance",
  risk: "/risk",
};

const SEVERITY_STYLE: Record<EventSeverity, string> = {
  critical: "border-danger/40 bg-danger/10 text-danger",
  degraded: "border-warning/40 bg-warning/10 text-warning",
  health: "border-success/40 bg-success/10 text-success",
};

const STAGE_STYLE: Record<EventStage, string> = {
  detect: "bg-danger/10 text-danger",
  triage: "bg-warning/10 text-warning",
  mitigate: "bg-primary/10 text-primary",
  resolved: "bg-success/10 text-success",
};

const SEED_EVENTS: LiveEvent[] = [
  {
    id: "evt-001",
    type: "fuji_reject",
    severity: "critical",
    stage: "triage",
    request_id: "req_9af21",
    decision_id: "dec_2201",
    occurred_at: "2026-03-09T06:12:10Z",
    owner: "Fuji",
    linked_page: "decision",
    summary: "Reject burst detected under policy.v44. Manual split needed.",
  },
  {
    id: "evt-002",
    type: "replay_mismatch",
    severity: "critical",
    stage: "mitigate",
    request_id: "req_9af09",
    decision_id: "dec_2198",
    occurred_at: "2026-03-09T06:10:22Z",
    owner: "Kernel",
    linked_page: "trustlog",
    summary: "Replay mismatch persisted for 3 checks. Chain revalidation running.",
  },
  {
    id: "evt-003",
    type: "policy_update_pending",
    severity: "degraded",
    stage: "detect",
    request_id: "req_9aef0",
    decision_id: "dec_2195",
    occurred_at: "2026-03-09T06:08:02Z",
    owner: "Governance",
    linked_page: "governance",
    summary: "Sign-off pending for policy rollout v44, impact window active.",
  },
];

function getReconnectDelayMs(attempt: number): number {
  const boundedAttempt = Math.max(0, attempt);
  const exponentialDelay = Math.min(
    BASE_RECONNECT_DELAY_MS * (2 ** boundedAttempt),
    MAX_RECONNECT_DELAY_MS,
  );
  const jitterFactor = 0.8 + (Math.random() * 0.4);
  return Math.round(exponentialDelay * jitterFactor);
}

function toLiveEvent(payload: unknown): LiveEvent | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }

  const record = payload as Partial<LiveEvent> & { type?: string };

  const validType = Object.keys(EVENT_TYPE_LABEL).includes(record.type ?? "")
    ? (record.type as EventType)
    : null;

  if (!validType || !record.id) {
    return null;
  }

  if (!record.severity || !record.stage || !record.request_id || !record.decision_id || !record.occurred_at || !record.owner || !record.linked_page || !record.summary) {
    return null;
  }

  return {
    id: String(record.id),
    type: validType,
    severity: record.severity,
    stage: record.stage,
    request_id: record.request_id,
    decision_id: record.decision_id,
    occurred_at: record.occurred_at,
    owner: record.owner,
    linked_page: record.linked_page,
    summary: record.summary,
  } as LiveEvent;
}

function buildLink(event: LiveEvent): string {
  const base = LINKED_PAGE_ROUTE[event.linked_page];
  if (event.linked_page === "decision") {
    return `${base}?decision_id=${encodeURIComponent(event.decision_id)}`;
  }
  if (event.linked_page === "trustlog" || event.linked_page === "risk") {
    return `${base}?request_id=${encodeURIComponent(event.request_id)}`;
  }
  return base;
}

export function LiveEventStream(): JSX.Element {
  const { t, tk } = useI18n();
  const [events, setEvents] = useState<LiveEvent[]>(SEED_EVENTS);
  const [connected, setConnected] = useState(false);
  const [authRecoveryAt, setAuthRecoveryAt] = useState<number | null>(null);
  const [activeFilter, setActiveFilter] = useState<EventFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [ackedIds, setAckedIds] = useState<FlagRecord>({});
  const [mutedIds, setMutedIds] = useState<FlagRecord>({});
  const [pinnedIds, setPinnedIds] = useState<FlagRecord>({});
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptRef = useRef(0);
  const authPauseRef = useRef(false);
  const streamUrl = "/api/veritas/v1/events";

  useEffect(() => {
    let mounted = true;
    let controller: AbortController | null = null;
    let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;

    const connect = async (): Promise<void> => {
      if (!mounted) {
        return;
      }

      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current);
      }

      controller?.abort();
      controller = new AbortController();

      try {
        const response = await fetch(streamUrl, { signal: controller.signal, credentials: "same-origin" });
        if (!response.ok || !response.body) {
          if (response.status === 401 || response.status === 403) {
            const recoveryAt = Date.now() + AUTH_RETRY_PAUSE_MS;
            authPauseRef.current = true;
            setAuthRecoveryAt(recoveryAt);
            reconnectRef.current = setTimeout(connect, AUTH_RETRY_PAUSE_MS);
            return;
          }
          throw new Error(`stream connection failed: ${response.status}`);
        }

        authPauseRef.current = false;
        setAuthRecoveryAt(null);
        setConnected(true);
        reconnectAttemptRef.current = 0;

        reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (mounted) {
          const { value, done } = await reader.read();
          if (!mounted || controller.signal.aborted) {
            break;
          }
          if (done) {
            break;
          }
          buffer += decoder.decode(value, { stream: true });

          while (buffer.includes("\n\n")) {
            if (!mounted || controller.signal.aborted) {
              break;
            }
            const [rawEvent, ...rest] = buffer.split("\n\n");
            buffer = rest.join("\n\n");
            const dataLine = rawEvent.split(/\r?\n/).find((line) => line.startsWith("data:"));
            if (!dataLine) {
              continue;
            }
            let parsed: LiveEvent | null;
            try {
              parsed = toLiveEvent(JSON.parse(dataLine.slice(5).trim()));
            } catch {
              continue;
            }
            if (!parsed) {
              continue;
            }
            setEvents((previous) => {
              const withoutDuplicate = previous.filter((event) => event.id !== parsed.id);
              return [parsed, ...withoutDuplicate].slice(0, 40);
            });
          }
        }
      } catch {
        // reconnect handled below
      }

      if (mounted) {
        setConnected(false);
        if (authPauseRef.current) {
          return;
        }
        const delayMs = getReconnectDelayMs(reconnectAttemptRef.current);
        reconnectAttemptRef.current += 1;
        reconnectRef.current = setTimeout(connect, delayMs);
      }
    };

    void connect();

    return () => {
      mounted = false;
      controller?.abort();
      void reader?.cancel();
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current);
      }
    };
  }, []);

  const filteredEvents = useMemo(() => {
    const withoutMuted = events.filter((event) => mutedIds[event.id] !== true);
    const severityFiltered = activeFilter === "all"
      ? withoutMuted
      : withoutMuted.filter((event) => event.severity === activeFilter);

    const normalizedQuery = searchQuery.trim().toLowerCase();
    const queryFiltered = normalizedQuery.length === 0
      ? severityFiltered
      : severityFiltered.filter((event) => {
        const searchableText = [
          EVENT_TYPE_LABEL[event.type],
          event.summary,
          event.request_id,
          event.decision_id,
          event.owner,
        ].join(" ").toLowerCase();
        return searchableText.includes(normalizedQuery);
      });

    return [...queryFiltered].sort((left, right) => {
      const leftPinned = pinnedIds[left.id] === true;
      const rightPinned = pinnedIds[right.id] === true;
      if (leftPinned === rightPinned) {
        return 0;
      }
      return leftPinned ? -1 : 1;
    });
  }, [activeFilter, events, mutedIds, pinnedIds, searchQuery]);

  const toggle = (setState: Dispatch<SetStateAction<FlagRecord>>, id: string): void => {
    setState((current) => {
      if (current[id] === true) {
        const { [id]: _removed, ...remaining } = current;
        return remaining;
      }
      return {
        ...current,
        [id]: true,
      };
    });
  };

  return (
    <Card title="Live Event Feed" titleSize="md" variant="glass" className="border-primary/20">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs">
          <span className={cn("h-2 w-2 rounded-full", connected ? "bg-emerald-500 status-dot-live" : "bg-amber-500")} />
          <span>{connected ? t("接続済み", "Connected") : t("再接続中...", "Reconnecting...")}</span>
        </div>
        <div className="flex gap-1">
          {FILTERS.map((filter) => (
            <button
              key={filter}
              type="button"
              onClick={() => setActiveFilter(filter)}
              aria-pressed={activeFilter === filter}
              className={cn(
                "rounded-md border px-2 py-1 text-[11px] capitalize",
                activeFilter === filter ? "border-primary bg-primary/10 text-primary" : "border-border/70 text-muted-foreground",
              )}
            >
              {filter}
            </button>
          ))}
        </div>
      </div>
      <div className="mb-3">
        <label className="sr-only" htmlFor="event-search-input">
          {t("イベント検索", "Search events")}
        </label>
        <input
          id="event-search-input"
          type="search"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder={t("イベントを検索...", "Search events...")}
          className="w-full rounded-md border border-border/70 bg-background px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
        />
      </div>

      {authRecoveryAt !== null ? (
        <p className="mb-3 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">
          {t("認証エラーを検知。再認証後に再接続します。", "Authentication error detected. Reconnect after re-auth.")}
          {" "}
          {new Date(authRecoveryAt).toLocaleTimeString()}
        </p>
      ) : null}

      <div className="max-h-80 space-y-2 overflow-auto pr-0.5" aria-label="Live event feed">
        {filteredEvents.length === 0 ? (
          <div className="rounded-lg border border-border/60 bg-muted/20 p-4 text-xs text-muted-foreground">
            <p>{t("現在は低アクティビティです。", "Low activity right now.")}</p>
            <p className="mt-1">
              {t(
                "このフィードは FUJI reject / replay mismatch / policy update pending / broken hash chain / risk burst を監視し、異常時は Decision・TrustLog・Governance・Risk へ遷移できます。",
                "This feed monitors FUJI reject/replay mismatch/policy update pending/broken hash chain/risk burst and routes to Decision, TrustLog, Governance, and Risk when anomalies occur.",
              )}
            </p>
          </div>
        ) : (
          filteredEvents.map((event) => {
            const link = buildLink(event);
            const isAcked = ackedIds[event.id] === true;
            const isPinned = pinnedIds[event.id] === true;

            return (
              <div
                key={event.id}
                className="rounded-lg border border-border/60 bg-background/70 p-3 transition-colors hover:bg-background"
              >
                <a href={link} className="block">
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <span className={cn("rounded border px-1.5 py-0.5 font-semibold", SEVERITY_STYLE[event.severity])}>
                          {event.severity}
                        </span>
                        <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-semibold", STAGE_STYLE[event.stage])}>
                          {STAGE_LABEL[event.stage]}
                        </span>
                        <span className="font-semibold">{EVENT_TYPE_LABEL[event.type]}</span>
                      </div>
                      <p className="text-xs text-muted-foreground">{event.summary}</p>
                      <p className="font-mono text-[10px] text-muted-foreground">
                        request_id:{event.request_id} / decision_id:{event.decision_id}
                      </p>
                    </div>
                    <div className="text-right text-[10px] text-muted-foreground">
                      <p>Owner: {event.owner}</p>
                      <p>{new Date(event.occurred_at).toLocaleTimeString()}</p>
                    </div>
                  </div>
                </a>
                <div className="mt-2 flex flex-wrap gap-1.5 text-[10px]">
                  <button
                    type="button"
                    onClick={() => toggle(setAckedIds, event.id)}
                    aria-pressed={isAcked}
                    className="rounded border border-border px-2 py-1"
                  >
                    {isAcked ? tk("acknowledged") : tk("acknowledge")}
                  </button>
                  <button
                    type="button"
                    onClick={() => toggle(setMutedIds, event.id)}
                    aria-label={t(`${EVENT_TYPE_LABEL[event.type]} をミュート`, `Mute ${EVENT_TYPE_LABEL[event.type]}`)}
                    className="rounded border border-border px-2 py-1"
                  >
                    {tk("mute")}
                  </button>
                  <button
                    type="button"
                    onClick={() => toggle(setPinnedIds, event.id)}
                    aria-pressed={isPinned}
                    className="rounded border border-border px-2 py-1"
                  >
                    {isPinned ? tk("pinned") : tk("pin")}
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </Card>
  );
}
