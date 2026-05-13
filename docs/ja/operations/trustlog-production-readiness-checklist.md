# TrustLog 本番 readiness チェックリスト

このチェックリストは、TrustLog の本番 posture を短時間で確認するための operator-facing な文書です。
本番相当として扱う前に必要な設定項目を要約します。
PostgreSQL production guide、runtime startup validation、CI checks、live provider validation を補完するものであり、置き換えるものではありません。
このチェックリストの通過だけでは十分ではなく、compliance を保証するものでもありません。

## 対象範囲と対象外

### 対象範囲

- TrustLog production posture
- PostgreSQL TrustLog backend
- managed signing
- WORM / immutable mirror
- transparency anchoring
- startup fail-fast
- operator CLI check
- evidence links / tests

### 対象外

- real KMS connectivity proof
- real DB connectivity proof
- real WORM retention proof
- legal/compliance certification
- external audit attestation
- end-to-end live provider validation

## Readiness チェックリスト

| 領域 | 必須確認 | 確認方法 | 期待結果 | 補足 |
| --- | --- | --- | --- | --- |
| Runtime posture trigger | `VERITAS_ENV` または `VERITAS_POSTURE` が strict 値、または `VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE` が truthy | deployment env を確認 | `prod` / `production` / `secure` / `hardened` のいずれかが有効 | strict alias は startup fail-fast semantics と共有されます |
| TrustLog backend | `VERITAS_TRUSTLOG_BACKEND=postgresql` | `make check-trustlog-production-posture` を実行 | backend failure が出ない | `jsonl` は dev/demo 用です |
| Database URL | `VERITAS_DATABASE_URL` または `DATABASE_URL` が設定されている | checker 実行 / secret injection を確認 | database URL failure が出ない | secret 値をログに出さないでください |
| Encryption key | `VERITAS_ENCRYPTION_KEY` が設定されている | checker 実行 / secret source を確認 | encryption key failure が出ない | production では外部 secret manager を使います |
| Managed signer | `VERITAS_TRUSTLOG_SIGNER_BACKEND` が `aws_kms` に解決される | checker を実行 | signer backend failure が出ない | `aws_kms_ed25519` は許可、`file` / `file_ed25519` は failure です |
| KMS key id | signer が `aws_kms` に解決される場合 `VERITAS_TRUSTLOG_KMS_KEY_ID` が設定されている | checker 実行 / KMS 関連 env を確認 | `KMS_KEY_ID` failure が出ない | checker は KMS へ接続しません |
| Break-glass override | `VERITAS_TRUSTLOG_ALLOW_INSECURE_SIGNER_IN_PROD` に依存しない | env を確認 | override があっても file signer は failure | production posture checker はこのフラグを無視します |
| WORM / immutable mirror | 適切な mirror backend/path を使う | checker と core posture startup validation を実行 | checker warning なし、または warning を記録済み。capability 不足なら core strict posture が拒否 | checker では warning-only、core strict posture では hard-error になり得ます |
| S3 Object Lock mirror | `VERITAS_TRUSTLOG_MIRROR_BACKEND=s3_object_lock` の場合は bucket/prefix を設定する | checker を実行 | `s3_object_lock` mirror warning が出ない | checker は S3 retention を検証しません |
| Transparency required | strict posture では transparency required を基本とし、明示 disable は例外運用に限定する | checker を実行 | "transparency anchoring is not required" warning が出ない | 明示 disable は warning-level です |
| Transparency log path | local anchor かつ transparency required の場合 `VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH` を設定する | checker を実行 | local transparency log path warning が出ない | TSA-specific validation はこの checker では未追加です |
| Noop anchor | production posture で `noop` / `none` / `no_op` anchor を使わない | checker を実行 | noop anchor warning が出ない | checker では warning-only、core strict posture では hard-error になり得ます |
| Startup fail-fast | production posture の failure で startup が停止する | strict env + 不正 TrustLog 設定で staging 検証を行う | `RuntimeError` / startup refusal になる | production 本番を壊して試験しないでください |
| Contract tests | checker/core alignment tests が通る | `python -m pytest -q veritas_os/tests/test_trustlog_posture_contract.py` | 全件 pass | checker と core posture validation の drift 防止です |
| CLI checker | operator CLI が pass、または expected warnings のみ | `make check-trustlog-production-posture` を実行 | Exit 0、warnings をレビュー済み | warnings 付き Exit 0 は readiness の証明ではありません |
| Live provider validation | 実 DB/KMS/WORM/TSA の接続・retention を別途検証する | 環境固有の検証手順 / クラウド側チェックを実行 | 証跡が文書化されている | checker の対象外です |

## コマンド早見表

- `make check-trustlog-production-posture`
- `python -m scripts.security.check_trustlog_production_posture`
- `python -m pytest -q veritas_os/tests/test_trustlog_posture_contract.py`
- `python -m pytest -q veritas_os/tests/test_trustlog_production_posture.py`
- `python -m pytest -q veritas_os/tests/test_posture.py`
- `python -m pytest -q veritas_os/tests/test_trustlog_backend_normalization.py`

## 結果の読み方

- failure は production posture では blocking です。
- warning は checker では non-fatal です。
- checker の warning-only 指摘でも、core strict posture validation では hard failure になり得ます。
- contract tests は warning-vs-hard-error divergence を意図的にカバーしています。
- checker 通過は必要条件ですが十分条件ではありません。
- 実 DB/KMS/WORM/transparency anchoring は別途検証が必要です。

## 証跡マップ

- Runtime startup fail-fast 実装: `veritas_os/api/startup_health.py`
- Production posture checker 実装: `veritas_os/security/trustlog_production_posture.py`
- Backend normalization 実装: `veritas_os/security/trustlog_backend_normalization.py`
- Core posture validation 実装: `veritas_os/core/posture.py`
- CLI wrapper: `scripts/security/check_trustlog_production_posture.py`
- Checker テスト: `veritas_os/tests/test_trustlog_production_posture.py`
- Contract テスト: `veritas_os/tests/test_trustlog_posture_contract.py`
- Normalization テスト: `veritas_os/tests/test_trustlog_backend_normalization.py`
- Operational guide: `docs/en/operations/postgresql-production-guide.md`

## 英語正本

この日本語版は運用者向けの説明補助です。厳密な仕様・英語正本は [TrustLog production readiness checklist](../../en/operations/trustlog-production-readiness-checklist.md) を参照してください。
