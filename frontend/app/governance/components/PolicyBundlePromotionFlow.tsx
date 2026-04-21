"use client";

import { useMemo, useState } from "react";
import { Card } from "@veritas/design-system";
import { StatusBadge } from "../../../components/ui";
import { veritasFetch } from "../../../lib/api-client";

interface PolicyBundlePromotionFlowProps {
  canOperate: boolean;
}

type CanonicalBindOutcome =
  | "COMMITTED"
  | "BLOCKED"
  | "ESCALATED"
  | "ROLLED_BACK"
  | "APPLY_FAILED"
  | "SNAPSHOT_FAILED"
  | "PRECONDITION_FAILED";
type BindOutcomeDisplay = CanonicalBindOutcome | "UNKNOWN";

type BindCheckSummary = "PASS" | "FAIL" | "UNKNOWN";
type BindCheckKey =
  | "authority_check_result"
  | "constraint_check_result"
  | "drift_check_result"
  | "risk_check_result";

type BindCheckPayload = {
  passed?: boolean;
  result?: string;
  reason_code?: string;
};

type BindReceiptPayload = Record<string, unknown> & Partial<Record<BindCheckKey, BindCheckPayload>>;

interface PromoteResponse {
  ok: boolean;
  bind_outcome?: CanonicalBindOutcome;
  bind_failure_reason?: string;
  bind_reason_code?: string;
  bind_receipt_id?: string;
  execution_intent_id?: string;
  authority_check_result?: BindCheckPayload;
  constraint_check_result?: BindCheckPayload;
  drift_check_result?: BindCheckPayload;
  risk_check_result?: BindCheckPayload;
  bind_receipt?: BindReceiptPayload;
  error?: string;
}

interface BindReceiptResponse {
  ok: boolean;
  bind_receipt?: BindReceiptPayload;
  bind_outcome?: CanonicalBindOutcome;
  bind_failure_reason?: string;
  bind_reason_code?: string;
  bind_receipt_id?: string;
  execution_intent_id?: string;
  authority_check_result?: BindCheckPayload;
  constraint_check_result?: BindCheckPayload;
  drift_check_result?: BindCheckPayload;
  risk_check_result?: BindCheckPayload;
  error?: string;
}

const CANONICAL_BIND_OUTCOMES: ReadonlySet<CanonicalBindOutcome> = new Set([
  "COMMITTED",
  "BLOCKED",
  "ESCALATED",
  "ROLLED_BACK",
  "APPLY_FAILED",
  "SNAPSHOT_FAILED",
  "PRECONDITION_FAILED",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseBindCheckPayload(value: unknown): BindCheckPayload | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const payload: BindCheckPayload = {
    passed: typeof value.passed === "boolean" ? value.passed : undefined,
    result: typeof value.result === "string" ? value.result : undefined,
    reason_code: typeof value.reason_code === "string" ? value.reason_code : undefined,
  };
  if (payload.passed === undefined && payload.result === undefined && payload.reason_code === undefined) {
    return undefined;
  }
  return payload;
}

function parseBindReceiptPayload(value: unknown): BindReceiptPayload | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const receipt: BindReceiptPayload = { ...value };
  const keys: BindCheckKey[] = [
    "authority_check_result",
    "constraint_check_result",
    "drift_check_result",
    "risk_check_result",
  ];
  for (const key of keys) {
    const parsed = parseBindCheckPayload(value[key]);
    if (parsed) {
      receipt[key] = parsed;
      continue;
    }
    delete receipt[key];
  }
  return receipt;
}

