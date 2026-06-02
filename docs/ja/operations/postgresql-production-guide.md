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

- コンパクトな運用チェックリストは [TrustLog 本番 readiness チェックリスト](trustlog-production-readiness-checklist.md) を参照してください。
- `check-trustlog-production-posture` は、TrustLog の本番姿勢に必要な環境変数の有無/設定姿勢を確認する operator-facing な最小チェックです（実行: `make check-trustlog-production-posture` または `python -m scripts.security.check_trustlog_production_posture`）。
- runtime default は変更せず、実DB/実KMS/実WORMへ接続もしません。CI の `[Tier 1] governance-smoke` では非シークレットのダミー環境変数で production enforcement path を検証しますが、実運用 readiness の証明にはなりません。
- production posture validation が厳格化される条件は以下です。
  - `VERITAS_ENV=production`
  - `VERITAS_ENV=prod`
  - `VERITAS_ENV=secure`
  - `VERITAS_ENV=hardened`
  - `VERITAS_POSTURE=secure|hardened|prod|production`
  - `VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE` が truthy（`1`/`true`/`yes`/`on`）
- runtime startup validation でも、上記 enforcement が active の場合は同じ production-failure posture を fail-fast で適用します（legacy strict `VERITAS_ENV`、strict `VERITAS_POSTURE`、truthy `VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE`）。
- failure 条件（起動拒否/CLI失敗）は以下です。
  - `VERITAS_TRUSTLOG_BACKEND` が `postgresql` でない
  - `VERITAS_DATABASE_URL` と `DATABASE_URL` が両方未設定
  - `VERITAS_ENCRYPTION_KEY` が未設定
  - `VERITAS_TRUSTLOG_SIGNER_BACKEND` が `aws_kms` に解決されない（`aws_kms_ed25519` は `aws_kms` 扱い。`file` / `file_ed25519` は本番 signer としては許可されず failure）
  - signer backend が `aws_kms` に解決されるのに `VERITAS_TRUSTLOG_KMS_KEY_ID` が未設定
- warning 条件（startup/CLI とも non-fatal）は以下です。
  - `VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED` が明示的に無効
  - local anchor backend かつ transparency required で `VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH` が未設定
  - `VERITAS_TRUSTLOG_ANCHOR_BACKEND` が `noop` に解決される（`noop`/`none`/`no_op`）
  - local mirror backend で `VERITAS_TRUSTLOG_WORM_MIRROR_PATH` が未設定
  - `VERITAS_TRUSTLOG_MIRROR_BACKEND=s3_object_lock` なのに `VERITAS_TRUSTLOG_S3_BUCKET`/`VERITAS_TRUSTLOG_S3_PREFIX` が不足
  - `VERITAS_TRUSTLOG_MIRROR_BACKEND` が未知値（warning には正規化された backend 値を含む）
- 注: `VERITAS_TRUSTLOG_ALLOW_INSECURE_SIGNER_IN_PROD` は、この production posture checker では考慮されません。本番姿勢チェックでは `VERITAS_TRUSTLOG_SIGNER_BACKEND=aws_kms` を要求し、`file` / `local` / `noop` / 未設定の signer は、break-glass フラグがあっても failure になります。

## TrustLog strict mirror capabilities の startup 拒否

`secure`/`prod` 姿勢では、選択された TrustLog mirror backend が
`immutable_retention` と `fail_closed` の両方を宣言していない場合、
startup は fail-closed で拒否されます。S3 Object Lock 対応 mirror を使う
には、`VERITAS_TRUSTLOG_MIRROR_BACKEND=s3_object_lock`、
`VERITAS_TRUSTLOG_S3_BUCKET`、`VERITAS_TRUSTLOG_S3_PREFIX` を設定し、
保持ポリシーに応じて `VERITAS_TRUSTLOG_S3_OBJECT_LOCK_MODE` と
`VERITAS_TRUSTLOG_S3_RETENTION_DAYS` を設定してください。local WORM mirror
は local/dev または二次 mirror 用であり、既存の backend contract が
完全な strict capability set を明示的に登録していない限り、本番
immutable retention の代替にはなりません。`VERITAS_POSTURE` を下げる
のは、既存ポリシーで許可された非本番/local 開発に限定してください。

## 現時点の制限
- ここで示す内容は一般指針で、各環境のHA/DR要件を代替しません。
- 本番適用前に監査設計・鍵管理・アクセス統制を追加してください。

## 英語正本
- [docs/en/operations/postgresql-production-guide.md](../../en/operations/postgresql-production-guide.md)
