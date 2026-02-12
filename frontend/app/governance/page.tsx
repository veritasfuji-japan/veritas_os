"use client";

import { useMemo, useState } from "react";
import { Card } from "@veritas/design-system";

const DEFAULT_API_BASE = process.env.NEXT_PUBLIC_VERITAS_API_BASE_URL ?? "http://localhost:8000";
const ENV_API_KEY = process.env.NEXT_PUBLIC_VERITAS_API_KEY ?? "";

type AuditIntensity = "light" | "standard" | "strict";

interface GovernancePolicy {
  fuji_enabled: boolean;
  risk_threshold: number;
  auto_stop_conditions: string[];
  log_retention_days: number;
  audit_intensity: AuditIntensity;
}

interface GovernanceResponse {
  ok: boolean;
  policy: GovernancePolicy;
  before?: GovernancePolicy;
}

const DEFAULT_POLICY: GovernancePolicy = {
  fuji_enabled: true,
  risk_threshold: 0.65,
  auto_stop_conditions: ["critical_fuji_violation", "trust_chain_break"],
  log_retention_days: 180,
  audit_intensity: "standard",
};

function policyPreview(policy: GovernancePolicy | null): string {
  if (!policy) {
    return "{}";
  }
  return JSON.stringify(policy, null, 2);
}

