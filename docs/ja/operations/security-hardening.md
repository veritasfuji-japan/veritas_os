# セキュリティハードニング（日本語解説）

## 位置づけ
VERITAS の secure/prod 運用に向けたハードニング観点を日本語で把握するための文書です。

## 要点
- fail-closed を前提に、秘密情報管理・署名検証・監査ログ保全を強化します。
- posture 設定（dev/staging/secure/prod）で安全既定値を明示的に分離します。
- 運用変更は監査可能な手順と証跡を伴う必要があります。

## VERITASにおける意味
- Decision Governance の有効性は、ハードニングされた運用環境で初めて成立します。
- FUJI Gate・TrustLog・governance artifact signing を横断した統制が必要です。

## 実装上の確認ポイント
- posture関連環境変数と override 利用条件を確認する。
- 外部シークレットマネージャー、署名鍵、監査ログ保全設定を確認する。
- 詳細は英語正本または実装ファイルを確認してください。

## 現時点の制限
- 本文書はチェックリストであり、第三者セキュリティ認証ではありません。
- 本番導入前に脅威モデルと運用審査を実施してください。

## 英語正本
- [docs/en/operations/security-hardening.md](../../en/operations/security-hardening.md)

## Type B Summary: TrustLog Secure-Default Posture Gate（英語正本準拠）
- `dev`: `jsonl` + encryption key未設定はローカル用途として許容。ただし `/v1/health` と `/v1/status` では `security_posture.trustlog_secure_default.status=degraded` として表示されます。
- `staging`: 診断上は `degraded`（非PostgreSQL backend、暗号キー未設定など）を表示します。なお `VERITAS_TRUSTLOG_BACKEND=postgresql` を選んだ状態で `VERITAS_DATABASE_URL` が未設定の場合は、既存の backend validation（`validate_backend_config()`）により起動失敗します。
- `secure/prod`: PostgreSQL TrustLog + `VERITAS_DATABASE_URL` + encryption key が必須で、未充足時は fail-closed で起動停止します。
- 現在の判定結果は `/v1/health` と `/v1/status` の `security_posture.trustlog_secure_default` で確認できます。

## Type B Summary: Bind Coverage reviewer evidence（英語正本準拠）

- 証跡ファイル（英語正本）:
  - `docs/en/validation/bind-coverage-evidence.latest.json`
  - `docs/en/validation/bind-coverage-evidence.latest.md`
- 再生成コマンド:
  - `python scripts/governance/export_bind_coverage_evidence.py`
- この証跡は runtime route の分類カバレッジを示しますが、法的認証や全業務安全性の証明ではありません。
- `audited_exemption` は定期的な governance review の対象です。
