# VERITAS OS Markdown Information Architecture Audit (2026-04-07)

## Executive Summary

- 監査対象は `node_modules` を除くリポジトリ管理下の Markdown **136 ファイル**です。
- 最大の構造課題は、(1) ルート直下のレビュー文書散在、(2) `docs/review` と `docs/reviews` の二重運用、(3) 日英混在文書の多さ、(4) 命名規則の不統一です。
- 本レポートは**監査版**であり、ファイル移動・改名・削除は実施していません。

## Current Problems

1. **Root clutter**: `FRONTEND_REVIEW.md`, `LARGE_FILE_REVIEW.md`, `REPOSITORY_REVIEW.md`, `REVIEW_CURRENT_IMPROVEMENTS_2026-03-30.md` などがルートに散在。
2. **命名規則の不統一**: `code-review-YYYY-MM-DD` / `code_review_YYYY_MM_DD` / `..._JP` / `..._ja_...` が混在。
3. **日英ペア不明瞭**: `README.md` と `README_JP.md` 以外はペアリンクが弱い。
4. **Mixed-language 文書の多発**: 多数のレビュー文書が英日混在で、翻訳資産として再利用しにくい。
5. **`docs/review` vs `docs/reviews`**: 同種文書が複数ディレクトリで重複管理。
6. **index不足**: ドキュメント全体の統合 index / map が不足。

## Full Markdown Inventory

