# 外部セキュリティレビュー対応サマリー

本資料は、外部セキュリティレビューで指摘された項目に対する実装修正の整理である。
第三者認証、法的認証、本番SLA、脆弱性ゼロを意味しない。
DD・監査・PoC担当者が、指摘内容・対応PR・確認方法を追えるようにするための資料である。
英語版が正本、日本語版は補助説明である。

## 1. スコープ

本サマリーは、レビュー指摘 #1 から #8 を対象とする。

重点領域:

- WebSocket API key auth
- TrustLog JSONL append integrity
- RBAC fallback
- HMAC nonce registration
- Docker Compose credentials
- local signing key file hardening
- WAT verifier post-check duplication
- KMS verify error handling

## 2. 対応マトリクス

| Finding | Severity | Original risk | Remediation | PR | Verification |
| --- | --- | --- | --- | --- | --- |
| #1 WebSocket multi-key auth | High | WebSocket auth did not honor VERITAS_API_KEYS multi-key config consistently with HTTP auth. | Aligned WebSocket API key validation with multi-key/single-key semantics and fail-closed behavior. | #1660 | WebSocket multi-key / malformed multi-key / legacy fallback tests. |
| #2 TrustLog JSONL multi-worker race | High | JSONL TrustLog append could race across workers and fork the hash chain. | Added process-level JSONL lock around read-last-entry / prev_hash / serialization / append critical section; kept mirror/anchor side effects outside the lock; anchored persisted JSONL snapshot. | #1660 | TrustLog JSONL lock tests, persisted-entry anchor hash tests. |
| #3 RBAC fallback admin | Medium | Role resolution failure could fall back to admin. | Changed fallback to least-privilege auditor while preserving valid legacy admin and multi-key roles. | #1661 | RBAC fallback tests. |
| #4 HMAC nonce poisoning | Medium | Invalid signatures could consume nonces before HMAC verification. | Separated nonce shape validation from nonce registration; registration now happens only after valid signature. | #1661, #1664 | Invalid signature does not consume nonce, oversized nonce rejected early, replay still rejected. |
| #5 Docker Compose default credentials | Medium | Default DB password and default admin BFF token could be used accidentally. | Removed unsafe defaults, required explicit .env credentials, added .env.example placeholders and compose security docs. | #1666 | Docker Compose security tests and deployment env default checks. |
| #6 Local signing key TOCTOU / symlink | Low | Private key load used path stat/read flow with symlink/TOCTOU exposure. | Moved to fd-based read, fstat checks, O_NOFOLLOW, O_CLOEXEC, O_NONBLOCK, lstat symlink rejection, regular-file and permission checks. | #1667 | Signing key file hardening tests. |
| #7 WAT verifier duplicated post-checks | Low | Replay/expiry/revocation/partial/timestamp checks were duplicated across observable-list and non-list paths. | Centralized post-validation checks into shared helper while preserving output contract. | #1669 | Observable-list and non-list parity tests for validation_status, failure_type, drift_vector, admissibility_state. |
| #8 KMS AttributeError swallowed | Low | Provider/client AttributeError could be reported as ordinary invalid signature. | Stopped swallowing AttributeError in GCP KMS verify path; preserved False for InvalidSignature / ValueError / TypeError. | #1668 | KMS verify error handling tests. |

## 3. 確認コマンド

- `pytest -q veritas_os/tests/test_docker_compose_security.py`
- `pytest -q veritas_os/tests/test_signing_key_file_hardening.py`
- `pytest -q veritas_os/tests/test_kms_verify_error_handling.py`
- `pytest -q veritas_os/tests/test_wat_verifier_post_checks.py`
- `pytest -q veritas_os/tests/unit/test_server_api.py`
- `pytest -q veritas_os/tests/unit/test_trustlog.py`
- `python scripts/quality/check_deployment_env_defaults.py`
- `python -m scripts.quality.check_bilingual_docs`

CI, Security Gates, CodeQL custom, and Runtime Pickle Guard が green であることを確認する。

## 4. 残存境界

- 正式なペネトレーションテストの代替ではない。
- EU AI Act等の法的認証ではない。
- 本番導入では managed secrets / durable storage / PostgreSQL TrustLog backend / deployment-specific review が必要。
- JSONL TrustLog backend は local/file-backed 向けに hardening 済みだが、本番では PostgreSQL backend を推奨。
- KMS/Vault統合は provider ごとの運用検証が必要。

## 5. レビュアーノート

- これらの対応により、前回レビュー時点の明確なDD阻害要因は縮小された。
- 一方で、エンタープライズ本番調達に向けては、実測性能指標・運用体制計画・第三者の法務/セキュリティレビューが引き続き必要である。
