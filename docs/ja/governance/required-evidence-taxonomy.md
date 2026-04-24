# Required Evidence Taxonomy（日本語解説）

## 位置づけ
`required_evidence` 系の語彙統制を理解するための日本語解説です。審査担当・テンプレート設計者・実装者向けです。

## 要点
- 必須証拠（required_evidence）と不足証拠（missing_evidence）を共通キーで扱います。
- alias を許容しつつ canonical key へ寄せる方針です。
- AML/KYC テンプレートと bind 判定の整合が重要です。

## VERITASにおける意味
- Decision Governance の説明責任をデータ語彙で支える基盤です。
- bind_summary / bind概要 で不足証拠の要点を示し、BindReceipt で詳細を追跡します。

## 実装上の確認ポイント
- taxonomy JSON の canonical key と UI/API 表示語彙を合わせる。
- テンプレート更新時に evidence key 差分レビューを実施する。
- 詳細は英語正本または実装ファイルを確認してください。

## 現時点の制限
- すべてのドメインで strict schema 強制は未完了です。
- 本番適用時は業務要件に沿った証拠キー拡張が必要です。

## 英語正本
- [docs/en/governance/required-evidence-taxonomy.md](../../en/governance/required-evidence-taxonomy.md)