| current path | title | primary language | document type | probable counterpart | issues found | recommended action |
|---|---|---|---|---|---|---|
| `CONTRIBUTING.md` | Contributing to VERITAS | EN | contributing | `-` | - | keep |
| `FRONTEND_REVIEW.md` | Frontend Code Review — Veritas OS | EN | review | `-` | root clutter | move |
| `LARGE_FILE_REVIEW.md` | 巨大ファイルレビュー: 技術負債候補 | Mixed | review | `-` | root clutter, mixed-language | move, split |
| `README.md` | VERITAS OS v2.0 — Auditable Decision OS for LLM Agents (Proto-AGI Skeleton) | EN | README | `README_JP.md` | - | keep |
| `README_JP.md` | VERITAS OS v2.0 — LLMエージェント向け監査可能な意思決定OS（Proto-AGI Skeleton） | Mixed | README | `README.md` | mixed-language, suffix inconsistency | split, rename |
| `REPOSITORY_REVIEW.md` | Veritas OS — Full Repository Review | EN | review | `-` | root clutter | move |
| `REVIEW_CURRENT_IMPROVEMENTS_2026-03-30.md` | VERITAS OS 改善点レビュー（2026-03-30） | Mixed | review | `-` | root clutter, mixed-language | move, split |
| `SECURITY.md` | Security Policy | EN | security | `-` | - | keep |
| `chainlit.md` | Welcome to Chainlit! 🚀🤖 | EN | other | `-` | root clutter | move |
| `docs/COVERAGE_AFTER_TEST_HARDENING.md` | Coverage Follow-up Report | Mixed | coverage | `-` | mixed-language | split |
| `docs/COVERAGE_REPORT.md` | VERITAS OS — テストカバレッジレポート（改善版） | Mixed | coverage | `-` | mixed-language | split |
| `docs/PRODUCTION_VALIDATION.md` | VERITAS OS — Production Validation Strategy | EN | other | `-` | - | keep |
| `docs/RUNTIME_DATA_POLICY.md` | Runtime Data Policy | Mixed | legal | `-` | mixed-language | split |
| `docs/VERITAS_FULL_USER_MANUAL_JP.md` | VERITAS OS 総合取り扱い説明書（全機能版） | Mixed | guide | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/architecture/continuation_runtime_adr.md` | ADR: Continuation Runtime — Architecture Decision Record | EN | other | `-` | - | keep |
| `docs/architecture/continuation_runtime_architecture_note.md` | Architecture Note: Continuation Runtime (Phase-1) | EN | note | `-` | - | keep |
| `docs/architecture/continuation_runtime_glossary.md` | Continuation Runtime — Glossary | EN | other | `-` | - | keep |
| `docs/architecture/continuation_runtime_rollout.md` | Continuation Runtime — Rollout Plan | EN | other | `-` | - | keep |
| `docs/architecture/core_responsibility_boundaries.md` | Core Responsibility Boundaries | EN | other | `-` | - | keep |
| `docs/benchmarks/VERITAS_EVIDENCE_BENCHMARK_PLAN.md` | VERITAS OS Evidence Benchmark Plan | Mixed | other | `-` | mixed-language | split |
| `docs/code-review-2026-03-24.md` | VERITAS OS コードレビュー総合報告書 | Mixed | review | `docs/code_review_2026_03_23.md` | mixed-language | split |
| `docs/code_review_2026_03_23.md` | VERITAS OS 総合コードレビュー (2026-03-23) | Mixed | review | `docs/code-review-2026-03-24.md` | mixed-language | split |
| `docs/demo-3min-script.md` | VERITAS OS — 3-Minute Demo Script | EN | other | `-` | - | keep |
| `docs/dependency-profiles.md` | VERITAS OS — Dependency Profiles | EN | other | `-` | - | keep |
| `docs/env-reference.md` | Environment Variable Reference | EN | other | `-` | - | keep |
| `docs/eu_ai_act/bias_assessment_report.md` | VERITAS OS — バイアス評価レポート | Mixed | other | `-` | mixed-language | split |
| `docs/eu_ai_act/continuous_risk_monitoring.md` | VERITAS OS — 継続的リスクモニタリング運用手順書 | Mixed | other | `-` | mixed-language | split |
| `docs/eu_ai_act/intended_purpose.md` | VERITAS OS — 意図された用途と制限 | Mixed | other | `-` | mixed-language | split |
| `docs/eu_ai_act/model_card_gpt41_mini.md` | VERITAS OS — モデルカード: OpenAI GPT-4.1-mini | Mixed | other | `-` | mixed-language | split |
| `docs/eu_ai_act/performance_metrics.md` | VERITAS OS — 精度・堅牢性指標 | Mixed | other | `-` | mixed-language | split |
| `docs/eu_ai_act/risk_assessment.md` | VERITAS OS — リスク評価と残留リスク | Mixed | other | `-` | mixed-language | split |
| `docs/eu_ai_act/risk_classification_matrix.md` | VERITAS OS — EU AI法 リスク分類マトリクス | Mixed | other | `-` | mixed-language | split |
| `docs/eu_ai_act/technical_documentation.md` | VERITAS OS — 技術文書 (附属書IV準拠) | Mixed | other | `-` | mixed-language | split |
| `docs/eu_ai_act/third_party_model_dpa_checklist.md` | VERITAS OS — 第三者モデル DPA チェックリスト | Mixed | legal | `-` | mixed-language | split |
| `docs/eu_ai_act_compliance_review.md` | VERITAS OS — EU AI Act 準拠レビュー | Mixed | review | `-` | mixed-language | split |
| `docs/fuji_error_codes.md` | FUJI Standard Codes (F-1xxx〜F-4xxx) | Mixed | other | `-` | mixed-language | split |
| `docs/fuji_eu_enterprise_strict_usage.md` | FUJI EU AI Act & Enterprise Strict Pack 使い方 | Mixed | other | `-` | mixed-language | split |
| `docs/notes/AGI_BENCH_INTEGRATION_GUIDE.md` | AGIベンチマーク統合ガイド | Mixed | guide | `-` | mixed-language | split |
| `docs/notes/AGI_progress_stages.md` | AGI_progress_stages | EN | note | `-` | - | keep |
| `docs/notes/BENCHMARK_MIGRATION_GUIDE.md` | run_benchmarks.py 移行ガイド | Mixed | guide | `-` | mixed-language | split |
| `docs/notes/CODE_REVIEW_DOCUMENT_MAP.md` | コードレビュー文書マップ（整理版） | Mixed | review | `-` | mixed-language | split |
| `docs/notes/CODE_REVIEW_REPORT_20260204.md` | VERITAS OS コードレビューレポート | Mixed | review | `-` | mixed-language | split |
| `docs/notes/CORE_COVERAGE_SNAPSHOT_JP.md` | コア部分カバレッジ・スナップショット | Mixed | coverage | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/notes/CRITIQUE_DEBATE_REVIEW.md` | Critique & Debate モジュール レビュー | Mixed | review | `-` | mixed-language | split |
| `docs/notes/CRITIQUE_INTEGRATION_GUIDE.md` | critique.py 改善版 - 統合ガイド | Mixed | guide | `-` | mixed-language | split |
| `docs/notes/DEBATE_CHANGES_DIFF.md` | DebateOS 変更点の詳細比較 | Mixed | note | `-` | mixed-language | split |
| `docs/notes/DEBATE_IMPROVEMENT_REPORT.md` | DebateOS 実用性改善レポート | Mixed | note | `-` | mixed-language | split |
| `docs/notes/DEPLOYMENT_COMPLETE.md` | 🎉 VERITAS OS 改善プロジェクト - 配置完了レポート | Mixed | note | `-` | mixed-language | split |
| `docs/notes/MEMORY_IMPROVEMENT_REPORT.md` | MemoryOS ベクトル検索修復レポート | Mixed | note | `-` | mixed-language | split |
| `docs/notes/PAPER_REVIEW_V1.md` | VERITAS OS Paper v1 - 詳細レビュー | Mixed | review | `-` | mixed-language | split |
| `docs/notes/TRUSTLOG_VERIFICATION_REPORT.md` | TrustLog実装検証レポート | Mixed | note | `-` | mixed-language | split |
| `docs/notes/VERITAS_CODE_REVIEW_PRINCIPLES.md` | VERITAS コードレビュー報告書 | Mixed | review | `-` | mixed-language | split |
| `docs/notes/VERITAS_EVALUATION_REPORT.md` | VERITAS OS 総合評価レポート | Mixed | note | `-` | mixed-language | split |
| `docs/notes/VERITAS_IMPROVEMENT_SUMMARY.md` | VERITAS OS 改善プロジェクト - 完全サマリ | Mixed | note | `-` | mixed-language | split |
| `docs/notes/VERITAS_REPORT.md` | VERITAS OS v1.0 - 最終統合レポート | Mixed | note | `-` | mixed-language | split |
| `docs/notes/WORLD_MIGRATION_GUIDE.md` | World.py 統合ガイド | Mixed | guide | `-` | mixed-language | split |
| `docs/notes/code_review_20260205.md` | VERITAS OS v2.0 全コードレビュー | Mixed | review | `-` | mixed-language | split |
| `docs/operations/ENTERPRISE_SLO_SLI_RUNBOOK_JP.md` | Enterprise SLO/SLI & 運用Runbook（2026-03-06） | Mixed | runbook | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/operations/MEMORY_PICKLE_MIGRATION.md` | MemoryOS Legacy Pickle Migration | Mixed | runbook | `-` | mixed-language | split |
| `docs/policy_as_code.md` | Policy-as-Code (Stage 3 / Runtime Adapter + Generated Tests) | Mixed | legal | `-` | mixed-language | split |
| `docs/replay_audit.md` | Replay Engine — 監査機能ドキュメント | Mixed | audit | `-` | mixed-language | split |
| `docs/review/BACKEND_CORE_PRECISION_REREVIEW_2026_03_02_JP.md` | Backend Core 精密再レビュー（Planner / Kernel / Fuji / MemoryOS） | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/BACKEND_CORE_PRECISION_REVIEW_2026_03_02_JP.md` | Backend Core 精密レビュー（Planner / Kernel / Fuji / MemoryOS） | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODEX_IMPROVEMENT_REVIEW_2026_02_24_JP.md` | CODEX 改善再レビュー（2026-02-24, JP） | Mixed | review | `docs/review/CODEX_IMPROVEMENT_REVIEW_2026_02_25_JP.md` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODEX_IMPROVEMENT_REVIEW_2026_02_25_JP.md` | CODEX 改善レビュー（2026-02-25, JP） | Mixed | review | `docs/review/CODEX_IMPROVEMENT_REVIEW_2026_02_24_JP.md` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODEX_IMPROVEMENT_REVIEW_2026_02_26_JP.md` | CODEX 改善再レビュー（2026-02-26, JP） | Mixed | review | `docs/review/CODEX_IMPROVEMENT_REVIEW_2026_02_24_JP.md` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODEX_START_HERE.md` | CODEX START HERE（レビュー着手 5 分ガイド） | Mixed | review | `-` | mixed-language | split |
| `docs/review/CODE_IMPROVEMENT_SUMMARY_JP.md` | VERITAS OS コード改善提案サマリー | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODE_REVIEW_2025.md` | VERITAS OS Comprehensive Code Review — 2025 | EN | review | `-` | - | keep |
| `docs/review/CODE_REVIEW_2026_02_10.md` | VERITAS OS 全コードレビュー（2nd Rewrite） | Mixed | review | `docs/review/CODE_REVIEW_2026_02_11.md` | mixed-language | split |
| `docs/review/CODE_REVIEW_2026_02_11.md` | VERITAS OS v2.0 - 総合コードレビュー | Mixed | review | `docs/review/CODE_REVIEW_2026_02_10.md` | mixed-language | split |
| `docs/review/CODE_REVIEW_2026_02_11_RUNTIME_CHECK.md` | VERITAS OS 全コードレビュー（再評価） | Mixed | review | `-` | mixed-language | split |
| `docs/review/CODE_REVIEW_2026_02_12.md` | コードレビュー 2026-02-12（現行スナップショット） | Mixed | review | `docs/review/CODE_REVIEW_2026_02_10.md` | mixed-language | split |
| `docs/review/CODE_REVIEW_2026_02_12_AGENT.md` | コードレビュー 2026-02-12（Agent） | Mixed | review | `docs/review/CODE_REVIEW_2026_02_15_AGENT_JP.md` | mixed-language | split |
| `docs/review/CODE_REVIEW_2026_02_13_AGENT_DETAILED_JP.md` | VERITAS OS 詳細コードレビュー（Agent版 / 2026-02-13） | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODE_REVIEW_2026_02_13_CORE.md` | コアレビュー（Planner / Kernel / Fuji / MemoryOS） | Mixed | review | `-` | mixed-language | split |
| `docs/review/CODE_REVIEW_2026_02_13_FULL_SCAN_JP.md` | VERITAS OS 全体コードレビュー（2026-02-13） | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODE_REVIEW_2026_02_14_SPAGHETTI_JP.md` | VERITAS OS 全コード スパゲッティコード診断レポート（2026-02-14） | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODE_REVIEW_2026_02_15_AGENT_JP.md` | CODE REVIEW 2026-02-15 (Agent) | Mixed | review | `docs/review/CODE_REVIEW_2026_02_12_AGENT.md` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODE_REVIEW_2026_02_16_COMPLETENESS_JP.md` | CODE REVIEW 2026-02-16（全体完成度評価 / アーカイブ） | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODE_REVIEW_2026_02_27_FULL_JP.md` | VERITAS OS 全コードレビューレポート | Mixed | review | `docs/review/CODE_REVIEW_FULL.md` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODE_REVIEW_2026_03_06_MUST_HAVE_FEATURES_JP.md` | VERITAS 全体コードレビュー（2026-03-06） | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODE_REVIEW_FATAL_BUG_SCAN_2026_03_02_JP.md` | 致命的バグ観点レビュー（2026-03-02） | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODE_REVIEW_FULL.md` | VERITAS OS v2.0 — 全コードレビュー報告書 | Mixed | review | `docs/review/CODE_REVIEW_2026_02_27_FULL_JP.md` | mixed-language | split |
| `docs/review/CODE_REVIEW_FULL_2026_02_08.md` | VERITAS OS 全コードレビュー報告書 | Mixed | review | `docs/review/CODE_REVIEW_2026_02_27_FULL_JP.md` | mixed-language | split |
| `docs/review/CODE_REVIEW_FULL_2026_03_04_AGENT_JP.md` | CODE REVIEW FULL（2026-03-04, Agent） | Mixed | review | `docs/review/CODE_REVIEW_FULL_2026_03_05_AGENT_JP.md` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODE_REVIEW_FULL_2026_03_04_JP.md` | VERITAS OS 全コードレビュー報告書 | Mixed | review | `docs/review/CODE_REVIEW_2026_02_27_FULL_JP.md` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODE_REVIEW_FULL_2026_03_05_AGENT2_JP.md` | 全コードレビュー（2026-03-05, Agent） | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODE_REVIEW_FULL_2026_03_05_AGENT_JP.md` | VERITAS OS 全コードレビュー（2026-03-05 / Codex Agent） | Mixed | review | `docs/review/CODE_REVIEW_FULL_2026_03_04_AGENT_JP.md` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODE_REVIEW_FULL_2026_03_13_JP.md` | CODE REVIEW FULL 2026-03-13 (JP) | Mixed | review | `docs/review/CODE_REVIEW_2026_02_27_FULL_JP.md` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODE_REVIEW_FULL_2026_03_14_ALL_CODE_CONSISTENCY_JP.md` | 全コード整合性レビュー（2026-03-14） | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODE_REVIEW_FULL_2026_03_14_JP.md` | CODE REVIEW FULL (2026-03-14, JP) | Mixed | review | `docs/review/CODE_REVIEW_2026_02_27_FULL_JP.md` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODE_REVIEW_FULL_2026_03_16_AGENT_JP.md` | VERITAS OS 完成度レビュー（バックエンド + フロントエンド全体） | Mixed | review | `docs/review/CODE_REVIEW_FULL_2026_03_04_AGENT_JP.md` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODE_REVIEW_REPORT.md` | VERITAS OS - Comprehensive Code Review Report | EN | review | `-` | - | keep |
| `docs/review/CODE_REVIEW_REREVIEW_2026_03_18_JP.md` | VERITAS OS 再評価レビュー（2026-03-18） | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/CODE_REVIEW_STATUS.md` | VERITAS OS - Code Review Status Update | Mixed | review | `-` | mixed-language | split |
| `docs/review/ENTERPRISE_READINESS_REVIEW_2026_03_06_JP.md` | Enterprise Readiness Review (2026-03-06) | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/FRONTEND_CODEX_IMPROVEMENT_REREVIEW_2026_02_27_JP.md` | Frontend CODEX 改善再レビュー（2026-02-27, JP） | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/FRONTEND_CODEX_IMPROVEMENT_REVIEW_2026_02_26_JP.md` | Frontend CODEX 改善精密レビュー（2026-02-26, JP） | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/FRONTEND_PRECISION_REVIEW_2026_02_23_JP.md` | Frontend 精密レビュー（2026-02-23） | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/FRONTEND_REVIEW_2026_02_23_FOLLOWUP_JP.md` | Frontend レビュー（フォローアップ, 2026-02-23） | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/README.md` | Review Docs Hub (active) | Mixed | README | `-` | mixed-language | split |
| `docs/review/README_REVIEW_2026_03_02_JP.md` | READMEレビュー（README.md / README_JP.md） | Mixed | README | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/review/SCHEMA_REVIEW_2026_02_23.md` | Schema 形状レビュー（2026-02-23） | Mixed | review | `-` | mixed-language | split |
| `docs/review/SECURITY_AUDIT_2026_03_12.md` | VERITAS OS セキュリティ全監査報告書 | Mixed | security | `-` | mixed-language | split |
| `docs/review/SYSTEM_SCORECARD_2026_03_02.md` | Veritas OS システム総合評価（2026-03-02） | Mixed | review | `-` | mixed-language | split |
| `docs/review/pipeline_py_precision_review_2026-03-11.md` | pipeline.py 精密レビュー（`veritas_os/core/pipeline.py`） | Mixed | review | `-` | mixed-language | split |
| `docs/review-frontend-backend-consistency.md` | フロントエンド・バックエンド整合性レビュー報告書 | Mixed | review | `-` | mixed-language | split |
| `docs/reviews/CODE_REVIEW_2026_03_21_JP.md` | VERITAS OS コードレビュー（2026-03-21） | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/reviews/CODE_REVIEW_CONSISTENCY_2026_03_15_JP.md` | VERITAS OS 整合性保持型コードレビュー (2026-03-15) | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/reviews/CODE_REVIEW_REASSESSMENT_2026_03_23_JP.md` | VERITAS OS 再評価レビュー（2026-03-23） | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/reviews/FRONTEND_BACKEND_CONSISTENCY_REVIEW_2026_03_30_JP.md` | フロントエンド / バックエンド整合性 精密レビュー（2026-03-30） | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/reviews/POLICY_AS_CODE_IMPLEMENTATION_REVIEW_2026-04-02.md` | Policy-as-Code 実装状況レビュー（2026-04-02） | Mixed | review | `-` | mixed-language | split |
| `docs/reviews/README.md` | Reviews Archive Guide | Mixed | README | `-` | mixed-language | split |
| `docs/reviews/THREAT_MODEL_STRIDE_LINDDUN_20260314.md` | VERITAS OS Threat Model（STRIDE / LINDDUN） | Mixed | review | `-` | mixed-language | split |
| `docs/reviews/full_code_review_20260327.md` | 全コードレビュー報告書（2026-03-27） | Mixed | review | `-` | mixed-language | split |
| `docs/reviews/improvement_instructions_ja_20260320.md` | VERITAS OS 今後の改善指示 | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/reviews/precision_code_review_ja_20260319.md` | VERITAS OS 精密コードレビュー | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/reviews/precision_code_review_ja_20260319_reassessment.md` | VERITAS OS 再評価レビュー | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/reviews/system_improvement_review_ja_20260327.md` | VERITAS システム改善レビュー（2026-03-27） | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/reviews/technical_dd_review_ja_20260314.md` | VERITAS OS 技術DD/査読レビュー（2026-03-14） | Mixed | review | `docs/reviews/technical_dd_review_ja_20260315.md` | mixed-language, suffix inconsistency | split, rename |
| `docs/reviews/technical_dd_review_ja_20260315.md` | VERITAS OS 技術DD/査読レビュー 再評価（2026-03-15） | Mixed | review | `docs/reviews/technical_dd_review_ja_20260314.md` | mixed-language, suffix inconsistency | split, rename |
| `docs/security-hardening.md` | Security Hardening Checklist | EN | security | `-` | - | keep |
| `docs/self_healing_loop.md` | Self-Healing Loop (自己修復ループ) | Mixed | other | `-` | mixed-language | split |
| `docs/system_review_2026-03-26.md` | VERITAS OS システムレビュー（2026-03-26） | Mixed | review | `-` | mixed-language | split |
| `docs/ui/PREVIEW_PAGES_JP.md` | UI/UX 各ページのプレビュー手順 | Mixed | review | `-` | mixed-language, suffix inconsistency | split, rename |
| `docs/ui/README_UI.md` | UI Monorepo Quickstart | Mixed | README | `-` | mixed-language | split |
| `docs/ui/architecture.md` | UI Architecture Notes | Mixed | other | `-` | mixed-language | split |
| `docs/ui/integration_plan.md` | UI Integration Plan (Task 1) | Mixed | other | `-` | mixed-language | split |
| `docs/user_guide_eu_ai_act.md` | VERITAS OS — エンドユーザー向け使用説明書 | JA | guide | `-` | - | keep |
| `frontend/FRONTEND_REVIEW.md` | Frontend Review (2026-03-03) | Mixed | review | `-` | mixed-language | split |
| `security/sbom/README.md` | SBOM Baseline | EN | README | `-` | - | keep |
| `spec/continuation_runtime_overview.md` | Continuation Runtime — Conceptual Overview | EN | other | `-` | - | keep |
| `veritas_os/README.md` | VERITAS OS v2.0 — Proto-AGI Decision OS | EN | README | `veritas_os/README_JP.md` | - | keep |
| `veritas_os/README_JP.md` | VERITAS OS v2.0 — Proto-AGI Decision OS（日本語版） | Mixed | README | `veritas_os/README.md` | mixed-language, suffix inconsistency | split, rename |
| `veritas_os/WEEKLY_TASKS.md` | WEEKLY_TASKS | Mixed | other | `-` | mixed-language | split |

