# 本番検証（Production Validation）

## 位置づけ
本番相当の検証経路（CI / staged / live）を日本語で把握するための解説です。

## 要点
- 本番検証は「実装済み事実の継続確認」であり、認証取得の主張ではありません。
- production/smoke テスト、ライブ検証、運用Runbook訓練を段階的に実施します。
- 検証結果は TrustLog や提出エビデンスに再利用できる形で保存します。

## VERITASにおける意味
- Decision Governance の fail-closed 振る舞いを継続的に確認する運用基盤です。
- operator-facing governance surface の信頼性を、テストと証跡で裏づけます。

## 実装上の確認ポイント
- `make quality-checks` と production/smoke 系テストを継続実行する。
- PostgreSQL の live 検証導線と運用ドリルを定期確認する。
- 詳細は英語正本または実装ファイルを確認してください。

## 現時点の制限
- 検証通過だけで本番可用性・法令適合を保証しません。
- 環境固有のセキュリティレビュー、監査設計、運用承認が必要です。

## 英語正本
- [docs/en/validation/production-validation.md](../../en/validation/production-validation.md)
