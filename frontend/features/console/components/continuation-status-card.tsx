import { Card } from "@veritas/design-system";
import type { DecideResponse, ContinuationOutput } from "@veritas/types";
import { useI18n } from "../../../components/i18n-provider";

interface ContinuationStatusCardProps {
  result: DecideResponse;
}

/** Claim status → visual color. */
function claimColor(status: string): string {
  if (status === "live") return "text-success";
  if (status === "narrowed" || status === "degraded") return "text-warning";
  return "text-danger"; // escalated, halted, revoked
}

/** Card accent derived from claim status. */
function cardAccent(status: string): "success" | "warning" | "danger" {
  if (status === "live") return "success";
  if (status === "narrowed" || status === "degraded") return "warning";
  return "danger";
}

/**
 * Minimal card showing continuation runtime status in the Decision Console.
 *
 * Only renders when continuation data is present (feature flag on).
 * Phase-1: observe/shadow only — no enforcement actions.
 */
export function ContinuationStatusCard({ result }: ContinuationStatusCardProps): JSX.Element | null {
  const { t } = useI18n();

  const continuation = result.continuation as ContinuationOutput | null | undefined;
  if (!continuation?.state || !continuation?.receipt) return null;

  const { state, receipt } = continuation;
  const claimStatus = String(state.claim_status ?? "unknown");
  const isDiverged = receipt.divergence_flag === true;

  return (
    <Card
      title={t("Continuation ステータス", "Continuation Status")}
      titleSize="sm"
      variant="elevated"
      accent={cardAccent(claimStatus)}
    >
      <div className="space-y-2 text-xs">
        {/* Divergence banner */}
        {isDiverged && (
          <div className="rounded border border-warning/40 bg-warning/10 px-2 py-1 text-warning">
            {t(
              "ステップは通過したが chain continuation は弱化しています",
              "Step passed but chain continuation is weakened",
            )}
          </div>
        )}

        <div className="grid gap-x-4 gap-y-1 md:grid-cols-2">
          {/* State side */}
          <p>
            <span className="text-muted-foreground">{t("請求ステータス", "Claim Status")}: </span>
            <span className={`font-semibold ${claimColor(claimStatus)}`}>
              {claimStatus.toUpperCase()}
            </span>
          </p>
          <p>
            <span className="text-muted-foreground">{t("法バージョン", "Law Version")}: </span>
            <span className="font-mono">{state.law_version || "-"}</span>
          </p>

          {/* Receipt side */}
          <p>
            <span className="text-muted-foreground">{t("再検証", "Revalidation")}: </span>
            <span className="font-mono">{String(receipt.revalidation_status ?? "-")}</span>
          </p>
          <p>
            <span className="text-muted-foreground">{t("結果", "Outcome")}: </span>
            <span className="font-mono">{String(receipt.revalidation_outcome ?? "-")}</span>
          </p>
          <p>
            <span className="text-muted-foreground">{t("効果前拒否推奨", "Should Refuse")}: </span>
            <span className={receipt.should_refuse_before_effect ? "font-semibold text-danger" : ""}>
              {receipt.should_refuse_before_effect ? "YES" : "no"}
            </span>
          </p>
          <p>
            <span className="text-muted-foreground">{t("乖離", "Divergence")}: </span>
            <span className={isDiverged ? "font-semibold text-warning" : ""}>
              {isDiverged ? "YES" : "no"}
            </span>
          </p>
        </div>

        {/* Reason codes (if any) */}
        {receipt.reason_codes && receipt.reason_codes.length > 0 && (
          <p className="text-2xs text-muted-foreground">
            <span className="font-semibold">{t("理由コード", "Reason Codes")}: </span>
            {receipt.reason_codes.join(", ")}
          </p>
        )}
      </div>
    </Card>
  );
}