## Language Pairing Analysis

- 明示的な日英ペアとして確認しやすいのは `README.md` ↔ `README_JP.md`, `veritas_os/README.md` ↔ `veritas_os/README_JP.md`。
- レビュー群は「同一主題の時系列再レビュー」が多く、**翻訳ペアというより版違い**の可能性が高い。
- `docs/review/README.md` と `docs/reviews/README.md` は役割が近く、将来は統合 index 候補。
- ペア判定が曖昧なものは「候補」扱いとし、本文 diff ベースの確認を推奨。

## Mixed-language Files

- Mixed 判定: **113 ファイル**。
- 主な集中領域: `docs/review/`, `docs/reviews/`, `docs/notes/`, ルートのレビュー文書。
- 方針: mixed 文書は `split`（言語分離）または `primary language 明示 + untranslated sections タグ化`。

## Root Cleanup Candidates

| file | reason | target (proposal) |
|---|---|---|
| `FRONTEND_REVIEW.md` | ルート直下文書の増加を招く | `docs/reviews/` |
| `LARGE_FILE_REVIEW.md` | ルート直下文書の増加を招く | `docs/reviews/` |
| `REPOSITORY_REVIEW.md` | ルート直下文書の増加を招く | `docs/reviews/` |
| `REVIEW_CURRENT_IMPROVEMENTS_2026-03-30.md` | ルート直下文書の増加を招く | `docs/reviews/` |
| `chainlit.md` | ルート直下文書の増加を招く | `docs/notes/` |


