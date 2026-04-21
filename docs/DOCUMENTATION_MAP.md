# Documentation Map (Bilingual Structure)

# ドキュメント対応表（バイリンガル構造）

---

## Entrypoints / 入口

- Universal Index / 総合インデックス: [docs/INDEX.md](INDEX.md)
- English Hub: [docs/en/README.md](en/README.md)
- 日本語入口: [docs/ja/README.md](ja/README.md)
- Bilingual Rules / 運用ルール: [docs/BILINGUAL_RULES.md](BILINGUAL_RULES.md)
- Path Migration / パス移行表: [docs/PATH_MIGRATION.md](PATH_MIGRATION.md)

---

## Bilingual Correspondence Table / 英日対応表

### Type A: EN + JA Both Maintained / 英日両方維持

| EN Path | JA Path | Status |
|---------|---------|--------|
| `README.md` | `README_JP.md` | EN/JA fully paired |
| `docs/INDEX.md` | (same file, bilingual) | Bilingual |
| `docs/en/guides/migration-guide.md` | (same file, bilingual) | Bilingual |
| — | `docs/ja/guides/user-manual.md` | JA primary, EN planned |

### Type B: EN Canonical Only / 英語正本のみ

#### Operations / 運用

| EN Path | Status | Description |
|---------|--------|-------------|
| `docs/en/operations/postgresql-production-guide.md` | EN only | PostgreSQL production guide |
| `docs/en/operations/postgresql-drill-runbook.md` | EN only | Recovery drill runbook |
| `docs/en/operations/security-hardening.md` | EN only | Security hardening checklist |
| `docs/en/operations/database-migrations.md` | EN only | Alembic migration guide |
| `docs/en/operations/operational-readiness-runbook.md` | EN only | Pre-launch readiness |
| `docs/en/operations/release-process.md` | EN only | Release workflow |
| `docs/en/operations/env-reference.md` | EN only | Environment variables |
| `docs/en/operations/dependency-profiles.md` | EN only | Dependency install profiles |
| `docs/en/operations/legacy-path-cleanup.md` | EN only | Storage transition tracker |
| `docs/en/operations/governance-artifact-signing.md` | EN only | Governance signing operations |
| `docs/en/operations/memory_pickle_migration.md` | EN only | Memory pickle migration |
| `docs/en/operations/trustlog_observability.md` | EN only | TrustLog observability |

#### Validation / 検証

| EN Path | Status | Description |
|---------|--------|-------------|
| `docs/en/validation/production-validation.md` | EN only | Production validation strategy |
| `docs/en/validation/backend-parity-coverage.md` | EN only | JSONL vs PostgreSQL parity |
| `docs/en/validation/external-audit-readiness.md` | EN only | External audit evidence pack |
| `docs/en/validation/technical-proof-pack.md` | EN only | External review proof-pack entrypoint |
| `docs/en/validation/governance-capability-matrix.md` | EN only | Governance implemented/pending matrix |
| `docs/en/validation/validation-evidence-map.md` | EN only | Validation layer to artifact mapping |
| `docs/en/validation/aml-kyc-pilot-evidence-map.md` | EN only | AML/KYC pilot evidence map |
| `docs/en/validation/external-reviewer-checklist.md` | EN only | External reviewer verification checklist |
| `docs/en/validation/implemented-vs-pending-boundary.md` | EN only | Implemented vs pending boundary |
| `docs/en/validation/short-dd-summary.md` | EN only | Short due-diligence summary |
| `docs/en/validation/benchmark-reproducibility-appendix.md` | EN only | Optional benchmark/repro appendix |

#### Governance / ガバナンス

| EN Path | Status | Description |
|---------|--------|-------------|
| `docs/en/governance/governance-artifact-lifecycle.md` | EN only | Artifact lifecycle |

#### Guides / ガイド

| EN Path | Status | Description |
|---------|--------|-------------|
| `docs/en/guides/demo-script.md` | EN only | 3-minute demo script |
| `docs/en/guides/governance-policy-bundle-promotion.md` | EN only | Operator-facing policy bundle promotion workflow |

#### Architecture / アーキテクチャ

| EN Path | Status | Description |
|---------|--------|-------------|
| `docs/architecture/continuation_enforcement_design_note.md` | EN only | Continuation enforcement design |
| `docs/architecture/continuation_runtime_adr.md` | EN only | Continuation runtime ADR |
| `docs/architecture/continuation_runtime_architecture_note.md` | EN only | Continuation runtime architecture |
| `docs/architecture/continuation_runtime_glossary.md` | EN only | Continuation runtime glossary |
| `docs/architecture/continuation_runtime_rollout.md` | EN only | Continuation runtime rollout |
| `docs/architecture/core_responsibility_boundaries.md` | EN only | Component responsibility boundaries |
| `docs/architecture/trustlog_storage_consolidation.md` | EN only | TrustLog storage consolidation |

#### EU AI Act / EU AI法

