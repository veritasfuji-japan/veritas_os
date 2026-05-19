# TrustLog production readiness checklist

This checklist is an operator-facing readiness checklist for TrustLog production posture.
It summarizes what must be configured before treating a deployment as production-ready.
It complements, but does not replace, the PostgreSQL production guide, runtime startup validation,
CI checks, and live provider validation.
Passing this checklist is not sufficient by itself and does not certify compliance.

## Scope and non-scope

### Scope

- TrustLog production posture
- PostgreSQL TrustLog backend
- managed signing
- WORM / immutable mirror
- transparency anchoring
- startup fail-fast
- operator CLI check
- evidence links / tests

### Non-scope

- real KMS connectivity proof
- real DB connectivity proof
- real WORM retention proof
- legal/compliance certification
- external audit attestation
- end-to-end live provider validation

## Readiness checklist

| Area | Required check | How to verify | Expected result | Notes |
| --- | --- | --- | --- | --- |
| Runtime posture trigger | `VERITAS_ENV` or `VERITAS_POSTURE` is strict, or `VERITAS_REQUIRE_PRODUCTION_TRUSTLOG_POSTURE` is truthy | Inspect deployment env | One of `prod`/`production`/`secure`/`hardened` triggers is active | Strict aliases are shared with startup fail-fast semantics |
| TrustLog backend | `VERITAS_TRUSTLOG_BACKEND=postgresql` | Run `make check-trustlog-production-posture` | No failure for backend | `jsonl` is dev/demo only |
| Database URL | `VERITAS_DATABASE_URL` or `DATABASE_URL` set | Run checker / inspect secret injection | No database URL failure | Do not print secrets in logs |
| Encryption key | `VERITAS_ENCRYPTION_KEY` set | Run checker / inspect secret source | No encryption key failure | Use external secret manager in production |
| Encryption backend | `cryptography`-backed AES-256-GCM is available when production posture is active | Run checker and inspect `get_encryption_status()` | `backend_available=true`, `backend_required=true`, `backend_acceptable=true` | HMAC-CTR fallback remains allowed for dev/staging only; do not move `cryptography` into core dependency without release approval |
| Managed signer | `VERITAS_TRUSTLOG_SIGNER_BACKEND` resolves to `aws_kms` | Run checker | No signer backend failure | `aws_kms_ed25519` is accepted; `file`/`file_ed25519` fail |
| KMS key id | `VERITAS_TRUSTLOG_KMS_KEY_ID` set when signer resolves to `aws_kms` | Run checker / inspect KMS env | No `KMS_KEY_ID` failure | Checker does not call KMS |
| Break-glass override | `VERITAS_TRUSTLOG_ALLOW_INSECURE_SIGNER_IN_PROD` must not be relied on | Inspect env | Checker still fails file signer even if override is set | Production posture checker ignores the flag |
| WORM / immutable mirror | Use appropriate mirror backend/path | Run checker and core posture startup validation | Checker warning-free or documented warning; core strict posture rejects incapable mirror | Checker warning-only; core strict posture can hard-error on capability |
| S3 Object Lock mirror | If `VERITAS_TRUSTLOG_MIRROR_BACKEND=s3_object_lock`, set bucket and prefix | Run checker | No `s3_object_lock` mirror warning | Checker does not verify S3 retention |
| Transparency required | Transparency should be required in strict posture unless explicitly disabled | Run checker | No "transparency anchoring is not required" warning | Explicit disable is warning-level |
| Transparency log path | If local anchor is selected and transparency is required, set `VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH` | Run checker | No local transparency log path warning | TSA-specific validation is not added here |
| Noop anchor | Do not use `noop`/`none`/`no_op` anchor in production posture | Run checker | No noop anchor warning | Checker warning-only; core strict posture hard-errors when transparency required |
| Startup fail-fast | Production posture failures stop startup | Start app with strict env and invalid TrustLog config in staging test | `RuntimeError` / startup refusal | Do not test by breaking production |
| Contract tests | checker/core alignment tests pass | `python -m pytest -q veritas_os/tests/test_trustlog_posture_contract.py` | All pass | Guards drift between checker and core posture validation |
| CLI checker | operator CLI passes or only expected warnings remain | `make check-trustlog-production-posture` | Exit 0; warnings reviewed | Exit 0 with warnings is not full readiness proof |
| Live provider validation | Real DB/KMS/WORM/TSA connectivity and retention validated separately | Run deployment-specific validation / cloud-native checks | Documented evidence | Not covered by this checker |

## Command quick reference

- `make check-trustlog-production-posture`
- `python -m scripts.security.check_trustlog_production_posture`
- `python -m pytest -q veritas_os/tests/test_trustlog_posture_contract.py`
- `python -m pytest -q veritas_os/tests/test_trustlog_production_posture.py`
- `python -m pytest -q veritas_os/tests/test_posture.py`
- `python -m pytest -q veritas_os/tests/test_trustlog_backend_normalization.py`

## Interpreting results

- Failures are blocking for production posture.
- Warnings are non-fatal in the checker.
- Some warning-only checker findings can still be hard failures in core strict posture validation.
- The contract tests intentionally cover this warning-vs-hard-error divergence.
- Passing the checker is necessary but not sufficient for production readiness.
- Real DB/KMS/WORM/transparency anchoring must be validated separately.

## Evidence map

- Runtime startup fail-fast: `veritas_os/api/startup_health.py`
- Production posture checker: `veritas_os/security/trustlog_production_posture.py`
- Backend normalization: `veritas_os/security/trustlog_backend_normalization.py`
- Core posture validation: `veritas_os/core/posture.py`
- CLI wrapper: `scripts/security/check_trustlog_production_posture.py`
- Checker tests: `veritas_os/tests/test_trustlog_production_posture.py`
- Contract tests: `veritas_os/tests/test_trustlog_posture_contract.py`
- Normalization tests: `veritas_os/tests/test_trustlog_backend_normalization.py`
- Operational guide: `docs/en/operations/postgresql-production-guide.md`