function parsePromoteResponse(value: unknown): PromoteResponse | null {
  if (!isRecord(value) || typeof value.ok !== "boolean") {
    return null;
  }
  return {
    ok: value.ok,
    bind_outcome: normalizeBindOutcome(value.bind_outcome) ?? undefined,
    bind_failure_reason: typeof value.bind_failure_reason === "string" ? value.bind_failure_reason : undefined,
    bind_reason_code: typeof value.bind_reason_code === "string" ? value.bind_reason_code : undefined,
    bind_receipt_id: typeof value.bind_receipt_id === "string" ? value.bind_receipt_id : undefined,
    execution_intent_id: typeof value.execution_intent_id === "string" ? value.execution_intent_id : undefined,
    authority_check_result: parseBindCheckPayload(value.authority_check_result),
    constraint_check_result: parseBindCheckPayload(value.constraint_check_result),
    drift_check_result: parseBindCheckPayload(value.drift_check_result),
    risk_check_result: parseBindCheckPayload(value.risk_check_result),
    bind_receipt: parseBindReceiptPayload(value.bind_receipt),
    error: typeof value.error === "string" ? value.error : undefined,
  };
}

function parseBindReceiptResponse(value: unknown): BindReceiptResponse | null {
  if (!isRecord(value) || typeof value.ok !== "boolean") {
    return null;
  }
  const bindReceipt = parseBindReceiptPayload(value.bind_receipt);
  return {
    ok: value.ok,
    bind_receipt: bindReceipt,
    bind_outcome:
      normalizeBindOutcome(value.bind_outcome) ?? normalizeBindOutcome(bindReceipt?.final_outcome) ?? undefined,
    bind_failure_reason: typeof value.bind_failure_reason === "string" ? value.bind_failure_reason : undefined,
    bind_reason_code: typeof value.bind_reason_code === "string" ? value.bind_reason_code : undefined,
    bind_receipt_id: typeof value.bind_receipt_id === "string" ? value.bind_receipt_id : undefined,
    execution_intent_id: typeof value.execution_intent_id === "string" ? value.execution_intent_id : undefined,
    authority_check_result: parseBindCheckPayload(value.authority_check_result),
    constraint_check_result: parseBindCheckPayload(value.constraint_check_result),
    drift_check_result: parseBindCheckPayload(value.drift_check_result),
    risk_check_result: parseBindCheckPayload(value.risk_check_result),
    error: typeof value.error === "string" ? value.error : undefined,
  };
}

function normalizeBindOutcome(outcome: unknown): CanonicalBindOutcome | null {
  if (typeof outcome !== "string") {
    return null;
  }
  const normalized = outcome.trim().toUpperCase();
  if (normalized === "SUCCESS") {
    return "COMMITTED";
  }
  return CANONICAL_BIND_OUTCOMES.has(normalized as CanonicalBindOutcome)
    ? (normalized as CanonicalBindOutcome)
    : null;
}

function resolveOutcomeVariant(outcome: BindOutcomeDisplay): "success" | "warning" | "danger" | "muted" {
  if (outcome === "COMMITTED") {
    return "success";
  }
  if (outcome === "BLOCKED" || outcome === "ROLLED_BACK" || outcome === "PRECONDITION_FAILED") {
    return "warning";
  }
  if (outcome === "ESCALATED" || outcome === "APPLY_FAILED" || outcome === "SNAPSHOT_FAILED") {
    return "danger";
  }
  return "muted";
}

function summarizeBindCheck(value: BindCheckPayload | undefined): BindCheckSummary {
  if (!value) {
    return "UNKNOWN";
  }
  if (value.passed !== undefined) {
    return value.passed ? "PASS" : "FAIL";
  }
  if (value.result) {
    const result = value.result.trim().toUpperCase();
    if (result === "PASS" || result === "OK" || result === "ALLOW") {
      return "PASS";
    }
    if (result === "FAIL" || result === "DENY" || result === "BLOCK") {
      return "FAIL";
    }
  }
  return "UNKNOWN";
}

function resolveCheckResult(
  result: PromoteResponse | null,
  receipt: BindReceiptResponse | null,
  key: BindCheckKey,
): BindCheckSummary {
  const fromResult = summarizeBindCheck(result?.[key]);
  if (fromResult !== "UNKNOWN") {
    return fromResult;
  }
  const fromReceiptTop = summarizeBindCheck(receipt?.[key]);
  if (fromReceiptTop !== "UNKNOWN") {
    return fromReceiptTop;
  }
  const fromReceipt = summarizeBindCheck(receipt?.bind_receipt?.[key]);
  return fromReceipt;
}