| EN Path | Status | Description |
|---------|--------|-------------|
| `docs/eu_ai_act/bias_assessment_report.md` | EN only | Bias assessment |
| `docs/eu_ai_act/continuous_risk_monitoring.md` | EN only | Risk monitoring |
| `docs/eu_ai_act/intended_purpose.md` | EN only | Intended purpose statement |
| `docs/eu_ai_act/model_card_gpt41_mini.md` | EN only | Model card |
| `docs/eu_ai_act/performance_metrics.md` | EN only | Performance metrics |
| `docs/eu_ai_act/risk_assessment.md` | EN only | Risk assessment |
| `docs/eu_ai_act/risk_classification_matrix.md` | EN only | Risk classification matrix |
| `docs/eu_ai_act/technical_documentation.md` | EN only | Technical documentation |
| `docs/eu_ai_act/third_party_model_dpa_checklist.md` | EN only | Third-party model DPA checklist |

#### UI / Frontend

| EN Path | Status | Description |
|---------|--------|-------------|
| `docs/ui/README_UI.md` | EN only | UI monorepo quickstart |
| `docs/ui/architecture.md` | EN only | UI architecture notes |
| `docs/ui/integration_plan.md` | EN only | UI integration plan |
| `docs/ui/PREVIEW_PAGES_JP.md` | JA only | UI preview pages (JA) |

#### Other / その他

| EN Path | Status | Description |
|---------|--------|-------------|
| `docs/benchmarks/VERITAS_EVIDENCE_BENCHMARK_PLAN.md` | EN only | Evidence benchmark plan |
| `docs/press/governance_control_plane_upgrade_2026-04.md` | EN only | Governance upgrade press summary |
| `docs/en/notes/chainlit.md` | EN only | Chainlit integration notes |

#### EN Reviews

| EN Path | Status | Description |
|---------|--------|-------------|
| `docs/en/reviews/code_review_2025.md` | EN only | 2025 code review |
| `docs/en/reviews/code_review_report.md` | EN only | Code review report |
| `docs/en/reviews/frontend_review.md` | EN only | Frontend review |
| `docs/en/reviews/repository_review.md` | EN only | Repository review |

### Type C: JA Only / 日本語のみ

#### JA Governance / ガバナンス

| JA Path | Status | Description |
|---------|--------|-------------|
| `docs/ja/governance/eu-ai-act-compliance-review.md` | JA only | EU AI Act準拠レビュー |
| `docs/ja/governance/user-guide-eu-ai-act.md` | JA only | エンドユーザー向けEU AI Act使用説明書 |
| `docs/ja/governance/policy-as-code.md` | JA only | Policy-as-Code解説 |

#### JA Operations / 運用

| JA Path | Status | Description |
|---------|--------|-------------|
| `docs/ja/operations/enterprise_slo_sli_runbook_ja.md` | JA only | Enterprise SLO/SLI運用Runbook |
| `docs/ja/operations/runtime-data-policy.md` | JA only | ランタイムデータポリシー |

#### JA Validation / 検証

| JA Path | Status | Description |
|---------|--------|-------------|
| `docs/ja/validation/coverage-report.md` | JA only | テストカバレッジレポート |
| `docs/ja/validation/coverage-after-hardening.md` | JA only | テスト強化後カバレッジ追跡 |

#### JA Guides / ガイド

| JA Path | Status | Description |
|---------|--------|-------------|
| `docs/ja/guides/user-manual.md` | JA only | VERITAS OS総合取り扱い説明書 |
| `docs/ja/guides/fuji-error-codes.md` | JA only | FUJIエラーコードリファレンス |
| `docs/ja/guides/fuji-eu-enterprise-strict-usage.md` | JA only | FUJI EU Strict Pack使い方 |
| `docs/ja/guides/self-healing-loop.md` | JA only | 自己修復ループ解説 |

#### JA Reviews / レビュー (65+ files)

See [docs/ja/reviews/README.md](ja/reviews/README.md) for the full index.
Key entry points:
- `docs/ja/reviews/codex_start_here_ja.md` — Start here
- `docs/ja/reviews/code_review_status_ja.md` — Current status
- `docs/ja/reviews/code-review-document-map.md` — Document map

#### JA Audits / 監査

| JA Path | Status | Description |
|---------|--------|-------------|
| `docs/ja/audits/markdown_information_architecture_audit_2026_04_07_ja.md` | JA only | Markdown情報設計監査 |
| `docs/ja/audits/replay_audit_ja.md` | JA only | リプレイ監査 |

---

## Archive / アーカイブ

Archived documents are historical snapshots. They are not actively maintained.

| Path | Original Location | Language |
|------|--------------------|----------|
| `docs/archive/reviews/repository-review-2026-04-07.md` | Root | EN |
| `docs/archive/reviews/review-current-improvements-2026-03-30.md` | Root | JA |
| `docs/archive/operations/enterprise-slo-sli-runbook-jp-legacy.md` | `docs/operations/` | JA |
| `docs/archive/notes/*` (20 files) | `docs/notes/` | Mixed |

---

## Language Split Policy / 言語分離ポリシー

- `docs/en/**`: English primary docs
- `docs/ja/**`: Japanese primary docs
- `docs/architecture/`, `docs/eu_ai_act/`, `docs/ui/`, `docs/benchmarks/`, `docs/press/`: Language-neutral categories (EN canonical)
- `docs/archive/**`: Historical documents (original language preserved)

For detailed rules, see [BILINGUAL_RULES.md](BILINGUAL_RULES.md).
