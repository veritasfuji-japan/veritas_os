# PostgreSQL本番運用ガイド（日本語解説）

## 位置づけ
PostgreSQL を本番で運用する際の確認観点を、日本語で短く整理した案内です。対象は運用者、SRE、監査担当です。

## 要点
- VERITAS は PostgreSQL を本番パスとして想定し、軽量バックエンドは開発用途と区別します。
- 監視、バックアップ/復旧、権限管理、設定固定を運用の基準点にします。
- bind証跡の保存可用性は Decision Governance の前提条件です。

## VERITASにおける意味
- TrustLog と Replay の再現性は DB運用品質に依存します。
- FUJI Gate の fail-closed 結果を保持するため、DB障害時の安全側停止設計が重要です。

## 実装上の確認ポイント
- `/health` で backend 種別を確認する。
- バックアップ/リストア手順とドリル結果を証跡化する。
- Migration 手順とロールバック手順を運用Runbookに統合する。

## 現時点の制限
- ここで示す内容は一般指針で、各環境のHA/DR要件を代替しません。
- 本番適用前に監査設計・鍵管理・アクセス統制を追加してください。

## 英語正本
- [docs/en/operations/postgresql-production-guide.md](../../en/operations/postgresql-production-guide.md)