## Proposed Directory Structure

```text
docs/
  en/
    reviews/
    audits/
    operations/
    notes/
    guides/
    legal/
    architecture/
  ja/
    reviews/
    audits/
    operations/
    notes/
    guides/
    legal/
    architecture/
  shared/
    assets/
    templates/
  index.md
```
- ルートに残す推奨: `README.md`, `README_JP.md`, `CONTRIBUTING.md`, `SECURITY.md`, （必要なら `chainlit.md`）。
- `docs/review` と `docs/reviews` は統合し、旧パスには移行期間の stub を置く。

## Naming Convention Proposal

- 英語: `kebab-case` + 日付 `YYYY-MM-DD`。例: `code-review-2026-03-30.en.md`
- 日本語: 同一 basename + `.ja.md`。例: `code-review-2026-03-30.ja.md`
- README 系: `README.md`（英）, `README.ja.md`（日）を各ディレクトリで統一。
- index 系: 各階層に `index.md` を配置。
- 互換例外: 外部参照が多い `README_JP.md` は当面維持し、`README.ja.md` へ段階移行。

## Safe Migration Plan

1. **Inventory freeze**: 本監査表を基準に対象確定。
2. **Index first**: 先に `docs/index.md` と各カテゴリ index を追加。
3. **Directory unification**: `docs/review` / `docs/reviews` を片系へ統合（推奨: `docs/ja/reviews`）。
4. **Language split**: Mixed 文書を優先度順で分離。未翻訳セクションは `> TODO(translation)` 明示。
5. **Redirect stubs**: 旧パスに短い移転案内を置き、リンク切れを防止。
6. **Link validation**: CIで markdown link checker を実行。
7. **Git history strategy**: rename/move を単独コミット化し、内容変更コミットと分離。
8. **Cutover**: README 導線更新、旧命名の deprecation window を明示。

