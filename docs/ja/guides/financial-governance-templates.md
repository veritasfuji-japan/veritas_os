# 金融ガバナンステンプレート（日本語解説）

## 位置づけ
AML/KYC PoC と実運用検討で使うテンプレート群の読み方を整理する日本語解説です。

## 要点
- テンプレートは Decision Governance の最小運用単位（判定基準・証拠要件・昇格条件）を定義します。
- required_evidence taxonomy と policy bundle promotion を前提に運用します。
- 過大主張を避け、betaで実装済み範囲を明確化します。

## VERITASにおける意味
- 金融領域での operator-facing governance surface を標準化する入口です。
- `bind_summary` と `BindReceipt` を使い、審査・監査・運用の会話を揃えます。

## 実装上の確認ポイント
- テンプレート適用時の required/missing evidence を API で確認する。
- ポリシーバンドル昇格と署名検証の運用手順を確認する。
- 詳細は英語正本または実装ファイルを確認してください。

## 現時点の制限
- テンプレートは組織固有要件に合わせた調整が必要です。
- 規制当局承認や法的適合を自動保証するものではありません。

## 英語正本
- [docs/en/guides/financial-governance-templates.md](../../en/guides/financial-governance-templates.md)
