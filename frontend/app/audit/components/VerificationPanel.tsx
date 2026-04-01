"use client";

import { Card } from "@veritas/design-system";
import { useI18n } from "../../../components/i18n-provider";
import { STATUS_DOT } from "../constants";
import type { TrustLogItem } from "@veritas/types";

interface VerificationPanelProps {
  decisionIds: string[];
  selectedDecisionId: string;
  selectedDecisionEntry: TrustLogItem | null;
  verificationMessage: string | null;
  onSelectedDecisionIdChange: (id: string) => void;
  onVerify: () => void;
}

export function VerificationPanel({
  decisionIds,
  selectedDecisionId,
  selectedDecisionEntry,
  verificationMessage,
  onSelectedDecisionIdChange,
  onVerify,
}: VerificationPanelProps): JSX.Element {
  const { t } = useI18n();

  const handleVerify = (): void => {
    if (!selectedDecisionEntry) {
      onVerify();
      return;
    }
    onVerify();
  };

  return (
    <Card
      title={t("TrustLog インタラクティブ検証", "TrustLog Interactive Verification")}
      titleSize="md"
      variant="elevated"
      accent="success"
    >
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <select
            aria-label={t("検証対象の意思決定ID", "Decision ID for verification")}
            className="rounded border border-border px-2 py-1 text-xs"
            value={selectedDecisionId}
            onChange={(e) => onSelectedDecisionIdChange(e.target.value)}
          >
            <option value="">{t("意思決定IDを選択", "Select a decision ID")}</option>
            {decisionIds.map((id) => (
              <option key={id} value={id}>{id}</option>
            ))}
          </select>
          <button
            type="button"
            className="rounded border border-primary/40 bg-primary/10 px-3 py-1.5 text-xs"
            onClick={handleVerify}
          >
            {t("ハッシュチェーン検証", "Verify hash chain")}
          </button>
        </div>
        {verificationMessage ? (
          <p className="text-xs">{verificationMessage}</p>
        ) : null}
        <div className="flex flex-wrap gap-2 text-2xs">
          {(["verified", "broken", "missing", "orphan"] as const).map((status) => (
            <span key={status} className="flex items-center gap-1">
              <span className={`inline-block h-2 w-2 rounded-full ${STATUS_DOT[status]}`} />
              {status}
            </span>
          ))}
        </div>
      </div>
    </Card>
  );
}