## High-priority Quick Wins

- `docs/review` と `docs/reviews` の役割定義を 1 ページで明文化。
- ルートのレビュー4件を `docs/reviews/legacy-root/` へ移動する計画を確定（実施は次フェーズ）。
- `README.md` / `README_JP.md` に Documentation Map へのリンク追加。
- Mixed 比率の高い文書から 5 本をパイロット分離。

## Open Questions / Ambiguities

- `chainlit.md` をプロダクト文書として保持するか、開発補助文書として `docs/operations` に寄せるか。
- `docs/eu_ai_act/*` を legal 配下に集約するか、compliance 専用トップレベルを作るか。
- `docs/notes/*` の一部（実質 review）を reviews に再分類する基準。
- `frontend/FRONTEND_REVIEW.md` を frontend サブプロジェクト専用文書として維持するか。

## Final Recommendation

- Enterprise/governance 運用の観点から、**言語軸（en/ja）× 文書種別軸**への二次元再編が最も監査性・保守性に優れます。
- 次フェーズでは「移動のみコミット」→「リンク修正コミット」→「内容正規化コミット」の3段階で実行し、監査証跡を明確化してください。
- 重複判定は断定せず、本文差分レビュー（semantic diff）で候補確定する運用を推奨します。

## この後そのまま実行版へ渡せるアクション一覧

- [ ] `docs/index.md` の新設（全体マップ）
- [ ] `docs/review` / `docs/reviews` 統合方針を決定
- [ ] ルートレビュー文書の移動対象を凍結
- [ ] 命名規則（`.en.md` / `.ja.md`）の採択可否を決定
- [ ] Mixed文書の分離優先順位トップ10を決定
- [ ] CIにリンクチェックを追加