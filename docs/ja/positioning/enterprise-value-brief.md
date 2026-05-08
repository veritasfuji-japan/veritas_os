# VERITAS OS 企業向け価値説明ブリーフ

> この文書は日本語の補助説明です。英語版の正本は `docs/en/positioning/enterprise-value-brief.md` です。

## 1. 一文で示す価値

VERITAS OS は、意思決定ガバナンスとバインド境界を提供するコントロールプレーンであり、AIエージェントの判断を実世界への作用前に、レビュー可能・追跡可能・再現可能・監査可能・強制可能な形で扱えるようにします。

## 2. 想定読者

- エンタープライズAIガバナンス担当
- 規制対象ワークフローの責任者
- リスク / コンプライアンス / 監査チーム
- AIプラットフォームチーム
- 投資家および技術デューデリジェンス担当
- 医療 / 金融 / 公共領域のAI評価担当

## 3. 解決したい問題

AI導入が止まる主因は、モデル性能の不足よりも、実行前のAIエージェント判断を説明・停止・レビュー・監査できないことにあります。

代表的なギャップ:

- 推奨から実行への遷移が速すぎる
- 規制領域では、明示的な証跡・承認境界・再現可能なトレースが必要
- 監査ログだけでは不十分（何が起きたかは示せても、なぜ許可されたかまでは示しにくい）

## 4. VERITAS が行うこと

VERITAS は、AIの判断をコミット前にガバナンス境界とバインド境界へ通します。

- レビュー可能な判断成果物・バインド成果物を生成
- コミット前に block / escalate / refuse / permit を実施
- 証跡境界と監査境界を明示
- 運用担当・レビュアー向け成果物と One-Day PoC 証跡パケットを提供

## 5. 実世界作用前にブロックできる対象

現在の実装範囲で、以下のような経路をコミット前にブロックまたは拒否できます。

- Authority Evidence の欠落
- 規制アクションの非admissible判定
- unsafe / 未定義の bind path
- pre-bind formation lineage が昇格不可
- bindチェックを欠いた governance mutation path
- 証拠で裏付けられない provider/compliance 主張

本ブリーフは「現在の実装済み制御パターン」を示すものであり、「すべての unsafe AI actions を防止する」とは主張しません。

## 6. VERITAS が生成する証跡

- Decision artifacts
- Execution intent lineage
- Bind receipts
- Bind summaries
- One-Day PoC evidence JSON / Markdown
- Benchmark JSON / Markdown
- Reviewer packs
- Provider support matrix
- Compliance positioning docs
- Type safety baseline
- Maintainer handoff runbook

## 7. 1日で検証できること

- One-Day PoC の smoke path 実行
- サニタイズ済み evidence packet の生成
- evidence schema の検証
- ローカル benchmark の実行
- provider support 境界の確認
- EU AI Act-aligned positioning 境界の確認
- maintainer handoff / type baseline 文書の確認

## 8. エンタープライズAI導入で重要な理由

- 企業には「実行後のログ」だけでなく「実行前の制御」が必要
- ガバナンスはモデル実装者以外にも検査可能である必要がある
- コンプライアンス / 監査チームには提出可能な証跡パケットが必要
- 投資家・技術レビュアーには再現可能な検証経路が必要
- VERITAS は、AIエージェントガバナンスを slideware から検査可能な control plane へ変換する

## 9. 現在の proof assets

- [One-Day PoC Reviewer Pack](../poc/one-day-poc-reviewer-pack.md)
- [One-Day PoC Performance Report](../poc/one-day-poc-performance-report.md)
- [Provider Support Matrix](../operations/provider-support-matrix.md)
- [Type Safety Baseline](../operations/type-safety-baseline.md)
- [Maintainer Handoff](../operations/maintainer-handoff.md)
- [Current Implementation Matrix](../validation/current-implementation-matrix.md)
- [Regulated Action Governance Proof Pack](../validation/regulated-action-governance-proof-pack.md)
- [Public Positioning](public-positioning.md)

## 10. 現時点の境界線（非主張）

以下は現時点で主張しません。

- 法的助言ではありません
- 規制当局の承認ではありません
- 第三者認証ではありません
- EU適合宣言ではありません
- CEマーキングではありません
- 本番SLAではありません
- 24/7サポートではありません
- provider-neutral production readiness の証明ではありません
- 銀行 / 医療 / 政府の本番統合実績の証明ではありません
- リポジトリ全体 strict typing 完了の証明ではありません
- バスファクターリスクの完全解消を示すものではありません

## 11. 最初に適したユースケース

- AML/KYC 規制アクションレビュー
- AIエージェント承認ゲート
- ツール実行前の内部ガバナンスレビュー
- 証跡先行のAIワークフローレビュー
- エンタープライズAIパイロットのデューデリジェンス
- 医療ポリシー / ガバナンスレビューのサンドボックス
- 監査提出可能なAI意思決定レビューパケット

## 12. レビュアー / 顧客向けの次の一手

- One-Day PoC を実行
- evidence packet をレビュー
- provider support matrix を確認
- compliance positioning を確認
- 規制対象の decision/action path を1つ特定
- 現行ワークフローと VERITAS ガバナンス適用後を比較
- スコープを絞った pilot へ進むか判断
