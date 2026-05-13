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

## TrustLog production posture checker（最小姿勢チェック）
- `check-trustlog-production-posture` は、TrustLog の本番姿勢に必要な環境変数の有無/設定姿勢を確認する operator-facing な最小チェックです（実行: `make check-trustlog-production-posture` または `python -m scripts.security.check_trustlog_production_posture`）。
- runtime default は変更せず、実DB/実KMS/実WORMへ接続もしません。CI の `[Tier 1] governance-smoke` では非シークレットのダミー環境変数で production enforcement path を検証しますが、実運用 readiness の証明にはなりません。
- production mode（`VERITAS_ENV=production|prod` または `VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE` が truthy）の failure 条件は、`postgresql` backend / DB URL / `VERITAS_ENCRYPTION_KEY` / `aws_kms` signer / `VERITAS_TRUSTLOG_KMS_KEY_ID` の不足です。`VERITAS_TRUSTLOG_WORM_MIRROR_PATH` 未設定、transparency 未要求、`VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH` 未設定、`VERITAS_TRUSTLOG_ANCHOR_BACKEND=noop` は warning 扱いです。
- 注: `VERITAS_TRUSTLOG_ALLOW_INSECURE_SIGNER_IN_PROD` は、この production posture checker では考慮されません。本番姿勢チェックでは `VERITAS_TRUSTLOG_SIGNER_BACKEND=aws_kms` を要求し、`file` / `local` / `noop` / 未設定の signer は、break-glass フラグがあっても failure になります。

## 現時点の制限
- ここで示す内容は一般指針で、各環境のHA/DR要件を代替しません。
- 本番適用前に監査設計・鍵管理・アクセス統制を追加してください。

## 英語正本
- [docs/en/operations/postgresql-production-guide.md](../../en/operations/postgresql-production-guide.md)
