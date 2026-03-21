"use client";

import { Card } from "@veritas/design-system";
import { useI18n } from "../../../components/i18n-provider";
import { StatusBadge } from "../../../components/ui";
import type { ApprovalStatus, GovernancePolicyUI } from "../governance-types";
import { APPROVAL_STATUS_ACCENT } from "../constants";

interface PolicyMetaPanelProps {
  savedPolicy: GovernancePolicyUI | null;
  draft: GovernancePolicyUI;
  draftApprovalStatus: ApprovalStatus;
  hasChanges: boolean;
  changeCount: number;
}

export function PolicyMetaPanel({ savedPolicy, draft, draftApprovalStatus, hasChanges, changeCount }: PolicyMetaPanelProps): JSX.Element {
  const { t } = useI18n();

  return (
    <Card title="Policy Meta" titleSize="md" variant="elevated" accent={APPROVAL_STATUS_ACCENT[draftApprovalStatus]}>
      <div className="grid gap-3 text-xs md:grid-cols-2 lg:grid-cols-3">
        <div className="rounded-lg border px-3 py-2">
          <p className="text-muted-foreground">Current Version</p>
          <p className="font-mono font-semibold">{savedPolicy?.version ?? "N/A"}</p>
        </div>
        <div className="rounded-lg border px-3 py-2">
          <p className="text-muted-foreground">Draft Version</p>
          <p className="font-mono font-semibold">{draft.draft_version ?? "N/A"}</p>
        </div>
        <div className="rounded-lg border px-3 py-2">
          <p className="text-muted-foreground">Approval Status</p>
          <StatusBadge label={draftApprovalStatus} variant={APPROVAL_STATUS_ACCENT[draftApprovalStatus]} />
        </div>
        <div className="rounded-lg border px-3 py-2">
          <p className="text-muted-foreground">updated_by</p>
          <p className="font-mono font-semibold">{draft.updated_by}</p>
        </div>
        <div className="rounded-lg border px-3 py-2">
          <p className="text-muted-foreground">effective_at</p>
          <p className="font-mono font-semibold">{draft.effective_at ?? "N/A"}</p>
        </div>
        <div className="rounded-lg border px-3 py-2">
          <p className="text-muted-foreground">last_applied</p>
          <p className="font-mono font-semibold">{draft.last_applied ?? "N/A"}</p>
        </div>
      </div>
      {hasChanges ? (
        <p className="mt-2 text-xs text-warning">{t(`${changeCount} 件の未適用変更があります。適用前に承認してください。`, `${changeCount} unapplied change(s). Approve before applying.`)}</p>
      ) : null}
    </Card>
  );
}
