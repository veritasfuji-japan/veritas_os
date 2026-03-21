"use client";

import { Card } from "@veritas/design-system";
import { useI18n } from "../../../components/i18n-provider";
import type { ApprovalStatus, PolicyActionMode } from "../governance-types";

interface ApplyFlowProps {
  hasChanges: boolean;
  saving: boolean;
  canApply: boolean;
  canOperate: boolean;
  draftApprovalStatus: ApprovalStatus;
  onApply: (mode: PolicyActionMode) => void;
  onRollback: () => void;
}

export function ApplyFlow({ hasChanges, saving, canApply, canOperate, draftApprovalStatus, onApply, onRollback }: ApplyFlowProps): JSX.Element {
  const { t } = useI18n();

  return (
    <Card title="Apply Flow" titleSize="md" variant="elevated">
      <div className="flex flex-wrap gap-2">
        <button type="button" className="rounded border px-3 py-2 text-sm" onClick={() => onApply("apply")} disabled={!hasChanges || saving || !canApply}>{t("適用", "apply")}</button>
        <button type="button" className="rounded border px-3 py-2 text-sm" onClick={() => onApply("dry-run")} disabled={!hasChanges || saving || !canOperate}>{t("ドライラン", "dry-run")}</button>
        <button type="button" className="rounded border px-3 py-2 text-sm" onClick={() => onApply("shadow")} disabled={saving || !canOperate}>{t("シャドウモード", "shadow mode")}</button>
        <button type="button" className="rounded border px-3 py-2 text-sm" onClick={onRollback} disabled={saving || !hasChanges || !canApply}>{t("ロールバック", "rollback")}</button>
      </div>
      {!canApply ? <p className="mt-2 text-xs text-warning">{t("RBAC: apply/rollback は admin のみ実行可能です。", "RBAC: apply/rollback requires admin role.")}</p> : null}
      {hasChanges && draftApprovalStatus !== "approved" ? <p className="mt-2 text-xs text-info">{t("apply するには先に承認が必要です。dry-run / shadow は承認前でも実行できます。", "Approval is required before apply. dry-run / shadow can be executed before approval.")}</p> : null}
    </Card>
  );
}
