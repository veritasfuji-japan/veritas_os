# Path Migration Table

# パス移行表

This table maps old file paths to their new locations after the bilingual docs restructure.
Use this to update any external links, bookmarks, or CI references.

この表は、バイリンガルドキュメント再整理後の旧パス→新パスの対応表です。
外部リンク、ブックマーク、CI参照の更新にご利用ください。

---

## Root-Level Files / ルートレベルファイル

| Old Path | New Path | Category |
|----------|----------|----------|
| `REPOSITORY_REVIEW_2026-04-07.md` | `docs/archive/reviews/repository-review-2026-04-07.md` | Archive |
| `REVIEW_CURRENT_IMPROVEMENTS_2026-03-30.md` | `docs/archive/reviews/review-current-improvements-2026-03-30.md` | Archive |

## docs/ Root → EN Operations

| Old Path | New Path |
|----------|----------|
| `docs/postgresql-production-guide.md` | `docs/en/operations/postgresql-production-guide.md` |
| `docs/postgresql-drill-runbook.md` | `docs/en/operations/postgresql-drill-runbook.md` |
| `docs/security-hardening.md` | `docs/en/operations/security-hardening.md` |
| `docs/database-migrations.md` | `docs/en/operations/database-migrations.md` |
| `docs/OPERATIONAL_READINESS_RUNBOOK.md` | `docs/en/operations/operational-readiness-runbook.md` |
| `docs/RELEASE_PROCESS.md` | `docs/en/operations/release-process.md` |
| `docs/env-reference.md` | `docs/en/operations/env-reference.md` |
| `docs/dependency-profiles.md` | `docs/en/operations/dependency-profiles.md` |
| `docs/legacy-path-cleanup.md` | `docs/en/operations/legacy-path-cleanup.md` |

## docs/ Root → EN Validation

| Old Path | New Path |
|----------|----------|
| `docs/PRODUCTION_VALIDATION.md` | `docs/en/validation/production-validation.md` |
| `docs/BACKEND_PARITY_COVERAGE.md` | `docs/en/validation/backend-parity-coverage.md` |
| `docs/EXTERNAL_AUDIT_READINESS.md` | `docs/en/validation/external-audit-readiness.md` |

## docs/ Root → EN Governance

| Old Path | New Path |
|----------|----------|
| `docs/governance_artifact_lifecycle.md` | `docs/en/governance/governance-artifact-lifecycle.md` |

## docs/ Root → EN Guides

| Old Path | New Path |
|----------|----------|
| `docs/demo-3min-script.md` | `docs/en/guides/demo-script.md` |
| `docs/migration-guide.md` | `docs/en/guides/migration-guide.md` |

## docs/ Root → JA Validation

| Old Path | New Path |
|----------|----------|
| `docs/COVERAGE_REPORT.md` | `docs/ja/validation/coverage-report.md` |
| `docs/COVERAGE_AFTER_TEST_HARDENING.md` | `docs/ja/validation/coverage-after-hardening.md` |

## docs/ Root → JA Governance

| Old Path | New Path |
|----------|----------|
| `docs/eu_ai_act_compliance_review.md` | `docs/ja/governance/eu-ai-act-compliance-review.md` |
| `docs/user_guide_eu_ai_act.md` | `docs/ja/governance/user-guide-eu-ai-act.md` |
| `docs/policy_as_code.md` | `docs/ja/governance/policy-as-code.md` |

## docs/ Root → JA Operations

| Old Path | New Path |
|----------|----------|
| `docs/RUNTIME_DATA_POLICY.md` | `docs/ja/operations/runtime-data-policy.md` |

## docs/ Root → JA Guides

| Old Path | New Path |
|----------|----------|
| `docs/VERITAS_FULL_USER_MANUAL_JP.md` | `docs/ja/guides/user-manual.md` |
| `docs/fuji_eu_enterprise_strict_usage.md` | `docs/ja/guides/fuji-eu-enterprise-strict-usage.md` |
| `docs/fuji_error_codes.md` | `docs/ja/guides/fuji-error-codes.md` |
| `docs/self_healing_loop.md` | `docs/ja/guides/self-healing-loop.md` |

