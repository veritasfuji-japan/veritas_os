# One-Day PoC証跡パック

- 英語版が正本であり、日本語版は補助説明です。
- これはOne-Day PoCをレビューするための証跡パックである。
- 何を確認し、どの証跡を集め、何を成功条件とするかを整理する。
- 本番SLAではない。
- 第三者認証ではない。
- 顧客環境測定ではない。
- EU AI Act準拠を認証するものではない。
- 外部LLM/provider latencyやcostは、明示的にproviderを有効化して別途記録しない限り測定対象ではない。

## 英語正本

- [One-Day PoC Evidence Pack](../../en/poc/one-day-poc-evidence-pack.md)

## Purpose

顧客・投資家・レビュー担当者が、One-Day PoC のガバナンス挙動と証跡品質を短時間で確認できるように、レビュー観点をコンパクトに整理する。

## What this PoC demonstrates

- 必要な authority/evidence が不足している場合、規制対象または高感度 action は commit 前に停止できる。
- 意思決定経路は governance/audit trace を通じてレビュー可能性を維持できる。
- reviewer-facing docs により deterministic local metrics と HTTP PoC benchmark を区別できる。
- 本番準備完了を主張する前に governance boundary を明示できる。

## What this PoC does not prove

- 本番レイテンシを証明するものではない。
- 本番可用性を証明するものではない。
- 顧客環境での性能を証明するものではない。
- これ単体で法的コンプライアンスを証明するものではない。
- 法務・セキュリティ・規制レビューを代替するものではない。
- EU AI Act準拠を認証するものではない。
- provider を明示的に有効化して別途測定しない限り、provider latency/cost を測定するものではない。

## Evidence checklist

| Evidence item | What to inspect | Expected result | Link |
|---|---|---|---|
| Local deterministic performance artifact | 最新の deterministic local benchmark markdown | deterministic metrics と非主張境界を確認できる | [`docs/en/benchmarks/local-performance-metrics.latest.md`](../../en/benchmarks/local-performance-metrics.latest.md) |
| Local deterministic performance summary | 最新の deterministic local benchmark JSON | 機械可読な metrics と注記を確認できる | [`docs/en/benchmarks/local-performance-metrics.latest.json`](../../en/benchmarks/local-performance-metrics.latest.json) |
| One-Day PoC performance benchmark doc | local/configured HTTP PoC benchmark の説明と境界 | HTTP benchmark と deterministic artifact を区別できる | [`docs/ja/poc/one-day-poc-performance-report.md`](one-day-poc-performance-report.md) |
| Bind / governance boundary documentation | bind admissibility と governance boundary の説明 | commit 前境界と必要証跡条件を特定できる | [`docs/ja/architecture/bind-boundary-governance-artifacts.md`](../architecture/bind-boundary-governance-artifacts.md) |
| TrustLog / audit trace documentation | 監査・追跡導線の設計 | 意思決定根拠と監査導線を辿れる | [`docs/ja/architecture/authority-evidence-vs-audit-log.md`](../architecture/authority-evidence-vs-audit-log.md) |
| README / README_JP entry points | トップレベルの案内導線 | EN/JA の入口をすぐ辿れる | [`README.md`](../../../README.md) / [`README_JP.md`](../../../README_JP.md) |
| Documentation map | EN/JA 対応表と正本ルール | EN正本/JA補助の対応関係を確認できる | [`docs/DOCUMENTATION_MAP.md`](../../DOCUMENTATION_MAP.md) |
| Any demo scenario docs already present in repo | 既存 walkthrough/reviewer pack/sample evidence docs | シナリオ実行と証跡比較の導線を確認できる | [`docs/ja/poc/one-day-poc-walkthrough.md`](one-day-poc-walkthrough.md), [`docs/ja/poc/one-day-poc-reviewer-pack.md`](one-day-poc-reviewer-pack.md), [`docs/ja/poc/sample-one-day-poc-evidence.md`](sample-one-day-poc-evidence.md) |

## Suggested walkthrough scenarios

1. authority/evidence 不足により sensitive action が commit 前に block される。
2. 必要 policy/evidence が揃うと許可された action が proceed する。
3. audit/TrustLog の経路がレビュー可能な状態で維持される。
4. deterministic local artifact と HTTP PoC benchmark を比較できる。
5. operator が non-claim boundary を明確に説明できる。

## Success criteria

- reviewer が commit boundary を特定できる。
- reviewer が action の block/allow 理由を特定できる。
- reviewer が relevant evidence/audit path を特定できる。
- reviewer が deterministic local metrics と HTTP PoC benchmark output を区別できる。
- reviewer が unsupported な SLA/compliance/certification claim を持ち帰らない。

## Failure criteria

- local metrics から本番SLAを主張しているように見える。
- 根拠なしに第三者認証を主張しているように見える。
- reviewer が action の block/allow 理由を特定できない。
- audit trail または evidence path が不明瞭である。
- 明示的な provider 測定なしに provider cost/latency を示唆している。

## Artifacts to collect

- block/allow decision path のスクリーンショット
- 取得可能な関連 JSON 出力
- deterministic local metrics artifact
- 実行した場合の One-Day PoC benchmark output
- environment / command / date / commit SHA の記録
- 例外または failed checks の記録

## Reviewer notes

本パックは既存の validation/walkthrough docs と併用する。結論は local/configured PoC の証跡範囲に限定し、非主張境界を口頭・文書の双方で明示する。

## Related documents

- [`docs/ja/poc/one-day-poc-reviewer-handoff-template.md`](one-day-poc-reviewer-handoff-template.md)
- [`docs/ja/poc/one-day-poc-operator-runbook.md`](one-day-poc-operator-runbook.md) — 証跡の準備・実行・提出手順はOperator Runbookを参照する。
- [`docs/en/benchmarks/local-performance-metrics.latest.md`](../../en/benchmarks/local-performance-metrics.latest.md)
- [`docs/en/benchmarks/local-performance-metrics.latest.json`](../../en/benchmarks/local-performance-metrics.latest.json)
- [`docs/en/benchmarks/performance-metrics.md`](../../en/benchmarks/performance-metrics.md)
- [`docs/en/poc/one-day-poc-performance-report.md`](../../en/poc/one-day-poc-performance-report.md)
- [`docs/INDEX.md`](../../INDEX.md)
- [`docs/DOCUMENTATION_MAP.md`](../../DOCUMENTATION_MAP.md)
