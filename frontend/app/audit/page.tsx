"use client";

import { useEffect, useMemo, useState } from "react";
import { Card } from "@veritas/design-system";
import { isRequestLogResponse, isTrustLogsResponse, type RequestLogResponse, type TrustLogItem } from "../../lib/api-validators";
import { useI18n } from "../../components/i18n-provider";

const DEFAULT_API_BASE = process.env.NEXT_PUBLIC_VERITAS_API_BASE_URL ?? "http://localhost:8000";
const ENV_API_KEY = process.env.NEXT_PUBLIC_VERITAS_API_KEY ?? "";
const PAGE_LIMIT = 50;

function toPrettyJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function shortHash(value: string | undefined): string {
  if (!value) {
    return "missing";
  }

  if (value.length <= 16) {
    return value;
  }

  return `${value.slice(0, 10)}...${value.slice(-6)}`;
}

type VerificationStatus = "idle" | "running" | "pass" | "fail";

export default function TrustLogExplorerPage(): JSX.Element {
  const { t } = useI18n();
  const [apiBase, setApiBase] = useState(DEFAULT_API_BASE);
  const [apiKey, setApiKey] = useState(ENV_API_KEY);
  const [cursor, setCursor] = useState<string | null>(null);
  const [items, setItems] = useState<TrustLogItem[]>([]);
  const [selected, setSelected] = useState<TrustLogItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [requestId, setRequestId] = useState("");
  const [requestResult, setRequestResult] = useState<RequestLogResponse | null>(null);
  const [stageFilter, setStageFilter] = useState("ALL");
  const [selectedDecisionId, setSelectedDecisionId] = useState("");
  const [verificationStatus, setVerificationStatus] = useState<VerificationStatus>("idle");
  const [verificationMessage, setVerificationMessage] = useState<string | null>(null);
  const [animationStep, setAnimationStep] = useState(0);

  const stageOptions = useMemo(() => {
    const stages = new Set<string>();
    for (const item of items) {
      const stage = typeof item.stage === "string" ? item.stage : "UNKNOWN";
      stages.add(stage);
    }
    return ["ALL", ...Array.from(stages).sort()];
  }, [items]);

  const filteredItems = useMemo(() => {
    if (stageFilter === "ALL") {
      return items;
    }
    return items.filter((item) => item.stage === stageFilter);
  }, [items, stageFilter]);

  const decisionIds = useMemo(() => {
    const ids = new Set<string>();
    for (const item of items) {
      if (typeof item.request_id === "string" && item.request_id.length > 0) {
        ids.add(item.request_id);
      }
    }
    return Array.from(ids).sort();
  }, [items]);

  const selectedDecisionEntry = useMemo(() => {
    if (!selectedDecisionId) {
      return null;
    }

    return items.find((item) => item.request_id === selectedDecisionId) ?? null;
  }, [items, selectedDecisionId]);

  const previousEntry = useMemo(() => {
    if (!selectedDecisionEntry) {
      return null;
    }

    const selectedIndex = items.findIndex((item) => item === selectedDecisionEntry);
    if (selectedIndex < 0 || selectedIndex >= items.length - 1) {
      return null;
    }
    return items[selectedIndex + 1] ?? null;
  }, [items, selectedDecisionEntry]);

  useEffect(() => {
    if (verificationStatus !== "running") {
      return undefined;
    }

    const timer = window.setInterval(() => {
      setAnimationStep((current) => {
        if (current >= 2) {
          return 2;
        }
        return current + 1;
      });
    }, 400);

    return () => {
      window.clearInterval(timer);
    };
  }, [verificationStatus]);

  const verifySelectedDecision = (): void => {
    setVerificationMessage(null);
    if (!selectedDecisionEntry) {
      setVerificationStatus("fail");
      setVerificationMessage(t("意思決定IDを選択してください。", "Please select a decision ID."));
      return;
    }

    if (!selectedDecisionEntry.sha256) {
      setVerificationStatus("fail");
      setVerificationMessage(t("選択ログに sha256 がありません。", "The selected log has no sha256."));
      return;
    }

    if (!previousEntry || !previousEntry.sha256) {
      setVerificationStatus("fail");
      setVerificationMessage(t("直前ログが見つからないため検証できません。", "Cannot verify without a previous log entry."));
      return;
    }

    setVerificationStatus("running");
    setAnimationStep(0);

    window.setTimeout(() => {
      const isTamperProof = selectedDecisionEntry.sha256_prev === previousEntry.sha256;
      setVerificationStatus(isTamperProof ? "pass" : "fail");
      setVerificationMessage(
        isTamperProof
          ? t("ハッシュチェーン整合: 改ざんは検出されませんでした。", "Hash chain verified: no tampering detected.")
          : t("ハッシュ不一致: 改ざんの可能性があります。", "Hash mismatch: potential tampering detected."),
      );
    }, 1400);
  };

  const loadLogs = async (nextCursor: string | null, replace: boolean): Promise<void> => {
    setError(null);
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: String(PAGE_LIMIT) });
      if (nextCursor) {
        params.set("cursor", nextCursor);
      }

      const response = await fetch(`${apiBase.replace(/\/$/, "")}/v1/trust/logs?${params.toString()}`, {
        headers: {
          "X-API-Key": apiKey.trim(),
        },
      });

      if (!response.ok) {
        setError(`HTTP ${response.status}: ${t("trust logs取得に失敗しました。", "Failed to fetch trust logs.")}`);
        return;
      }

      const payload: unknown = await response.json();
      if (!isTrustLogsResponse(payload)) {
        setError(t("レスポンス形式エラー: trust logs の形式が不正です。", "Response format error: trust logs payload is invalid."));
        return;
      }
      const nextItems = payload.items;
      setItems((prev) => (replace ? nextItems : [...prev, ...nextItems]));
      setCursor(payload.next_cursor);
      setHasMore(Boolean(payload.has_more));
      if (replace && nextItems.length > 0) {
        setSelected(nextItems[0]);
      }
    } catch {
      setError(t("ネットワークエラー: trust logs 取得に失敗しました。", "Network error: failed to fetch trust logs."));
    } finally {
      setLoading(false);
    }
  };

  const searchByRequestId = async (): Promise<void> => {
    const value = requestId.trim();
    setRequestResult(null);
    setError(null);
    if (!value) {
      setError(t("request_id を入力してください。", "Please enter request_id."));
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`${apiBase.replace(/\/$/, "")}/v1/trust/${encodeURIComponent(value)}`, {
        headers: {
          "X-API-Key": apiKey.trim(),
        },
      });

      if (!response.ok) {
        setError(`HTTP ${response.status}: ${t("request_id 検索に失敗しました。", "Failed to search request_id.")}`);
        return;
      }

      const payload: unknown = await response.json();
      if (!isRequestLogResponse(payload)) {
        setError(t("レスポンス形式エラー: request_id 応答の形式が不正です。", "Response format error: request_id payload is invalid."));
        return;
      }
      setRequestResult(payload);
      if (payload.items.length > 0) {
        setSelected(payload.items[payload.items.length - 1]);
      }
    } catch {
      setError(t("ネットワークエラー: request_id 検索に失敗しました。", "Network error: failed to search request_id."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card title="TrustLog Explorer" className="border-primary/50 bg-surface/85">
        <p className="text-sm text-muted-foreground">
          {t(
            "/v1/trust/logs と /v1/trust/{request_id} を使って、監査証跡を時系列に確認します。",
            "Use /v1/trust/logs and /v1/trust/{request_id} to review audit evidence in chronological order.",
          )}
        </p>
      </Card>

      <Card title="Connection" className="bg-background/75">
        <div className="grid gap-3 md:grid-cols-2">
          <label className="space-y-1 text-xs">
            <span className="font-medium">API Base URL</span>
            <input className="w-full rounded-md border border-border bg-background px-2 py-2" value={apiBase} onChange={(event) => setApiBase(event.target.value)} />
          </label>
          <label className="space-y-1 text-xs">
            <span className="font-medium">X-API-Key</span>
            <input className="w-full rounded-md border border-border bg-background px-2 py-2" value={apiKey} onChange={(event) => setApiKey(event.target.value)} type="password" autoComplete="off" />
          </label>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" className="rounded-md border border-primary/60 bg-primary/20 px-3 py-2 text-sm" disabled={loading || !apiKey.trim()} onClick={() => void loadLogs(null, true)}>
            {t("最新ログを読み込み", "Load latest logs")}
          </button>
          <button type="button" className="rounded-md border border-border px-3 py-2 text-sm" disabled={loading || !hasMore || !cursor || !apiKey.trim()} onClick={() => void loadLogs(cursor, false)}>
            {t("さらに読み込む", "Load more")}
          </button>
        </div>
      </Card>

      <Card title={t("request_id 検索", "request_id Search")} className="bg-background/75">
        <div className="flex flex-col gap-2 md:flex-row">
          <input aria-label="request_id" className="w-full rounded-md border border-border bg-background px-2 py-2 text-sm" placeholder="request_id" value={requestId} onChange={(event) => setRequestId(event.target.value)} />
          <button type="button" className="rounded-md border border-primary/60 bg-primary/20 px-3 py-2 text-sm" disabled={loading || !apiKey.trim()} onClick={() => void searchByRequestId()}>
            {t("検索", "Search")}
          </button>
        </div>
        {requestResult ? <p className="mt-2 text-xs text-muted-foreground">count: {requestResult.count} / chain_ok: {String(requestResult.chain_ok)} / verification_result: {requestResult.verification_result}</p> : null}
      </Card>

      {error ? <p className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-300">{error}</p> : null}

      <Card title="Timeline" className="bg-background/75">
        <div className="mb-3 flex items-center gap-2 text-xs">
          <label htmlFor="stage-filter" className="font-medium">{t("ステージフィルタ", "Stage filter")}</label>
          <select id="stage-filter" className="rounded-md border border-border bg-background px-2 py-1" value={stageFilter} onChange={(event) => setStageFilter(event.target.value)}>
            {stageOptions.map((stage) => (<option key={stage} value={stage}>{stage}</option>))}
          </select>
          <span className="text-muted-foreground">{t("表示件数", "Visible")}: {filteredItems.length}</span>
        </div>

        <ol className="max-h-[520px] space-y-2 overflow-y-auto border-l border-border pl-4">
          {filteredItems.map((item, index) => {
            const id = `${item.request_id ?? "unknown"}-${index}`;
            const isSelected = selected === item;
            return (
              <li key={id}>
                <button
                  type="button"
                  className={`w-full rounded-md border px-3 py-2 text-left text-xs ${isSelected ? "border-primary/60 bg-primary/15" : "border-border bg-background/60"}`}
                  onClick={() => setSelected(item)}
                >
                  <p className="font-semibold">{item.stage ?? "UNKNOWN"}</p>
                  <p className="text-muted-foreground">{item.created_at ?? "no timestamp"}</p>
                  <p className="truncate text-muted-foreground">request_id: {item.request_id ?? "unknown"}</p>
                </button>
              </li>
            );
          })}
        </ol>
      </Card>

      <Card title="Selected JSON" className="bg-background/75">
        {selected ? (
          <details open>
            <summary className="cursor-pointer text-sm font-semibold">{t("JSON 展開", "Expand JSON")}</summary>
            <pre className="mt-2 overflow-x-auto rounded-md border border-border bg-background/70 p-3 text-xs">{toPrettyJson(selected)}</pre>
          </details>
        ) : (
          <p className="text-sm text-muted-foreground">{t("ログを選択してください。", "Select a log.")}</p>
        )}
      </Card>

      <Card title={t("TrustLog インタラクティブ検証", "TrustLog Interactive Verification")} className="bg-background/75">
        <div className="space-y-3 text-sm">
          <div className="flex flex-col gap-2 md:flex-row md:items-end">
            <label className="flex-1 space-y-1 text-xs">
              <span className="font-medium">{t("意思決定ID", "Decision ID")}</span>
              <select
                className="w-full rounded-md border border-border bg-background px-2 py-2 text-sm"
                value={selectedDecisionId}
                onChange={(event) => setSelectedDecisionId(event.target.value)}
              >
                <option value="">{t("選択してください", "Select one")}</option>
                {decisionIds.map((id) => (
                  <option key={id} value={id}>{id}</option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="rounded-md border border-primary/60 bg-primary/20 px-3 py-2 text-sm"
              disabled={loading || !apiKey.trim() || !selectedDecisionId}
              onClick={verifySelectedDecision}
            >
              {t("ハッシュチェーン検証", "Verify hash chain")}
            </button>
          </div>

          <div className="rounded-md border border-border bg-background/60 p-3">
            <p className="font-medium">{t("検証アニメーション", "Verification animation")}</p>
            <div className="mt-2 flex items-center gap-2 text-xs">
              <span className={`rounded border px-2 py-1 ${animationStep >= 1 ? "border-primary/60 bg-primary/15" : "border-border bg-background"}`}>
                {t("直前ログ", "Previous log")}: {shortHash(previousEntry?.sha256)}
              </span>
              <span aria-hidden="true" className={animationStep >= 2 ? "text-primary" : "text-muted-foreground"}>→</span>
              <span className={`rounded border px-2 py-1 ${animationStep >= 2 ? "border-primary/60 bg-primary/15" : "border-border bg-background"}`}>
                {t("sha256_prev", "sha256_prev")}: {shortHash(selectedDecisionEntry?.sha256_prev)}
              </span>
              <span aria-hidden="true" className={animationStep >= 2 ? "text-primary" : "text-muted-foreground"}>→</span>
              <span className="rounded border border-border bg-background px-2 py-1">
                {t("現在ログ", "Current log")}: {shortHash(selectedDecisionEntry?.sha256)}
              </span>
            </div>
          </div>

          {verificationStatus === "pass" ? (
            <p className="inline-flex w-fit rounded-full border border-emerald-500/60 bg-emerald-500/15 px-3 py-1 text-xs font-semibold text-emerald-300">
              TAMPER-PROOF ✅
            </p>
          ) : null}

          {verificationMessage ? (
            <p className={`rounded-md border p-2 text-xs ${verificationStatus === "pass" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" : "border-amber-500/40 bg-amber-500/10 text-amber-200"}`}>
              {verificationMessage}
            </p>
          ) : null}
        </div>
      </Card>
    </div>
  );
}