## docs/operations/ → Merged

| Old Path | New Path | Notes |
|----------|----------|-------|
| `docs/operations/governance_artifact_signing_operations.md` | `docs/en/operations/governance-artifact-signing.md` | EN canonical |
| `docs/operations/ENTERPRISE_SLO_SLI_RUNBOOK_JP.md` | `docs/archive/operations/enterprise-slo-sli-runbook-jp-legacy.md` | Legacy; canonical is `docs/ja/operations/enterprise_slo_sli_runbook_ja.md` |

## docs/notes/ → Archive

| Old Path | New Path |
|----------|----------|
| `docs/notes/CODE_REVIEW_DOCUMENT_MAP.md` | `docs/ja/reviews/code-review-document-map.md` |
| `docs/notes/AGI_BENCH_INTEGRATION_GUIDE.md` | `docs/archive/notes/AGI_BENCH_INTEGRATION_GUIDE.md` |
| `docs/notes/AGI_progress_stages.md` | `docs/archive/notes/AGI_progress_stages.md` |
| `docs/notes/BENCHMARK_MIGRATION_GUIDE.md` | `docs/archive/notes/BENCHMARK_MIGRATION_GUIDE.md` |
| `docs/notes/CODE_REVIEW_REPORT_20260204.md` | `docs/archive/notes/CODE_REVIEW_REPORT_20260204.md` |
| `docs/notes/CORE_COVERAGE_SNAPSHOT_JP.md` | `docs/archive/notes/CORE_COVERAGE_SNAPSHOT_JP.md` |
| `docs/notes/CRITIQUE_DEBATE_REVIEW.md` | `docs/archive/notes/CRITIQUE_DEBATE_REVIEW.md` |
| `docs/notes/CRITIQUE_INTEGRATION_GUIDE.md` | `docs/archive/notes/CRITIQUE_INTEGRATION_GUIDE.md` |
| `docs/notes/DEBATE_CHANGES_DIFF.md` | `docs/archive/notes/DEBATE_CHANGES_DIFF.md` |
| `docs/notes/DEBATE_IMPROVEMENT_REPORT.md` | `docs/archive/notes/DEBATE_IMPROVEMENT_REPORT.md` |
| `docs/notes/DEPLOYMENT_COMPLETE.md` | `docs/archive/notes/DEPLOYMENT_COMPLETE.md` |
| `docs/notes/MEMORY_IMPROVEMENT_REPORT.md` | `docs/archive/notes/MEMORY_IMPROVEMENT_REPORT.md` |
| `docs/notes/PAPER_REVIEW_V1.md` | `docs/archive/notes/PAPER_REVIEW_V1.md` |
| `docs/notes/TRUSTLOG_VERIFICATION_REPORT.md` | `docs/archive/notes/TRUSTLOG_VERIFICATION_REPORT.md` |
| `docs/notes/VERITAS_CODE_REVIEW_PRINCIPLES.md` | `docs/archive/notes/VERITAS_CODE_REVIEW_PRINCIPLES.md` |
| `docs/notes/VERITAS_EVALUATION_REPORT.md` | `docs/archive/notes/VERITAS_EVALUATION_REPORT.md` |
| `docs/notes/VERITAS_IMPROVEMENT_SUMMARY.md` | `docs/archive/notes/VERITAS_IMPROVEMENT_SUMMARY.md` |
| `docs/notes/VERITAS_REPORT.md` | `docs/archive/notes/VERITAS_REPORT.md` |
| `docs/notes/WORLD_MIGRATION_GUIDE.md` | `docs/archive/notes/WORLD_MIGRATION_GUIDE.md` |
| `docs/notes/bilingual_docs_reorganization_report.md` | `docs/archive/notes/bilingual_docs_reorganization_report.md` |
| `docs/notes/code_review_20260205.md` | `docs/archive/notes/code_review_20260205.md` |