/**
 * Compact operator-facing workflow to submit policy bundle promotion
 * using the existing governance promote endpoint and inspect bind lineage.
 */
export function PolicyBundlePromotionFlow({ canOperate }: PolicyBundlePromotionFlowProps): JSX.Element {
  const [bundleId, setBundleId] = useState("");
  const [bundleDirName, setBundleDirName] = useState("");
  const [decisionId, setDecisionId] = useState("");
  const [requestId, setRequestId] = useState("");
  const [policySnapshotId, setPolicySnapshotId] = useState("");
  const [decisionHash, setDecisionHash] = useState("");
  const [approvalContextText, setApprovalContextText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PromoteResponse | null>(null);
  const [receiptLoading, setReceiptLoading] = useState(false);
  const [receiptError, setReceiptError] = useState<string | null>(null);
  const [receiptDetail, setReceiptDetail] = useState<BindReceiptResponse | null>(null);

  const selectorError = useMemo(() => {
    const hasBundleId = bundleId.trim().length > 0;
    const hasBundleDirName = bundleDirName.trim().length > 0;
    if (hasBundleId && hasBundleDirName) {
      return "bundle_id と bundle_dir_name は同時に指定できません。";
    }
    if (!hasBundleId && !hasBundleDirName) {
      return "bundle_id または bundle_dir_name のどちらか1つが必須です。";
    }
    const selected = hasBundleId ? bundleId.trim() : bundleDirName.trim();
    if ([".", ".."].includes(selected) || selected.includes("/") || selected.includes("\\")) {
      return "bundle selector に path 文字は使えません。";
    }
    return null;
  }, [bundleDirName, bundleId]);

  const canonicalOutcome = result?.bind_outcome ?? "UNKNOWN";

  const handleSubmit = async (): Promise<void> => {
    setError(null);
    setReceiptDetail(null);
    setReceiptError(null);

    if (!canOperate) {
      setError("RBAC: promotion は operator 以上のみ実行可能です。");
      return;
    }
    if (selectorError) {
      return;
    }
    if (!decisionId.trim() || !requestId.trim() || !policySnapshotId.trim() || !decisionHash.trim()) {
      setError("decision_id / request_id / policy_snapshot_id / decision_hash は必須です。");
      return;
    }

    let approvalContext: Record<string, unknown> | undefined;
    const trimmedApprovalContext = approvalContextText.trim();
    if (trimmedApprovalContext.length > 0) {
      try {
        const parsed: unknown = JSON.parse(trimmedApprovalContext);
        if (!isRecord(parsed)) {
          setError("approval_context は JSON object で入力してください。");
          return;
        }
        approvalContext = parsed;
      } catch {
        setError("approval_context は有効な JSON を入力してください。");
        return;
      }
    }

    const payload: Record<string, unknown> = {
      decision_id: decisionId.trim(),
      request_id: requestId.trim(),
      policy_snapshot_id: policySnapshotId.trim(),
      decision_hash: decisionHash.trim(),
    };

    if (bundleId.trim()) {
      payload.bundle_id = bundleId.trim();
    }
    if (bundleDirName.trim()) {
      payload.bundle_dir_name = bundleDirName.trim();
    }
    if (approvalContext) {
      payload.approval_context = approvalContext;
    }

    setSubmitting(true);
    try {
      const response = await veritasFetch("/api/veritas/v1/governance/policy-bundles/promote", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      const data = parsePromoteResponse(await response.json());
      if (!response.ok) {
        setResult(data);
        setError(data?.error ?? `HTTP ${response.status}: promotion の実行に失敗しました。`);
        return;
      }
      if (!data) {
        setError("promotion レスポンスの形式が不正です。");
        return;
      }
      setResult(data);
    } catch (caught: unknown) {
      const message = caught instanceof Error ? caught.message : "Network error";
      setError(`promotion request failed: ${message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleLoadReceipt = async (): Promise<void> => {
    if (!result?.bind_receipt_id) {
      return;
    }
    setReceiptError(null);
    setReceiptLoading(true);
    try {
      const response = await veritasFetch(
        `/api/veritas/v1/governance/bind-receipts/${encodeURIComponent(result.bind_receipt_id)}`,
      );
      const data = parseBindReceiptResponse(await response.json());
      if (!response.ok || !data) {
        setReceiptError(data?.error ?? `HTTP ${response.status}: bind receipt の取得に失敗しました。`);
        return;
      }
      setReceiptDetail(data);
    } catch (caught: unknown) {
      const message = caught instanceof Error ? caught.message : "Network error";
      setReceiptError(`bind receipt request failed: ${message}`);
    } finally {
      setReceiptLoading(false);
    }
  };

  return (
    <Card title="Policy Bundle Promotion" titleSize="md" variant="elevated" accent="info">
      <div className="space-y-3 text-xs">
        <p className="text-muted-foreground">
          Existing bind-boundary endpoint を使って promotion を実行し、bind outcome / receipt lineage を追跡します。
        </p>

        <div className="grid gap-3 md:grid-cols-2">
          <label className="space-y-1">
            <span>bundle_id</span>
            <input
              aria-label="bundle_id"
              type="text"
              value={bundleId}
              onChange={(event) => setBundleId(event.target.value.slice(0, 128))}
              className="w-full rounded border px-2 py-1"
              placeholder="bundle-2026-04"
              disabled={!canOperate || submitting}
            />
          </label>
          <label className="space-y-1">
            <span>bundle_dir_name</span>
            <input
              aria-label="bundle_dir_name"
              type="text"
              value={bundleDirName}
              onChange={(event) => setBundleDirName(event.target.value.slice(0, 128))}
              className="w-full rounded border px-2 py-1"
              placeholder="policy_bundle_prod"
              disabled={!canOperate || submitting}
            />
          </label>
          <label className="space-y-1">
            <span>decision_id</span>
            <input aria-label="decision_id" type="text" value={decisionId} onChange={(event) => setDecisionId(event.target.value.slice(0, 128))} className="w-full rounded border px-2 py-1" disabled={!canOperate || submitting} />
          </label>
          <label className="space-y-1">
            <span>request_id</span>
            <input aria-label="request_id" type="text" value={requestId} onChange={(event) => setRequestId(event.target.value.slice(0, 128))} className="w-full rounded border px-2 py-1" disabled={!canOperate || submitting} />
          </label>
          <label className="space-y-1">
            <span>policy_snapshot_id</span>
            <input aria-label="policy_snapshot_id" type="text" value={policySnapshotId} onChange={(event) => setPolicySnapshotId(event.target.value.slice(0, 128))} className="w-full rounded border px-2 py-1" disabled={!canOperate || submitting} />
          </label>
          <label className="space-y-1">
            <span>decision_hash</span>
            <input aria-label="decision_hash" type="text" value={decisionHash} onChange={(event) => setDecisionHash(event.target.value.slice(0, 128))} className="w-full rounded border px-2 py-1" disabled={!canOperate || submitting} />
          </label>
        </div>

        <label className="space-y-1 block">
          <span>approval_context (optional JSON)</span>
          <textarea
            aria-label="approval_context"
            value={approvalContextText}
            onChange={(event) => setApprovalContextText(event.target.value.slice(0, 5000))}
            className="min-h-[88px] w-full rounded border px-2 py-1 font-mono"
            placeholder='{"ticket_id":"GOV-123"}'
            disabled={!canOperate || submitting}
          />
        </label>

        {selectorError ? (
          <p className="rounded border border-warning/30 bg-warning/10 px-2 py-1 text-warning-foreground">{selectorError}</p>
        ) : null}
        {!canOperate ? (
          <p className="rounded border border-warning/30 bg-warning/10 px-2 py-1 text-warning-foreground">
            RBAC: promotion は operator または admin ロールが必要です。
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="rounded border px-3 py-1.5"
            onClick={() => void handleSubmit()}
            disabled={!canOperate || submitting}
          >
            {submitting ? "promoting..." : "promote bundle"}
          </button>
          {result?.bind_receipt_id ? (
            <button
              type="button"
              className="rounded border px-3 py-1.5"
              onClick={() => void handleLoadReceipt()}
              disabled={receiptLoading}
            >
              {receiptLoading ? "loading receipt..." : receiptDetail ? "reload bind receipt detail" : "load bind receipt detail"}
            </button>
          ) : null}
          {result?.bind_receipt_id ? (
            <a className="rounded border px-3 py-1.5" href={`/audit?bind_receipt_id=${encodeURIComponent(result.bind_receipt_id)}`}>
              open TrustLog Explorer
            </a>
          ) : null}
        </div>

        {error ? (
          <p className="rounded border border-danger/30 bg-danger/10 px-2 py-1 text-danger">{error}</p>
        ) : null}

        {result ? (
          <div className="space-y-2 rounded border p-3">
            <div className="flex items-center gap-2">
              <span className="font-semibold">Promotion Result</span>
              <StatusBadge label={canonicalOutcome} variant={resolveOutcomeVariant(canonicalOutcome)} />
            </div>
            <div className="grid gap-1 md:grid-cols-2">
              <p>bind_outcome: <span className="font-mono">{canonicalOutcome}</span></p>
              <p>bind_reason_code: <span className="font-mono">{result.bind_reason_code ?? "-"}</span></p>
              <p className="md:col-span-2">bind_failure_reason: <span className="font-mono">{result.bind_failure_reason ?? "-"}</span></p>
              <p>
                bind_receipt_id:{" "}
                {result.bind_receipt_id ? (
                  <a
                    className="font-mono underline underline-offset-2"
                    href={`/audit?bind_receipt_id=${encodeURIComponent(result.bind_receipt_id)}`}
                  >
                    {result.bind_receipt_id}
                  </a>
                ) : (
                  <span className="font-mono">-</span>
                )}
              </p>
              <p>execution_intent_id: <span className="font-mono">{result.execution_intent_id ?? "-"}</span></p>
            </div>

            <div className="rounded border border-muted p-2">
              <p className="font-semibold">bind check summary</p>
              <div className="mt-1 grid gap-1 md:grid-cols-2">
                <p>authority: <span className="font-mono">{resolveCheckResult(result, receiptDetail, "authority_check_result")}</span></p>
                <p>constraints: <span className="font-mono">{resolveCheckResult(result, receiptDetail, "constraint_check_result")}</span></p>
                <p>drift: <span className="font-mono">{resolveCheckResult(result, receiptDetail, "drift_check_result")}</span></p>
                <p>risk: <span className="font-mono">{resolveCheckResult(result, receiptDetail, "risk_check_result")}</span></p>
              </div>
            </div>

            {receiptDetail ? (
              <p className="text-muted-foreground">bind receipt detail loaded</p>
            ) : null}
          </div>
        ) : null}

        {receiptError ? (
          <p className="rounded border border-danger/30 bg-danger/10 px-2 py-1 text-danger">{receiptError}</p>
        ) : null}

        {receiptDetail?.bind_receipt ? (
          <details className="rounded border p-2">
            <summary className="cursor-pointer font-semibold">bind receipt detail</summary>
            <pre className="mt-2 overflow-x-auto rounded bg-muted/20 p-2 text-[11px]">{JSON.stringify(receiptDetail.bind_receipt, null, 2)}</pre>
          </details>
        ) : null}
      </div>
    </Card>
  );
}
