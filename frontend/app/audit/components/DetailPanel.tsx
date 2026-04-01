"use client";

import { Card } from "@veritas/design-system";
import type { TrustLogItem } from "@veritas/types";
import { useI18n } from "../../../components/i18n-provider";
import {
  buildHumanSummary,
  getString,
  shortHash,
  toPrettyJson,
  type ChainResult,
  type DetailTab,
} from "../audit-types";
import { STATUS_BG, STATUS_COLORS } from "../constants";

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

interface DetailPanelProps {
  selected: TrustLogItem | null;
  selectedChain: ChainResult | null;
  previousEntry: TrustLogItem | null;
  nextEntry: TrustLogItem | null;
  detailTab: DetailTab;
  onDetailTabChange: (tab: DetailTab) => void;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function DetailPanel({
  selected,
  selectedChain,
  previousEntry,
  nextEntry,
  detailTab,
  onDetailTabChange,
}: DetailPanelProps): JSX.Element {
  const { t } = useI18n();

  const DETAIL_TABS: { value: DetailTab; label: string }[] = [
    { value: "summary", label: t("サマリー", "Summary") },
    { value: "metadata", label: t("メタデータ", "Metadata") },
    { value: "hash", label: t("ハッシュ", "Hash") },
    { value: "related", label: t("関連ID", "Related") },
    { value: "continuation", label: t("継続", "Continuation") },
    { value: "raw", label: "Raw JSON" },
  ];

  // ── Continuation runtime helpers ────────────────────────────────
  const hasContinuation = selected
    ? typeof selected.continuation_claim_status === "string"
    : false;

  const claimStatus = selected?.continuation_claim_status as string | undefined;
  const revalStatus = selected?.continuation_revalidation_status as string | undefined;
  const revalOutcome = selected?.continuation_revalidation_outcome as string | undefined;
  const divergenceFlag = selected?.continuation_divergence_flag as boolean | undefined;
  const shouldRefuse = selected?.continuation_should_refuse as boolean | undefined;
  const reasonCodes = selected?.continuation_reason_codes as string[] | undefined;
  const lawVersion = selected?.continuation_law_version_id as string | undefined;
  const supportDigest = selected?.continuation_support_basis_digest as string | undefined;
  const burdenDigest = selected?.continuation_burden_headroom_digest as string | undefined;
  const localStepResult = selected?.continuation_local_step_result as string | undefined;

  /** Color for claim status based on severity. */
  function claimStatusColor(status: string | undefined): string {
    if (!status) return "text-muted-foreground";
    if (status === "live") return "text-success";
    if (status === "narrowed" || status === "degraded") return "text-warning";
    return "text-danger"; // escalated, halted, revoked
  }

  /** Whether there is step-pass + chain-weakening divergence. */
  const isDiverged = divergenceFlag === true;

  return (
    <Card title="Selected Audit" titleSize="md" variant="elevated">
      {selected ? (
        <div className="space-y-3 text-xs">
          {/* Tab bar */}
          <div className="flex gap-1 border-b border-border pb-1">
            {DETAIL_TABS.map((tab) => (
              <button
                key={tab.value}
                type="button"
                onClick={() => onDetailTabChange(tab.value)}
                className={`rounded-t px-3 py-1.5 text-xs transition-colors ${
                  detailTab === tab.value
                    ? "border-b-2 border-primary bg-primary/5 font-semibold"
                    : "text-muted-foreground hover:bg-muted/20"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab: Summary */}
          {detailTab === "summary" && (
            <div className="space-y-3">
              <div
                className={`rounded border p-3 ${selectedChain ? STATUS_BG[selectedChain.status] : "border-border"}`}
              >
                <p className="text-sm font-medium">
                  {buildHumanSummary(selected)}
                </p>
                {selectedChain && (
                  <p className="mt-1">
                    <span className="font-semibold">
                      {t("チェーン状態", "Chain status")}:
                    </span>{" "}
                    <span className={STATUS_COLORS[selectedChain.status]}>
                      {selectedChain.status.toUpperCase()}
                    </span>{" "}
                    — {selectedChain.reason}
                  </p>
                )}
              </div>
              <div className="grid gap-2 rounded border border-border p-3 md:grid-cols-2">
                <p>
                  <strong>Stage:</strong> {getString(selected, "stage")}
                </p>
                <p>
                  <strong>Status:</strong> {getString(selected, "status")}
                </p>
                <p>
                  <strong>Policy Version:</strong>{" "}
                  {getString(selected, "policy_version")}
                </p>
                <p>
                  <strong>Severity:</strong>{" "}
                  {getString(selected, "severity")}
                </p>
              </div>
            </div>
          )}

          {/* Tab: Metadata */}
          {detailTab === "metadata" && (
            <div className="rounded border border-border p-3">
              <p className="mb-2 font-semibold">
                {t("メタデータカード", "Metadata Card")}
              </p>
              <pre className="overflow-x-auto whitespace-pre-wrap rounded bg-muted/20 p-2 text-2xs">
                {toPrettyJson(selected.metadata ?? {})}
              </pre>
            </div>
          )}

          {/* Tab: Hash */}
          {detailTab === "hash" && (
            <div className="space-y-2">
              <div className="grid gap-2 md:grid-cols-3">
                <div className="rounded border border-border p-3 text-center">
                  <p className="text-2xs text-muted-foreground">
                    {t("前ログ", "Previous")}
                  </p>
                  <p className="mt-1 font-mono text-2xs">
                    {previousEntry
                      ? shortHash(previousEntry.sha256)
                      : t("なし", "none")}
                  </p>
                </div>
                <div
                  className={`rounded border p-3 text-center ${selectedChain ? STATUS_BG[selectedChain.status] : "border-border"}`}
                >
                  <p className="text-2xs font-semibold">
                    {t("現在", "Current")}
                  </p>
                  <p className="mt-1 font-mono text-2xs">
                    {shortHash(selected.sha256)}
                  </p>
                  <p className="mt-0.5 font-mono text-2xs text-muted-foreground">
                    prev: {shortHash(selected.sha256_prev)}
                  </p>
                </div>
                <div className="rounded border border-border p-3 text-center">
                  <p className="text-2xs text-muted-foreground">
                    {t("次ログ", "Next")}
                  </p>
                  <p className="mt-1 font-mono text-2xs">
                    {nextEntry
                      ? shortHash(nextEntry.sha256)
                      : t("なし", "none")}
                  </p>
                </div>
              </div>
              {selectedChain && selectedChain.status !== "verified" && (
                <div
                  className={`rounded border p-3 ${STATUS_BG[selectedChain.status]}`}
                >
                  <p className="font-semibold">
                    {selectedChain.status === "broken" &&
                      t(
                        "チェーン破損: ハッシュの不一致が検出されました。このエントリまたは前のエントリが改竄された可能性があります。",
                        "Chain broken: Hash mismatch detected. This entry or the previous one may have been tampered with.",
                      )}
                    {selectedChain.status === "missing" &&
                      t(
                        "ハッシュ欠損: 検証に必要なハッシュ値が存在しません。ログの欠落が考えられます。",
                        "Hash missing: A required hash value is absent. Log entries may be missing.",
                      )}
                    {selectedChain.status === "orphan" &&
                      t(
                        "孤立エントリ: 前のエントリが存在するにもかかわらず、sha256_prevが設定されていません。",
                        "Orphan entry: Previous entry exists but sha256_prev is not set on this entry.",
                      )}
                  </p>
                  <p className="mt-1 text-2xs">
                    {t("理由", "Reason")}: {selectedChain.reason}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Tab: Related IDs */}
          {detailTab === "related" && (
            <div className="grid gap-2 rounded border border-border p-3 md:grid-cols-2">
              <p>
                <strong>request_id:</strong>{" "}
                <span className="font-mono">
                  {selected.request_id ?? "-"}
                </span>
              </p>
              <p>
                <strong>decision_id:</strong>{" "}
                <span className="font-mono">
                  {String(selected.decision_id ?? "-")}
                </span>
              </p>
              <p>
                <strong>replay_id:</strong>{" "}
                {typeof selected.replay_id === "string" ? (
                  <a
                    className="font-mono underline"
                    href={`/replay?replay_id=${encodeURIComponent(selected.replay_id)}`}
                  >
                    {selected.replay_id}
                  </a>
                ) : (
                  "-"
                )}
              </p>
              <p>
                <strong>policy_version:</strong>{" "}
                <span className="font-mono">
                  {getString(selected, "policy_version")}
                </span>
              </p>
            </div>
          )}

          {/* Tab: Continuation */}
          {detailTab === "continuation" && (
            <div className="space-y-3">
              {!hasContinuation ? (
                <p className="text-xs text-muted-foreground">
                  {t(
                    "この監査エントリにはcontinuationデータがありません。VERITAS_CAP_CONTINUATION_RUNTIME が無効か、このリクエスト以前のバージョンです。",
                    "No continuation data for this audit entry. The continuation runtime flag may be off or this predates the feature.",
                  )}
                </p>
              ) : (
                <>
                  {/* Divergence banner */}
                  {isDiverged && (
                    <div className="rounded border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">
                      {t(
                        "ステップは通過したが、chain-level continuation は弱化・停止・失効していました。",
                        "Step passed but chain-level continuation was weakened, halted, or revoked.",
                      )}
                    </div>
                  )}

                  {/* State side */}
                  <div className="rounded border border-border p-3">
                    <p className="mb-2 text-xs font-semibold">
                      {t("State（スナップショット）", "State (Snapshot)")}
                    </p>
                    <div className="grid gap-2 text-xs md:grid-cols-2">
                      <p>
                        <strong>{t("請求ステータス", "Claim Status")}:</strong>{" "}
                        <span className={`font-semibold ${claimStatusColor(claimStatus)}`}>
                          {claimStatus?.toUpperCase() ?? "-"}
                        </span>
                      </p>
                      <p>
                        <strong>{t("法バージョン", "Law Version")}:</strong>{" "}
                        <span className="font-mono">{lawVersion ?? "-"}</span>
                      </p>
                      <p>
                        <strong>{t("支持基盤", "Support Basis")}:</strong>{" "}
                        <span className="font-mono text-2xs">{supportDigest ?? "-"}</span>
                      </p>
                      <p>
                        <strong>{t("負担/余裕", "Burden / Headroom")}:</strong>{" "}
                        <span className="font-mono text-2xs">{burdenDigest ?? "-"}</span>
                      </p>
                    </div>
                  </div>

                  {/* Receipt side */}
                  <div className="rounded border border-border p-3">
                    <p className="mb-2 text-xs font-semibold">
                      {t("Receipt（監査証跡）", "Receipt (Audit Witness)")}
                    </p>
                    <div className="grid gap-2 text-xs md:grid-cols-2">
                      <p>
                        <strong>{t("再検証ステータス", "Revalidation Status")}:</strong>{" "}
                        <span className="font-mono">{revalStatus ?? "-"}</span>
                      </p>
                      <p>
                        <strong>{t("再検証結果", "Revalidation Outcome")}:</strong>{" "}
                        <span className="font-mono">{revalOutcome ?? "-"}</span>
                      </p>
                      <p>
                        <strong>{t("効果前拒否推奨", "Should Refuse Before Effect")}:</strong>{" "}
                        <span className={shouldRefuse ? "font-semibold text-danger" : ""}>
                          {shouldRefuse === true ? "YES" : shouldRefuse === false ? "no" : "-"}
                        </span>
                      </p>
                      <p>
                        <strong>{t("乖離フラグ", "Divergence Flag")}:</strong>{" "}
                        <span className={isDiverged ? "font-semibold text-warning" : ""}>
                          {divergenceFlag === true ? "YES" : divergenceFlag === false ? "no" : "-"}
                        </span>
                      </p>
                      <p>
                        <strong>{t("ローカルステップ結果", "Local Step Result")}:</strong>{" "}
                        <span className="font-mono">{localStepResult ?? "-"}</span>
                      </p>
                      {reasonCodes && reasonCodes.length > 0 && (
                        <p className="md:col-span-2">
                          <strong>{t("理由コード", "Reason Codes")}:</strong>{" "}
                          <span className="font-mono text-2xs">
                            {reasonCodes.join(", ")}
                          </span>
                        </p>
                      )}
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {/* Tab: Raw JSON */}
          {detailTab === "raw" && (
            <details open>
              <summary className="cursor-pointer font-semibold">
                {t("JSON 展開", "Expand JSON")}
              </summary>
              <pre className="mt-2 overflow-x-auto rounded border border-border bg-muted/20 p-3">
                {toPrettyJson(selected)}
              </pre>
            </details>
          )}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          {t(
            "タイムラインからログを選択すると、ここに詳細が表示されます。サマリー・メタデータ・ハッシュ検証・関連ID・生JSONの各タブで確認できます。",
            "Select a log from the timeline to see details. Tabs include summary, metadata, hash verification, related IDs, and raw JSON.",
          )}
        </p>
      )}
    </Card>
  );
}
