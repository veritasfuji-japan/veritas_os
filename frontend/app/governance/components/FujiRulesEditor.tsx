"use client";

import { Card } from "@veritas/design-system";
import type { FujiRules } from "@veritas/types";
import { useI18n } from "../../../components/i18n-provider";
import type { GovernancePolicyUI } from "../governance-types";
import { FUJI_LABELS } from "../constants";
import { ToggleRow } from "./ToggleRow";

interface FujiRulesEditorProps {
  draft: GovernancePolicyUI;
  isViewer: boolean;
  onUpdate: (updater: (prev: GovernancePolicyUI) => GovernancePolicyUI) => void;
}

export function FujiRulesEditor({ draft, isViewer, onUpdate }: FujiRulesEditorProps): JSX.Element {
  const { t } = useI18n();

  return (
    <Card title="FUJI rules / thresholds / escalation" titleSize="md" variant="elevated">
      <div className="grid gap-2 md:grid-cols-2">
        {(Object.keys(FUJI_LABELS) as (keyof FujiRules)[]).map((key) => (
          <ToggleRow key={key} label={FUJI_LABELS[key]} checked={draft.fuji_rules[key]} disabled={isViewer} onChange={(v) => onUpdate((prev) => ({ ...prev, fuji_rules: { ...prev.fuji_rules, [key]: v } }))} />
        ))}
      </div>

      <div className="mt-4">
        <p className="text-xs font-semibold mb-2">Risk Thresholds</p>
        <div className="grid gap-2 md:grid-cols-2">
          {(["allow_upper", "warn_upper", "human_review_upper", "deny_upper"] as const).map((field) => (
            <label key={field} className="text-xs">
              {field}{" "}
              <span className="font-mono text-muted-foreground">({draft.risk_thresholds[field].toFixed(2)})</span>
              <input
                aria-label={field}
                aria-valuetext={`${(draft.risk_thresholds[field] * 100).toFixed(0)}%`}
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={draft.risk_thresholds[field]}
                disabled={isViewer}
                onChange={(e) => onUpdate((prev) => ({ ...prev, risk_thresholds: { ...prev.risk_thresholds, [field]: Number(e.target.value) } }))}
                className="w-full"
              />
            </label>
          ))}
        </div>
      </div>

      <div className="mt-4">
        <p className="text-xs font-semibold mb-2">Auto-Stop / Escalation</p>
        <div className="grid gap-2 md:grid-cols-2">
          <ToggleRow label="Auto-Stop Enabled" checked={draft.auto_stop.enabled} disabled={isViewer} onChange={(v) => onUpdate((prev) => ({ ...prev, auto_stop: { ...prev.auto_stop, enabled: v } }))} />
          <label className="text-xs">
            max_risk_score{" "}
            <span className="font-mono text-muted-foreground">({draft.auto_stop.max_risk_score.toFixed(2)})</span>
            <input
              aria-label="max_risk_score"
              aria-valuetext={`${(draft.auto_stop.max_risk_score * 100).toFixed(0)}%`}
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={draft.auto_stop.max_risk_score}
              disabled={isViewer}
              onChange={(e) => onUpdate((prev) => ({ ...prev, auto_stop: { ...prev.auto_stop, max_risk_score: Number(e.target.value) } }))}
              className="w-full"
            />
          </label>
        </div>
      </div>

      <div className="mt-4">
        <p className="text-xs font-semibold mb-2">Log Retention / Audit</p>
        <div className="grid gap-2 md:grid-cols-2">
          <label className="text-xs">
            retention_days{" "}
            <span className="font-mono text-muted-foreground">({draft.log_retention.retention_days})</span>
            <input
              aria-label="retention_days"
              aria-valuetext={`${draft.log_retention.retention_days} ${t("日", "days")}`}
              type="range"
              min={1}
              max={365}
              step={1}
              value={draft.log_retention.retention_days}
              disabled={isViewer}
              onChange={(e) => onUpdate((prev) => ({ ...prev, log_retention: { ...prev.log_retention, retention_days: Number(e.target.value) } }))}
              className="w-full"
            />
          </label>
          <ToggleRow label="Redact Before Log" checked={draft.log_retention.redact_before_log} disabled={isViewer} onChange={(v) => onUpdate((prev) => ({ ...prev, log_retention: { ...prev.log_retention, redact_before_log: v } }))} />
        </div>
      </div>
    </Card>
  );
}