export default function GovernanceControlPage(): JSX.Element {
  const [apiBase, setApiBase] = useState(DEFAULT_API_BASE);
  const [apiKey, setApiKey] = useState(ENV_API_KEY);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentPolicy, setCurrentPolicy] = useState<GovernancePolicy | null>(null);
  const [beforePolicy, setBeforePolicy] = useState<GovernancePolicy | null>(null);

  const [fujiEnabled, setFujiEnabled] = useState(DEFAULT_POLICY.fuji_enabled);
  const [riskThreshold, setRiskThreshold] = useState(DEFAULT_POLICY.risk_threshold);
  const [autoStopRaw, setAutoStopRaw] = useState(DEFAULT_POLICY.auto_stop_conditions.join("\n"));
  const [logRetentionDays, setLogRetentionDays] = useState(DEFAULT_POLICY.log_retention_days);
  const [auditIntensity, setAuditIntensity] = useState<AuditIntensity>(DEFAULT_POLICY.audit_intensity);

  const diffPreview = useMemo(() => {
    const nextPolicy: GovernancePolicy = {
      fuji_enabled: fujiEnabled,
      risk_threshold: riskThreshold,
      auto_stop_conditions: autoStopRaw
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean),
      log_retention_days: logRetentionDays,
      audit_intensity: auditIntensity,
    };

    return {
      before: beforePolicy ?? currentPolicy,
      after: nextPolicy,
    };
  }, [auditIntensity, autoStopRaw, beforePolicy, currentPolicy, fujiEnabled, logRetentionDays, riskThreshold]);

  const applyPolicyToForm = (policy: GovernancePolicy): void => {
    setFujiEnabled(policy.fuji_enabled);
    setRiskThreshold(policy.risk_threshold);
    setAutoStopRaw(policy.auto_stop_conditions.join("\n"));
    setLogRetentionDays(policy.log_retention_days);
    setAuditIntensity(policy.audit_intensity);
  };

  const fetchPolicy = async (): Promise<void> => {
    setError(null);
    if (!apiKey.trim()) {
      setError("API key を入力してください。");
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`${apiBase.replace(/\/$/, "")}/v1/governance/policy`, {
        headers: {
          "X-API-Key": apiKey.trim(),
        },
      });

      if (!response.ok) {
        setError(`HTTP ${response.status}: policy 取得に失敗しました。`);
        return;
      }

      const payload = (await response.json()) as GovernanceResponse;
      setCurrentPolicy(payload.policy);
      setBeforePolicy(payload.policy);
      applyPolicyToForm(payload.policy);
    } catch {
      setError("ネットワークエラー: policy 取得に失敗しました。");
    } finally {
      setLoading(false);
    }
  };

  const updatePolicy = async (): Promise<void> => {
    setError(null);
    if (!apiKey.trim()) {
      setError("API key を入力してください。");
      return;
    }

    const policy: GovernancePolicy = {
      fuji_enabled: fujiEnabled,
      risk_threshold: Number(riskThreshold.toFixed(2)),
      auto_stop_conditions: autoStopRaw
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean),
      log_retention_days: logRetentionDays,
      audit_intensity: auditIntensity,
    };

    setLoading(true);
    try {
      const response = await fetch(`${apiBase.replace(/\/$/, "")}/v1/governance/policy`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": apiKey.trim(),
        },
        body: JSON.stringify({ policy }),
      });

      if (!response.ok) {
        setError(`HTTP ${response.status}: policy 更新に失敗しました。`);
        return;
      }

      const payload = (await response.json()) as GovernanceResponse;
      setBeforePolicy(payload.before ?? null);
      setCurrentPolicy(payload.policy);
      applyPolicyToForm(payload.policy);
    } catch {
      setError("ネットワークエラー: policy 更新に失敗しました。");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card title="Governance Control" className="border-primary/50 bg-surface/85">
        <p className="text-sm text-muted-foreground">
          FUJIの有効化、リスク閾値、自動停止条件、ログ保持/監査強度を統制プレーンで一元管理します。
        </p>
      </Card>

      <Card title="Connection" className="bg-background/75">
        <div className="grid gap-3 md:grid-cols-2">
          <label className="space-y-1 text-xs">
            <span className="font-medium">API Base URL</span>
            <input
              className="w-full rounded-md border border-border bg-background px-2 py-2"
              value={apiBase}
              onChange={(event) => setApiBase(event.target.value)}
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="font-medium">X-API-Key</span>
            <input
              className="w-full rounded-md border border-border bg-background px-2 py-2"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              type="password"
              autoComplete="off"
            />
          </label>
        </div>
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            className="rounded-md border border-primary/60 bg-primary/20 px-3 py-2 text-sm"
            onClick={() => void fetchPolicy()}
            disabled={loading}
          >
            現在ポリシー取得
          </button>
          <button
            type="button"
            className="rounded-md border border-border px-3 py-2 text-sm"
            onClick={() => void updatePolicy()}
            disabled={loading}
          >
            ポリシー更新
          </button>
        </div>
      </Card>

      {error ? <p className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-300">{error}</p> : null}

      <Card title="Policy Editor" className="bg-background/75">
        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-1 text-xs">
            <span className="font-medium">FUJI rule switch</span>
            <select
              className="w-full rounded-md border border-border bg-background px-2 py-2"
              value={fujiEnabled ? "enabled" : "disabled"}
              onChange={(event) => setFujiEnabled(event.target.value === "enabled")}
            >
              <option value="enabled">enabled</option>
              <option value="disabled">disabled</option>
            </select>
          </label>

          <label className="space-y-1 text-xs">
            <span className="font-medium">Risk threshold ({riskThreshold.toFixed(2)})</span>
            <input
              type="range"
              min="0"
              max="1"
              step="0.01"
              value={riskThreshold}
              onChange={(event) => setRiskThreshold(Number(event.target.value))}
              className="w-full"
            />
          </label>

          <label className="space-y-1 text-xs md:col-span-2">
            <span className="font-medium">Auto stop conditions (1行1条件)</span>
            <textarea
              value={autoStopRaw}
              onChange={(event) => setAutoStopRaw(event.target.value)}
              className="min-h-24 w-full rounded-md border border-border bg-background px-2 py-2"
            />
          </label>

          <label className="space-y-1 text-xs">
            <span className="font-medium">Log retention days</span>
            <input
              type="number"
              min={1}
              max={3650}
              value={logRetentionDays}
              onChange={(event) => setLogRetentionDays(Number(event.target.value))}
              className="w-full rounded-md border border-border bg-background px-2 py-2"
            />
          </label>

          <label className="space-y-1 text-xs">
            <span className="font-medium">Audit intensity</span>
            <select
              className="w-full rounded-md border border-border bg-background px-2 py-2"
              value={auditIntensity}
              onChange={(event) => setAuditIntensity(event.target.value as AuditIntensity)}
            >
              <option value="light">light</option>
              <option value="standard">standard</option>
              <option value="strict">strict</option>
            </select>
          </label>
        </div>
      </Card>

      <Card title="Diff Preview (before / after)" className="bg-background/75">
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-semibold">before</p>
            <pre className="overflow-x-auto rounded-md border border-border bg-background/70 p-3 text-xs">
              {policyPreview(diffPreview.before)}
            </pre>
          </div>
          <div>
            <p className="mb-2 text-xs font-semibold">after</p>
            <pre className="overflow-x-auto rounded-md border border-border bg-background/70 p-3 text-xs">
              {policyPreview(diffPreview.after)}
            </pre>
          </div>
        </div>
      </Card>
    </div>
  );
}
