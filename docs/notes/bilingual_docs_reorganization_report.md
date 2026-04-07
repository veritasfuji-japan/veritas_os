# Bilingual Markdown Reorganization Report

Date: 2026-04-07

## 発見した問題の要約
- ルート直下にレビュー文書が散在。
- `docs/review` と `docs/reviews` の二重運用。
- 命名規則（大文字/小文字、JP/ja、日付区切り）が混在。
- Mixed-language 文書が多数。

## ファイル棚卸し一覧
- 完全な棚卸しは `docs/ja/audits/markdown_information_architecture_audit_2026_04_07_ja.md` の Full Markdown Inventory を正本とする。
- 本実施後の現行一覧（path / language / type）:

| path | language | type |
|---|---|---|
| `CONTRIBUTING.md` | EN | other |
| `README.md` | EN | README |
| `README_JP.md` | JA | README |
| `SECURITY.md` | EN | other |
| `docs/COVERAGE_AFTER_TEST_HARDENING.md` | Mixed | other |
| `docs/COVERAGE_REPORT.md` | Mixed | other |
| `docs/DOCUMENTATION_MAP.md` | Mixed | other |
| `docs/PRODUCTION_VALIDATION.md` | EN | other |
| `docs/RUNTIME_DATA_POLICY.md` | Mixed | other |
| `docs/VERITAS_FULL_USER_MANUAL_JP.md` | Mixed | other |
| `docs/architecture/continuation_runtime_adr.md` | EN | other |
| `docs/architecture/continuation_runtime_architecture_note.md` | EN | note |
| `docs/architecture/continuation_runtime_glossary.md` | EN | other |
| `docs/architecture/continuation_runtime_rollout.md` | EN | other |
| `docs/architecture/core_responsibility_boundaries.md` | EN | other |
| `docs/benchmarks/VERITAS_EVIDENCE_BENCHMARK_PLAN.md` | Mixed | other |
| `docs/demo-3min-script.md` | EN | other |
| `docs/dependency-profiles.md` | EN | other |
| `docs/en/README.md` | EN | README |
| `docs/en/notes/chainlit.md` | EN | note |
| `docs/en/operations/memory_pickle_migration.md` | EN | runbook |
| `docs/en/reviews/README.md` | EN | README |
| `docs/en/reviews/code_review_2025.md` | EN | review |
| `docs/en/reviews/code_review_report.md` | EN | review |
| `docs/en/reviews/frontend_review.md` | EN | review |
| `docs/en/reviews/repository_review.md` | EN | review |
| `docs/env-reference.md` | EN | other |
| `docs/eu_ai_act/bias_assessment_report.md` | Mixed | other |
| `docs/eu_ai_act/continuous_risk_monitoring.md` | Mixed | other |
| `docs/eu_ai_act/intended_purpose.md` | Mixed | other |
| `docs/eu_ai_act/model_card_gpt41_mini.md` | Mixed | other |
| `docs/eu_ai_act/performance_metrics.md` | Mixed | other |
| `docs/eu_ai_act/risk_assessment.md` | Mixed | other |
| `docs/eu_ai_act/risk_classification_matrix.md` | Mixed | other |
| `docs/eu_ai_act/technical_documentation.md` | Mixed | other |
| `docs/eu_ai_act/third_party_model_dpa_checklist.md` | Mixed | other |
| `docs/eu_ai_act_compliance_review.md` | Mixed | review |
| `docs/fuji_error_codes.md` | Mixed | other |
| `docs/fuji_eu_enterprise_strict_usage.md` | Mixed | other |
| `docs/ja/README.md` | JA | README |
| `docs/ja/audits/markdown_information_architecture_audit_2026_04_07_ja.md` | JA | audit |
| `docs/ja/audits/replay_audit_ja.md` | JA | audit |
| `docs/ja/operations/enterprise_slo_sli_runbook_ja.md` | JA | runbook |
| `docs/ja/reviews/README.md` | JA | README |
| `docs/ja/reviews/backend_core_precision_rereview_2026_03_02_ja.md` | JA | review |
| `docs/ja/reviews/backend_core_precision_review_2026_03_02_ja.md` | JA | review |
| `docs/ja/reviews/code_improvement_summary_ja.md` | JA | review |
| `docs/ja/reviews/code_review_2026_02_10_ja.md` | JA | review |
| `docs/ja/reviews/code_review_2026_02_11_ja.md` | JA | review |
| `docs/ja/reviews/code_review_2026_02_11_runtime_check_ja.md` | JA | review |
| `docs/ja/reviews/code_review_2026_02_12_agent_ja.md` | JA | review |
| `docs/ja/reviews/code_review_2026_02_12_ja.md` | JA | review |
| `docs/ja/reviews/code_review_2026_02_13_agent_detailed_ja.md` | JA | review |
| `docs/ja/reviews/code_review_2026_02_13_core_ja.md` | JA | review |
| `docs/ja/reviews/code_review_2026_02_13_full_scan_ja.md` | JA | review |
| `docs/ja/reviews/code_review_2026_02_14_spaghetti_ja.md` | JA | review |
| `docs/ja/reviews/code_review_2026_02_15_agent_ja.md` | JA | review |
| `docs/ja/reviews/code_review_2026_02_16_completeness_ja.md` | JA | review |
| `docs/ja/reviews/code_review_2026_02_27_full_ja.md` | JA | review |
| `docs/ja/reviews/code_review_2026_03_06_must_have_features_ja.md` | JA | review |
| `docs/ja/reviews/code_review_2026_03_21_ja.md` | JA | review |
| `docs/ja/reviews/code_review_2026_03_23_ja.md` | JA | review |
| `docs/ja/reviews/code_review_2026_03_24_ja.md` | JA | review |
| `docs/ja/reviews/code_review_consistency_2026_03_15_ja.md` | JA | review |
| `docs/ja/reviews/code_review_fatal_bug_scan_2026_03_02_ja.md` | JA | review |
| `docs/ja/reviews/code_review_full_2026_02_08_ja.md` | JA | review |
| `docs/ja/reviews/code_review_full_2026_03_04_agent_ja.md` | JA | review |
| `docs/ja/reviews/code_review_full_2026_03_04_ja.md` | JA | review |
| `docs/ja/reviews/code_review_full_2026_03_05_agent2_ja.md` | JA | review |
| `docs/ja/reviews/code_review_full_2026_03_05_agent_ja.md` | JA | review |
| `docs/ja/reviews/code_review_full_2026_03_13_ja.md` | JA | review |
| `docs/ja/reviews/code_review_full_2026_03_14_all_code_consistency_ja.md` | JA | review |
| `docs/ja/reviews/code_review_full_2026_03_14_ja.md` | JA | review |
| `docs/ja/reviews/code_review_full_2026_03_16_agent_ja.md` | JA | review |
| `docs/ja/reviews/code_review_full_ja.md` | JA | review |
| `docs/ja/reviews/code_review_reassessment_2026_03_23_ja.md` | JA | review |
| `docs/ja/reviews/code_review_rereview_2026_03_18_ja.md` | JA | review |
| `docs/ja/reviews/code_review_status_ja.md` | JA | review |
| `docs/ja/reviews/codex_improvement_review_2026_02_24_ja.md` | JA | review |
| `docs/ja/reviews/codex_improvement_review_2026_02_25_ja.md` | JA | review |
| `docs/ja/reviews/codex_improvement_review_2026_02_26_ja.md` | JA | review |
| `docs/ja/reviews/codex_start_here_ja.md` | JA | review |
| `docs/ja/reviews/enterprise_readiness_review_2026_03_06_ja.md` | JA | review |
| `docs/ja/reviews/frontend_backend_consistency_review_2026_03_30_ja.md` | JA | review |
| `docs/ja/reviews/frontend_codex_improvement_rereview_2026_02_27_ja.md` | JA | review |
| `docs/ja/reviews/frontend_codex_improvement_review_2026_02_26_ja.md` | JA | review |
| `docs/ja/reviews/frontend_precision_review_2026_02_23_ja.md` | JA | review |
| `docs/ja/reviews/frontend_review_2026_02_23_followup_ja.md` | JA | review |
| `docs/ja/reviews/frontend_review_ja.md` | JA | review |
| `docs/ja/reviews/full_code_review_20260327_ja.md` | JA | review |
| `docs/ja/reviews/improvement_instructions_ja_20260320.md` | JA | review |
| `docs/ja/reviews/large_file_review_ja.md` | JA | review |
| `docs/ja/reviews/pipeline_py_precision_review_2026_03_11_ja.md` | JA | review |
| `docs/ja/reviews/policy_as_code_implementation_review_2026_04_02_ja.md` | JA | review |
| `docs/ja/reviews/precision_code_review_ja_20260319.md` | JA | review |
| `docs/ja/reviews/precision_code_review_ja_20260319_reassessment.md` | JA | review |
| `docs/ja/reviews/readme_ja.md` | JA | README |
| `docs/ja/reviews/readme_ja_2.md` | JA | README |
| `docs/ja/reviews/readme_review_2026_03_02_ja.md` | JA | README |
| `docs/ja/reviews/review_current_improvements_2026_03_30_ja.md` | JA | review |
| `docs/ja/reviews/review_frontend_backend_consistency_ja.md` | JA | review |
| `docs/ja/reviews/schema_review_2026_02_23_ja.md` | JA | review |
| `docs/ja/reviews/security_audit_2026_03_12_ja.md` | JA | audit |
| `docs/ja/reviews/system_improvement_review_ja_20260327.md` | JA | review |
| `docs/ja/reviews/system_review_2026_03_26_ja.md` | JA | review |
| `docs/ja/reviews/system_scorecard_2026_03_02_ja.md` | JA | review |
| `docs/ja/reviews/technical_dd_review_ja_20260314.md` | JA | review |
| `docs/ja/reviews/technical_dd_review_ja_20260315.md` | JA | review |
| `docs/ja/reviews/threat_model_stride_linddun_20260314_ja.md` | JA | review |
| `docs/notes/AGI_BENCH_INTEGRATION_GUIDE.md` | Mixed | note |
| `docs/notes/AGI_progress_stages.md` | EN | note |
| `docs/notes/BENCHMARK_MIGRATION_GUIDE.md` | Mixed | note |
| `docs/notes/CODE_REVIEW_DOCUMENT_MAP.md` | Mixed | review |
| `docs/notes/CODE_REVIEW_REPORT_20260204.md` | Mixed | review |
| `docs/notes/CORE_COVERAGE_SNAPSHOT_JP.md` | Mixed | note |
| `docs/notes/CRITIQUE_DEBATE_REVIEW.md` | Mixed | review |
| `docs/notes/CRITIQUE_INTEGRATION_GUIDE.md` | Mixed | note |
| `docs/notes/DEBATE_CHANGES_DIFF.md` | Mixed | note |
| `docs/notes/DEBATE_IMPROVEMENT_REPORT.md` | Mixed | note |
| `docs/notes/DEPLOYMENT_COMPLETE.md` | Mixed | note |
| `docs/notes/MEMORY_IMPROVEMENT_REPORT.md` | Mixed | note |
| `docs/notes/PAPER_REVIEW_V1.md` | Mixed | review |
| `docs/notes/TRUSTLOG_VERIFICATION_REPORT.md` | Mixed | note |
| `docs/notes/VERITAS_CODE_REVIEW_PRINCIPLES.md` | Mixed | review |
| `docs/notes/VERITAS_EVALUATION_REPORT.md` | Mixed | note |
| `docs/notes/VERITAS_IMPROVEMENT_SUMMARY.md` | Mixed | note |
| `docs/notes/VERITAS_REPORT.md` | Mixed | note |
| `docs/notes/WORLD_MIGRATION_GUIDE.md` | Mixed | note |
| `docs/notes/code_review_20260205.md` | Mixed | review |
| `docs/policy_as_code.md` | Mixed | other |
| `docs/security-hardening.md` | EN | other |
| `docs/self_healing_loop.md` | Mixed | other |
| `docs/ui/PREVIEW_PAGES_JP.md` | Mixed | review |
| `docs/ui/README_UI.md` | Mixed | README |
| `docs/ui/architecture.md` | Mixed | other |
| `docs/ui/integration_plan.md` | Mixed | other |
| `docs/user_guide_eu_ai_act.md` | Mixed | other |
| `node_modules/.pnpm/@adobe+css-tools@4.4.4/node_modules/@adobe/css-tools/README.md` | EN | README |
| `node_modules/.pnpm/@adobe+css-tools@4.4.4/node_modules/@adobe/css-tools/docs/API.md` | EN | other |
| `node_modules/.pnpm/@adobe+css-tools@4.4.4/node_modules/@adobe/css-tools/docs/AST.md` | EN | other |
| `node_modules/.pnpm/@adobe+css-tools@4.4.4/node_modules/@adobe/css-tools/docs/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/@adobe+css-tools@4.4.4/node_modules/@adobe/css-tools/docs/EXAMPLES.md` | EN | other |
| `node_modules/.pnpm/@alloc+quick-lru@5.2.0/node_modules/@alloc/quick-lru/readme.md` | EN | README |
| `node_modules/.pnpm/@ampproject+remapping@2.3.0/node_modules/@ampproject/remapping/README.md` | EN | README |
| `node_modules/.pnpm/@asamuzakjp+css-color@3.2.0/node_modules/@asamuzakjp/css-color/README.md` | EN | README |
| `node_modules/.pnpm/@axe-core+playwright@4.11.1_playwright-core@1.58.2/node_modules/@axe-core/playwright/README.md` | EN | README |
| `node_modules/.pnpm/@babel+code-frame@7.29.0/node_modules/@babel/code-frame/README.md` | EN | README |
| `node_modules/.pnpm/@babel+compat-data@7.29.0/node_modules/@babel/compat-data/README.md` | EN | README |
| `node_modules/.pnpm/@babel+core@7.29.0/node_modules/@babel/core/README.md` | EN | README |
| `node_modules/.pnpm/@babel+generator@7.29.1/node_modules/@babel/generator/README.md` | EN | README |
| `node_modules/.pnpm/@babel+helper-compilation-targets@7.28.6/node_modules/@babel/helper-compilation-targets/README.md` | EN | README |
| `node_modules/.pnpm/@babel+helper-globals@7.28.0/node_modules/@babel/helper-globals/README.md` | EN | README |
| `node_modules/.pnpm/@babel+helper-module-imports@7.28.6/node_modules/@babel/helper-module-imports/README.md` | EN | README |
| `node_modules/.pnpm/@babel+helper-module-transforms@7.28.6_@babel+core@7.29.0/node_modules/@babel/helper-module-transforms/README.md` | EN | README |
| `node_modules/.pnpm/@babel+helper-plugin-utils@7.28.6/node_modules/@babel/helper-plugin-utils/README.md` | EN | README |
| `node_modules/.pnpm/@babel+helper-string-parser@7.27.1/node_modules/@babel/helper-string-parser/README.md` | EN | README |
| `node_modules/.pnpm/@babel+helper-validator-identifier@7.28.5/node_modules/@babel/helper-validator-identifier/README.md` | EN | README |
| `node_modules/.pnpm/@babel+helper-validator-option@7.27.1/node_modules/@babel/helper-validator-option/README.md` | EN | README |
| `node_modules/.pnpm/@babel+helpers@7.28.6/node_modules/@babel/helpers/README.md` | EN | README |
| `node_modules/.pnpm/@babel+parser@7.29.0/node_modules/@babel/parser/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/@babel+parser@7.29.0/node_modules/@babel/parser/README.md` | EN | README |
| `node_modules/.pnpm/@babel+plugin-transform-react-jsx-self@7.27.1_@babel+core@7.29.0/node_modules/@babel/plugin-transform-react-jsx-self/README.md` | EN | README |
| `node_modules/.pnpm/@babel+plugin-transform-react-jsx-source@7.27.1_@babel+core@7.29.0/node_modules/@babel/plugin-transform-react-jsx-source/README.md` | EN | README |
| `node_modules/.pnpm/@babel+runtime@7.28.6/node_modules/@babel/runtime/README.md` | EN | README |
| `node_modules/.pnpm/@babel+runtime@7.29.2/node_modules/@babel/runtime/README.md` | EN | README |
| `node_modules/.pnpm/@babel+template@7.28.6/node_modules/@babel/template/README.md` | EN | README |
| `node_modules/.pnpm/@babel+traverse@7.29.0/node_modules/@babel/traverse/README.md` | EN | README |
| `node_modules/.pnpm/@babel+types@7.29.0/node_modules/@babel/types/README.md` | EN | README |
| `node_modules/.pnpm/@bcoe+v8-coverage@0.2.3/node_modules/@bcoe/v8-coverage/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/@bcoe+v8-coverage@0.2.3/node_modules/@bcoe/v8-coverage/LICENSE.md` | EN | other |
| `node_modules/.pnpm/@bcoe+v8-coverage@0.2.3/node_modules/@bcoe/v8-coverage/README.md` | EN | README |
| `node_modules/.pnpm/@bcoe+v8-coverage@0.2.3/node_modules/@bcoe/v8-coverage/dist/lib/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/@bcoe+v8-coverage@0.2.3/node_modules/@bcoe/v8-coverage/dist/lib/LICENSE.md` | EN | other |
| `node_modules/.pnpm/@bcoe+v8-coverage@0.2.3/node_modules/@bcoe/v8-coverage/dist/lib/README.md` | EN | README |
| `node_modules/.pnpm/@csstools+color-helpers@5.1.0/node_modules/@csstools/color-helpers/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/@csstools+color-helpers@5.1.0/node_modules/@csstools/color-helpers/LICENSE.md` | EN | other |
| `node_modules/.pnpm/@csstools+color-helpers@5.1.0/node_modules/@csstools/color-helpers/README.md` | EN | README |
| `node_modules/.pnpm/@csstools+css-calc@2.1.4_@csstools+css-parser-algorithms@3.0.5_@csstools+css-tokenizer@3.0.4__w6bxvhxcuwf7wuvvqqujerjqsm/node_modules/@csstools/css-calc/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/@csstools+css-calc@2.1.4_@csstools+css-parser-algorithms@3.0.5_@csstools+css-tokenizer@3.0.4__w6bxvhxcuwf7wuvvqqujerjqsm/node_modules/@csstools/css-calc/LICENSE.md` | EN | other |
| `node_modules/.pnpm/@csstools+css-calc@2.1.4_@csstools+css-parser-algorithms@3.0.5_@csstools+css-tokenizer@3.0.4__w6bxvhxcuwf7wuvvqqujerjqsm/node_modules/@csstools/css-calc/README.md` | EN | README |
| `node_modules/.pnpm/@csstools+css-color-parser@3.1.0_@csstools+css-parser-algorithms@3.0.5_@csstools+css-tokenize_hhnv33zvdizn2g25owm5qvkubq/node_modules/@csstools/css-color-parser/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/@csstools+css-color-parser@3.1.0_@csstools+css-parser-algorithms@3.0.5_@csstools+css-tokenize_hhnv33zvdizn2g25owm5qvkubq/node_modules/@csstools/css-color-parser/LICENSE.md` | EN | other |
| `node_modules/.pnpm/@csstools+css-color-parser@3.1.0_@csstools+css-parser-algorithms@3.0.5_@csstools+css-tokenize_hhnv33zvdizn2g25owm5qvkubq/node_modules/@csstools/css-color-parser/README.md` | EN | README |
| `node_modules/.pnpm/@csstools+css-parser-algorithms@3.0.5_@csstools+css-tokenizer@3.0.4/node_modules/@csstools/css-parser-algorithms/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/@csstools+css-parser-algorithms@3.0.5_@csstools+css-tokenizer@3.0.4/node_modules/@csstools/css-parser-algorithms/LICENSE.md` | EN | other |
| `node_modules/.pnpm/@csstools+css-parser-algorithms@3.0.5_@csstools+css-tokenizer@3.0.4/node_modules/@csstools/css-parser-algorithms/README.md` | EN | README |
| `node_modules/.pnpm/@csstools+css-tokenizer@3.0.4/node_modules/@csstools/css-tokenizer/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/@csstools+css-tokenizer@3.0.4/node_modules/@csstools/css-tokenizer/LICENSE.md` | EN | other |
| `node_modules/.pnpm/@csstools+css-tokenizer@3.0.4/node_modules/@csstools/css-tokenizer/README.md` | EN | README |
| `node_modules/.pnpm/@esbuild+linux-x64@0.21.5/node_modules/@esbuild/linux-x64/README.md` | EN | README |
| `node_modules/.pnpm/@eslint+eslintrc@2.1.4/node_modules/@eslint/eslintrc/README.md` | EN | README |
| `node_modules/.pnpm/@eslint+js@8.57.1/node_modules/@eslint/js/README.md` | EN | README |
| `node_modules/.pnpm/@eslint-community+eslint-utils@4.9.1_eslint@8.57.1/node_modules/@eslint-community/eslint-utils/README.md` | EN | README |
| `node_modules/.pnpm/@eslint-community+regexpp@4.12.2/node_modules/@eslint-community/regexpp/README.md` | EN | README |
| `node_modules/.pnpm/@humanwhocodes+config-array@0.13.0/node_modules/@humanwhocodes/config-array/README.md` | EN | README |
| `node_modules/.pnpm/@humanwhocodes+module-importer@1.0.1/node_modules/@humanwhocodes/module-importer/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/@humanwhocodes+module-importer@1.0.1/node_modules/@humanwhocodes/module-importer/README.md` | EN | README |
| `node_modules/.pnpm/@humanwhocodes+object-schema@2.0.3/node_modules/@humanwhocodes/object-schema/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/@humanwhocodes+object-schema@2.0.3/node_modules/@humanwhocodes/object-schema/README.md` | EN | README |
| `node_modules/.pnpm/@img+colour@1.1.0/node_modules/@img/colour/LICENSE.md` | EN | other |
| `node_modules/.pnpm/@img+colour@1.1.0/node_modules/@img/colour/README.md` | EN | README |
| `node_modules/.pnpm/@img+sharp-libvips-linux-x64@1.2.4/node_modules/@img/sharp-libvips-linux-x64/README.md` | EN | README |
| `node_modules/.pnpm/@img+sharp-libvips-linuxmusl-x64@1.2.4/node_modules/@img/sharp-libvips-linuxmusl-x64/README.md` | EN | README |
| `node_modules/.pnpm/@img+sharp-linux-x64@0.34.5/node_modules/@img/sharp-linux-x64/README.md` | EN | README |
| `node_modules/.pnpm/@img+sharp-linuxmusl-x64@0.34.5/node_modules/@img/sharp-linuxmusl-x64/README.md` | EN | README |
| `node_modules/.pnpm/@isaacs+cliui@8.0.2/node_modules/@isaacs/cliui/README.md` | EN | README |
| `node_modules/.pnpm/@istanbuljs+schema@0.1.3/node_modules/@istanbuljs/schema/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/@istanbuljs+schema@0.1.3/node_modules/@istanbuljs/schema/README.md` | EN | README |
| `node_modules/.pnpm/@jridgewell+gen-mapping@0.3.13/node_modules/@jridgewell/gen-mapping/README.md` | EN | README |
| `node_modules/.pnpm/@jridgewell+remapping@2.3.5/node_modules/@jridgewell/remapping/README.md` | EN | README |
| `node_modules/.pnpm/@jridgewell+resolve-uri@3.1.2/node_modules/@jridgewell/resolve-uri/README.md` | EN | README |
| `node_modules/.pnpm/@jridgewell+sourcemap-codec@1.5.5/node_modules/@jridgewell/sourcemap-codec/README.md` | EN | README |
| `node_modules/.pnpm/@jridgewell+trace-mapping@0.3.31/node_modules/@jridgewell/trace-mapping/README.md` | EN | README |
| `node_modules/.pnpm/@next+env@16.1.7/node_modules/@next/env/README.md` | EN | README |
| `node_modules/.pnpm/@next+eslint-plugin-next@15.5.10/node_modules/@next/eslint-plugin-next/README.md` | EN | README |
| `node_modules/.pnpm/@next+swc-linux-x64-gnu@16.1.7/node_modules/@next/swc-linux-x64-gnu/README.md` | EN | README |
| `node_modules/.pnpm/@next+swc-linux-x64-musl@16.1.7/node_modules/@next/swc-linux-x64-musl/README.md` | EN | README |
| `node_modules/.pnpm/@nodelib+fs.scandir@2.1.5/node_modules/@nodelib/fs.scandir/README.md` | EN | README |
| `node_modules/.pnpm/@nodelib+fs.stat@2.0.5/node_modules/@nodelib/fs.stat/README.md` | EN | README |
| `node_modules/.pnpm/@nodelib+fs.walk@1.2.8/node_modules/@nodelib/fs.walk/README.md` | EN | README |
| `node_modules/.pnpm/@pkgjs+parseargs@0.11.0/node_modules/@pkgjs/parseargs/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/@pkgjs+parseargs@0.11.0/node_modules/@pkgjs/parseargs/README.md` | EN | README |
| `node_modules/.pnpm/@playwright+test@1.58.2/node_modules/@playwright/test/README.md` | EN | README |
| `node_modules/.pnpm/@rolldown+pluginutils@1.0.0-rc.3/node_modules/@rolldown/pluginutils/README.md` | EN | README |
| `node_modules/.pnpm/@rollup+rollup-linux-x64-gnu@4.57.1/node_modules/@rollup/rollup-linux-x64-gnu/README.md` | EN | README |
| `node_modules/.pnpm/@rollup+rollup-linux-x64-musl@4.57.1/node_modules/@rollup/rollup-linux-x64-musl/README.md` | EN | README |
| `node_modules/.pnpm/@rtsao+scc@1.1.0/node_modules/@rtsao/scc/README.md` | EN | README |
| `node_modules/.pnpm/@rushstack+eslint-patch@1.15.0/node_modules/@rushstack/eslint-patch/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/@rushstack+eslint-patch@1.15.0/node_modules/@rushstack/eslint-patch/README.md` | EN | README |
| `node_modules/.pnpm/@testing-library+dom@10.4.1/node_modules/@testing-library/dom/README.md` | EN | README |
| `node_modules/.pnpm/@testing-library+jest-dom@6.9.1/node_modules/@testing-library/jest-dom/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/@testing-library+jest-dom@6.9.1/node_modules/@testing-library/jest-dom/README.md` | EN | README |
| `node_modules/.pnpm/@testing-library+react@16.3.2_@testing-library+dom@10.4.1_@types+react-dom@18.3.7_@types+reac_spm2j6wuon27jfezwgjvqbbvgm/node_modules/@testing-library/react/README.md` | EN | README |
| `node_modules/.pnpm/@types+aria-query@5.0.4/node_modules/@types/aria-query/README.md` | EN | README |
| `node_modules/.pnpm/@types+babel__core@7.20.5/node_modules/@types/babel__core/README.md` | EN | README |
| `node_modules/.pnpm/@types+babel__generator@7.27.0/node_modules/@types/babel__generator/README.md` | EN | README |
| `node_modules/.pnpm/@types+babel__template@7.4.4/node_modules/@types/babel__template/README.md` | EN | README |
| `node_modules/.pnpm/@types+babel__traverse@7.28.0/node_modules/@types/babel__traverse/README.md` | EN | README |
| `node_modules/.pnpm/@types+estree@1.0.8/node_modules/@types/estree/README.md` | EN | README |
| `node_modules/.pnpm/@types+json5@0.0.29/node_modules/@types/json5/README.md` | EN | README |
| `node_modules/.pnpm/@types+node@22.19.11/node_modules/@types/node/README.md` | EN | README |
| `node_modules/.pnpm/@types+prop-types@15.7.15/node_modules/@types/prop-types/README.md` | EN | README |
| `node_modules/.pnpm/@types+react-dom@18.3.7_@types+react@18.3.28/node_modules/@types/react-dom/README.md` | EN | README |
| `node_modules/.pnpm/@types+react@18.3.28/node_modules/@types/react/README.md` | EN | README |
| `node_modules/.pnpm/@typescript-eslint+eslint-plugin@8.55.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typesc_rr3iah4h5bhmuw7vmv2hwgbamm/node_modules/@typescript-eslint/eslint-plugin/README.md` | EN | README |
| `node_modules/.pnpm/@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3/node_modules/@typescript-eslint/parser/README.md` | EN | README |
| `node_modules/.pnpm/@typescript-eslint+project-service@8.55.0_typescript@5.9.3/node_modules/@typescript-eslint/project-service/README.md` | EN | README |
| `node_modules/.pnpm/@typescript-eslint+scope-manager@8.55.0/node_modules/@typescript-eslint/scope-manager/README.md` | EN | README |
| `node_modules/.pnpm/@typescript-eslint+tsconfig-utils@8.55.0_typescript@5.9.3/node_modules/@typescript-eslint/tsconfig-utils/README.md` | EN | README |
| `node_modules/.pnpm/@typescript-eslint+type-utils@8.55.0_eslint@8.57.1_typescript@5.9.3/node_modules/@typescript-eslint/type-utils/README.md` | EN | README |
| `node_modules/.pnpm/@typescript-eslint+types@8.55.0/node_modules/@typescript-eslint/types/README.md` | EN | README |
| `node_modules/.pnpm/@typescript-eslint+typescript-estree@8.55.0_typescript@5.9.3/node_modules/@typescript-eslint/typescript-estree/README.md` | EN | README |
| `node_modules/.pnpm/@typescript-eslint+utils@8.55.0_eslint@8.57.1_typescript@5.9.3/node_modules/@typescript-eslint/utils/README.md` | EN | README |
| `node_modules/.pnpm/@typescript-eslint+visitor-keys@8.55.0/node_modules/@typescript-eslint/visitor-keys/README.md` | EN | README |
| `node_modules/.pnpm/@ungap+structured-clone@1.3.0/node_modules/@ungap/structured-clone/README.md` | EN | README |
| `node_modules/.pnpm/@unrs+resolver-binding-linux-x64-gnu@1.11.1/node_modules/@unrs/resolver-binding-linux-x64-gnu/README.md` | EN | README |
| `node_modules/.pnpm/@unrs+resolver-binding-linux-x64-musl@1.11.1/node_modules/@unrs/resolver-binding-linux-x64-musl/README.md` | EN | README |
| `node_modules/.pnpm/@vitejs+plugin-react@5.1.4_vite@5.4.21_@types+node@22.19.11_/node_modules/@vitejs/plugin-react/README.md` | EN | README |
| `node_modules/.pnpm/@vitest+expect@2.1.9/node_modules/@vitest/expect/README.md` | EN | README |
| `node_modules/.pnpm/@vitest+mocker@2.1.9_vite@5.4.21_@types+node@22.19.11_/node_modules/@vitest/mocker/README.md` | EN | README |
| `node_modules/.pnpm/@vitest+runner@2.1.9/node_modules/@vitest/runner/README.md` | EN | README |
| `node_modules/.pnpm/@vitest+snapshot@2.1.9/node_modules/@vitest/snapshot/README.md` | EN | README |
| `node_modules/.pnpm/@vitest+spy@2.1.9/node_modules/@vitest/spy/README.md` | EN | README |
| `node_modules/.pnpm/acorn-jsx@5.3.2_acorn@8.15.0/node_modules/acorn-jsx/README.md` | EN | README |
| `node_modules/.pnpm/acorn@8.15.0/node_modules/acorn/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/acorn@8.15.0/node_modules/acorn/README.md` | EN | README |
| `node_modules/.pnpm/agent-base@7.1.4/node_modules/agent-base/README.md` | EN | README |
| `node_modules/.pnpm/ajv@6.12.6/node_modules/ajv/README.md` | EN | README |
| `node_modules/.pnpm/ajv@6.12.6/node_modules/ajv/lib/dotjs/README.md` | EN | README |
| `node_modules/.pnpm/ansi-regex@5.0.1/node_modules/ansi-regex/readme.md` | EN | README |
| `node_modules/.pnpm/ansi-regex@6.2.2/node_modules/ansi-regex/readme.md` | EN | README |
| `node_modules/.pnpm/ansi-styles@4.3.0/node_modules/ansi-styles/readme.md` | EN | README |
| `node_modules/.pnpm/ansi-styles@5.2.0/node_modules/ansi-styles/readme.md` | EN | README |
| `node_modules/.pnpm/ansi-styles@6.2.3/node_modules/ansi-styles/readme.md` | EN | README |
| `node_modules/.pnpm/any-promise@1.3.0/node_modules/any-promise/README.md` | EN | README |
| `node_modules/.pnpm/anymatch@3.1.3/node_modules/anymatch/README.md` | EN | README |
| `node_modules/.pnpm/arg@5.0.2/node_modules/arg/LICENSE.md` | EN | other |
| `node_modules/.pnpm/arg@5.0.2/node_modules/arg/README.md` | EN | README |
| `node_modules/.pnpm/argparse@2.0.1/node_modules/argparse/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/argparse@2.0.1/node_modules/argparse/README.md` | EN | README |
| `node_modules/.pnpm/aria-query@5.3.0/node_modules/aria-query/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/aria-query@5.3.0/node_modules/aria-query/README.md` | EN | README |
| `node_modules/.pnpm/aria-query@5.3.2/node_modules/aria-query/README.md` | EN | README |
| `node_modules/.pnpm/array-buffer-byte-length@1.0.2/node_modules/array-buffer-byte-length/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/array-buffer-byte-length@1.0.2/node_modules/array-buffer-byte-length/README.md` | EN | README |
| `node_modules/.pnpm/array-includes@3.1.9/node_modules/array-includes/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/array-includes@3.1.9/node_modules/array-includes/README.md` | EN | README |
| `node_modules/.pnpm/array.prototype.findlast@1.2.5/node_modules/array.prototype.findlast/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/array.prototype.findlast@1.2.5/node_modules/array.prototype.findlast/README.md` | EN | README |
| `node_modules/.pnpm/array.prototype.findlastindex@1.2.6/node_modules/array.prototype.findlastindex/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/array.prototype.findlastindex@1.2.6/node_modules/array.prototype.findlastindex/README.md` | EN | README |
| `node_modules/.pnpm/array.prototype.flat@1.3.3/node_modules/array.prototype.flat/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/array.prototype.flat@1.3.3/node_modules/array.prototype.flat/README.md` | EN | README |
| `node_modules/.pnpm/array.prototype.flatmap@1.3.3/node_modules/array.prototype.flatmap/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/array.prototype.flatmap@1.3.3/node_modules/array.prototype.flatmap/README.md` | EN | README |
| `node_modules/.pnpm/array.prototype.tosorted@1.1.4/node_modules/array.prototype.tosorted/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/array.prototype.tosorted@1.1.4/node_modules/array.prototype.tosorted/README.md` | EN | README |
| `node_modules/.pnpm/arraybuffer.prototype.slice@1.0.4/node_modules/arraybuffer.prototype.slice/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/arraybuffer.prototype.slice@1.0.4/node_modules/arraybuffer.prototype.slice/README.md` | EN | README |
| `node_modules/.pnpm/assertion-error@2.0.1/node_modules/assertion-error/README.md` | EN | README |
| `node_modules/.pnpm/ast-types-flow@0.0.8/node_modules/ast-types-flow/README.md` | EN | README |
| `node_modules/.pnpm/async-function@1.0.0/node_modules/async-function/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/async-function@1.0.0/node_modules/async-function/README.md` | EN | README |
| `node_modules/.pnpm/asynckit@0.4.0/node_modules/asynckit/README.md` | EN | README |
| `node_modules/.pnpm/autoprefixer@10.4.24_postcss@8.5.6/node_modules/autoprefixer/README.md` | EN | README |
| `node_modules/.pnpm/available-typed-arrays@1.0.7/node_modules/available-typed-arrays/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/available-typed-arrays@1.0.7/node_modules/available-typed-arrays/README.md` | EN | README |
| `node_modules/.pnpm/axe-core@4.11.1/node_modules/axe-core/README.md` | EN | README |
| `node_modules/.pnpm/axe-core@4.11.1/node_modules/axe-core/locales/README.md` | EN | README |
| `node_modules/.pnpm/axobject-query@4.1.0/node_modules/axobject-query/README.md` | EN | README |
| `node_modules/.pnpm/balanced-match@1.0.2/node_modules/balanced-match/LICENSE.md` | EN | other |
| `node_modules/.pnpm/balanced-match@1.0.2/node_modules/balanced-match/README.md` | EN | README |
| `node_modules/.pnpm/balanced-match@4.0.4/node_modules/balanced-match/LICENSE.md` | EN | other |
| `node_modules/.pnpm/balanced-match@4.0.4/node_modules/balanced-match/README.md` | EN | README |
| `node_modules/.pnpm/baseline-browser-mapping@2.10.8/node_modules/baseline-browser-mapping/README.md` | EN | README |
| `node_modules/.pnpm/binary-extensions@2.3.0/node_modules/binary-extensions/readme.md` | EN | README |
| `node_modules/.pnpm/brace-expansion@1.1.12/node_modules/brace-expansion/README.md` | EN | README |
| `node_modules/.pnpm/brace-expansion@2.0.2/node_modules/brace-expansion/README.md` | EN | README |
| `node_modules/.pnpm/brace-expansion@5.0.5/node_modules/brace-expansion/README.md` | EN | README |
| `node_modules/.pnpm/braces@3.0.3/node_modules/braces/README.md` | EN | README |
| `node_modules/.pnpm/browserslist@4.28.1/node_modules/browserslist/README.md` | EN | README |
| `node_modules/.pnpm/cac@6.7.14/node_modules/cac/README.md` | EN | README |
| `node_modules/.pnpm/call-bind-apply-helpers@1.0.2/node_modules/call-bind-apply-helpers/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/call-bind-apply-helpers@1.0.2/node_modules/call-bind-apply-helpers/README.md` | EN | README |
| `node_modules/.pnpm/call-bind@1.0.8/node_modules/call-bind/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/call-bind@1.0.8/node_modules/call-bind/README.md` | EN | README |
| `node_modules/.pnpm/call-bound@1.0.4/node_modules/call-bound/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/call-bound@1.0.4/node_modules/call-bound/README.md` | EN | README |
| `node_modules/.pnpm/callsites@3.1.0/node_modules/callsites/readme.md` | EN | README |
| `node_modules/.pnpm/camelcase-css@2.0.1/node_modules/camelcase-css/README.md` | EN | README |
| `node_modules/.pnpm/caniuse-lite@1.0.30001769/node_modules/caniuse-lite/README.md` | EN | README |
| `node_modules/.pnpm/caniuse-lite@1.0.30001780/node_modules/caniuse-lite/README.md` | EN | README |
| `node_modules/.pnpm/chai@5.3.3/node_modules/chai/README.md` | EN | README |
| `node_modules/.pnpm/chalk@4.1.2/node_modules/chalk/readme.md` | EN | README |
| `node_modules/.pnpm/chalk@5.6.2/node_modules/chalk/readme.md` | EN | README |
| `node_modules/.pnpm/check-error@2.1.3/node_modules/check-error/README.md` | EN | README |
| `node_modules/.pnpm/chokidar@3.6.0/node_modules/chokidar/README.md` | EN | README |
| `node_modules/.pnpm/class-variance-authority@0.7.1/node_modules/class-variance-authority/README.md` | EN | README |
| `node_modules/.pnpm/clsx@2.1.1/node_modules/clsx/readme.md` | EN | README |
| `node_modules/.pnpm/color-convert@2.0.1/node_modules/color-convert/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/color-convert@2.0.1/node_modules/color-convert/README.md` | EN | README |
| `node_modules/.pnpm/color-name@1.1.4/node_modules/color-name/README.md` | EN | README |
| `node_modules/.pnpm/combined-stream@1.0.8/node_modules/combined-stream/Readme.md` | EN | README |
| `node_modules/.pnpm/commander@4.1.1/node_modules/commander/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/commander@4.1.1/node_modules/commander/Readme.md` | EN | README |
| `node_modules/.pnpm/convert-source-map@2.0.0/node_modules/convert-source-map/README.md` | EN | README |
| `node_modules/.pnpm/cross-spawn@7.0.6/node_modules/cross-spawn/README.md` | EN | README |
| `node_modules/.pnpm/css.escape@1.5.1/node_modules/css.escape/README.md` | EN | README |
| `node_modules/.pnpm/cssesc@3.0.0/node_modules/cssesc/README.md` | EN | README |
| `node_modules/.pnpm/cssstyle@4.6.0/node_modules/cssstyle/README.md` | EN | README |
| `node_modules/.pnpm/csstype@3.2.3/node_modules/csstype/README.md` | EN | README |
| `node_modules/.pnpm/damerau-levenshtein@1.0.8/node_modules/damerau-levenshtein/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/damerau-levenshtein@1.0.8/node_modules/damerau-levenshtein/README.md` | EN | README |
| `node_modules/.pnpm/data-urls@5.0.0/node_modules/data-urls/README.md` | EN | README |
| `node_modules/.pnpm/data-view-buffer@1.0.2/node_modules/data-view-buffer/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/data-view-buffer@1.0.2/node_modules/data-view-buffer/README.md` | EN | README |
| `node_modules/.pnpm/data-view-byte-length@1.0.2/node_modules/data-view-byte-length/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/data-view-byte-length@1.0.2/node_modules/data-view-byte-length/README.md` | EN | README |
| `node_modules/.pnpm/data-view-byte-offset@1.0.1/node_modules/data-view-byte-offset/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/data-view-byte-offset@1.0.1/node_modules/data-view-byte-offset/README.md` | EN | README |
| `node_modules/.pnpm/debug@3.2.7/node_modules/debug/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/debug@3.2.7/node_modules/debug/README.md` | EN | README |
| `node_modules/.pnpm/debug@4.4.3/node_modules/debug/README.md` | EN | README |
| `node_modules/.pnpm/decimal.js@10.6.0/node_modules/decimal.js/LICENCE.md` | EN | other |
| `node_modules/.pnpm/decimal.js@10.6.0/node_modules/decimal.js/README.md` | EN | README |
| `node_modules/.pnpm/deep-eql@5.0.2/node_modules/deep-eql/README.md` | EN | README |
| `node_modules/.pnpm/define-data-property@1.1.4/node_modules/define-data-property/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/define-data-property@1.1.4/node_modules/define-data-property/README.md` | EN | README |
| `node_modules/.pnpm/define-properties@1.2.1/node_modules/define-properties/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/define-properties@1.2.1/node_modules/define-properties/README.md` | EN | README |
| `node_modules/.pnpm/delayed-stream@1.0.0/node_modules/delayed-stream/Readme.md` | EN | README |
| `node_modules/.pnpm/dequal@2.0.3/node_modules/dequal/readme.md` | EN | README |
| `node_modules/.pnpm/detect-libc@2.1.2/node_modules/detect-libc/README.md` | EN | README |
| `node_modules/.pnpm/didyoumean@1.2.2/node_modules/didyoumean/README.md` | EN | README |
| `node_modules/.pnpm/dlv@1.1.3/node_modules/dlv/README.md` | EN | README |
| `node_modules/.pnpm/doctrine@2.1.0/node_modules/doctrine/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/doctrine@2.1.0/node_modules/doctrine/README.md` | EN | README |
| `node_modules/.pnpm/doctrine@3.0.0/node_modules/doctrine/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/doctrine@3.0.0/node_modules/doctrine/README.md` | EN | README |
| `node_modules/.pnpm/dom-accessibility-api@0.5.16/node_modules/dom-accessibility-api/LICENSE.md` | EN | other |
| `node_modules/.pnpm/dom-accessibility-api@0.5.16/node_modules/dom-accessibility-api/README.md` | EN | README |
| `node_modules/.pnpm/dom-accessibility-api@0.6.3/node_modules/dom-accessibility-api/LICENSE.md` | EN | other |
| `node_modules/.pnpm/dom-accessibility-api@0.6.3/node_modules/dom-accessibility-api/README.md` | EN | README |
| `node_modules/.pnpm/dunder-proto@1.0.1/node_modules/dunder-proto/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/dunder-proto@1.0.1/node_modules/dunder-proto/README.md` | EN | README |
| `node_modules/.pnpm/eastasianwidth@0.2.0/node_modules/eastasianwidth/README.md` | Mixed | README |
| `node_modules/.pnpm/electron-to-chromium@1.5.286/node_modules/electron-to-chromium/README.md` | EN | README |
| `node_modules/.pnpm/emoji-regex@8.0.0/node_modules/emoji-regex/README.md` | EN | README |
| `node_modules/.pnpm/emoji-regex@9.2.2/node_modules/emoji-regex/README.md` | EN | README |
| `node_modules/.pnpm/entities@6.0.1/node_modules/entities/readme.md` | EN | README |
| `node_modules/.pnpm/es-abstract@1.24.1/node_modules/es-abstract/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/es-abstract@1.24.1/node_modules/es-abstract/README.md` | EN | README |
| `node_modules/.pnpm/es-define-property@1.0.1/node_modules/es-define-property/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/es-define-property@1.0.1/node_modules/es-define-property/README.md` | EN | README |
| `node_modules/.pnpm/es-errors@1.3.0/node_modules/es-errors/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/es-errors@1.3.0/node_modules/es-errors/README.md` | EN | README |
| `node_modules/.pnpm/es-iterator-helpers@1.2.2/node_modules/es-iterator-helpers/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/es-iterator-helpers@1.2.2/node_modules/es-iterator-helpers/README.md` | EN | README |
| `node_modules/.pnpm/es-module-lexer@1.7.0/node_modules/es-module-lexer/README.md` | EN | README |
| `node_modules/.pnpm/es-object-atoms@1.1.1/node_modules/es-object-atoms/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/es-object-atoms@1.1.1/node_modules/es-object-atoms/README.md` | EN | README |
| `node_modules/.pnpm/es-set-tostringtag@2.1.0/node_modules/es-set-tostringtag/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/es-set-tostringtag@2.1.0/node_modules/es-set-tostringtag/README.md` | EN | README |
| `node_modules/.pnpm/es-shim-unscopables@1.1.0/node_modules/es-shim-unscopables/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/es-shim-unscopables@1.1.0/node_modules/es-shim-unscopables/README.md` | EN | README |
| `node_modules/.pnpm/es-to-primitive@1.3.0/node_modules/es-to-primitive/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/es-to-primitive@1.3.0/node_modules/es-to-primitive/README.md` | EN | README |
| `node_modules/.pnpm/esbuild@0.21.5/node_modules/esbuild/LICENSE.md` | EN | other |
| `node_modules/.pnpm/esbuild@0.21.5/node_modules/esbuild/README.md` | EN | README |
| `node_modules/.pnpm/escalade@3.2.0/node_modules/escalade/readme.md` | EN | README |
| `node_modules/.pnpm/escape-string-regexp@4.0.0/node_modules/escape-string-regexp/readme.md` | EN | README |
| `node_modules/.pnpm/eslint-import-resolver-node@0.3.9/node_modules/eslint-import-resolver-node/README.md` | EN | README |
| `node_modules/.pnpm/eslint-import-resolver-typescript@3.10.1_eslint-plugin-import@2.32.0_eslint@8.57.1/node_modules/eslint-import-resolver-typescript/README.md` | EN | README |
| `node_modules/.pnpm/eslint-module-utils@2.12.1_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3__e_b3rgvxa4h7mpu2hkqbzzj3huau/node_modules/eslint-module-utils/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/README.md` | EN | README |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/SECURITY.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/consistent-type-specifier-style.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/default.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/dynamic-import-chunkname.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/enforce-node-protocol-usage.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/export.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/exports-last.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/extensions.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/first.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/group-exports.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/imports-first.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/max-dependencies.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/named.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/namespace.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/newline-after-import.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-absolute-path.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-amd.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-anonymous-default-export.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-commonjs.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-cycle.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-default-export.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-deprecated.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-duplicates.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-dynamic-require.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-empty-named-blocks.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-extraneous-dependencies.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-import-module-exports.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-internal-modules.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-mutable-exports.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-named-as-default-member.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-named-as-default.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-named-default.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-named-export.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-namespace.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-nodejs-modules.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-relative-packages.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-relative-parent-imports.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-restricted-paths.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-self-import.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-unassigned-import.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-unresolved.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-unused-modules.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-useless-path-segments.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/no-webpack-loader-syntax.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/order.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/prefer-default-export.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/docs/rules/unambiguous.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-import@2.32.0_@typescript-eslint+parser@8.55.0_eslint@8.57.1_typescript@5.9.3___6ggcwg5p4roxciqevsgi2osdie/node_modules/eslint-plugin-import/memo-parser/README.md` | EN | README |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/LICENSE.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/README.md` | EN | README |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/accessible-emoji.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/alt-text.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/anchor-ambiguous-text.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/anchor-has-content.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/anchor-is-valid.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/aria-activedescendant-has-tabindex.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/aria-props.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/aria-proptypes.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/aria-role.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/aria-unsupported-elements.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/autocomplete-valid.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/click-events-have-key-events.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/control-has-associated-label.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/heading-has-content.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/html-has-lang.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/iframe-has-title.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/img-redundant-alt.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/interactive-supports-focus.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/label-has-associated-control.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/label-has-for.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/lang.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/media-has-caption.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/mouse-events-have-key-events.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/no-access-key.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/no-aria-hidden-on-focusable.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/no-autofocus.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/no-distracting-elements.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/no-interactive-element-to-noninteractive-role.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/no-noninteractive-element-interactions.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/no-noninteractive-element-to-interactive-role.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/no-noninteractive-tabindex.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/no-onchange.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/no-redundant-roles.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/no-static-element-interactions.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/prefer-tag-over-role.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/role-has-required-aria-props.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/role-supports-aria-props.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/scope.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-jsx-a11y@6.10.2_eslint@8.57.1/node_modules/eslint-plugin-jsx-a11y/docs/rules/tabindex-no-positive.md` | EN | other |
| `node_modules/.pnpm/eslint-plugin-react-hooks@5.2.0_eslint@8.57.1/node_modules/eslint-plugin-react-hooks/README.md` | EN | README |
| `node_modules/.pnpm/eslint-plugin-react@7.37.5_eslint@8.57.1/node_modules/eslint-plugin-react/README.md` | EN | README |
| `node_modules/.pnpm/eslint-scope@7.2.2/node_modules/eslint-scope/README.md` | EN | README |
| `node_modules/.pnpm/eslint-visitor-keys@3.4.3/node_modules/eslint-visitor-keys/README.md` | EN | README |
| `node_modules/.pnpm/eslint-visitor-keys@4.2.1/node_modules/eslint-visitor-keys/README.md` | EN | README |
| `node_modules/.pnpm/eslint@8.57.1/node_modules/eslint/README.md` | EN | README |
| `node_modules/.pnpm/espree@9.6.1/node_modules/espree/README.md` | EN | README |
| `node_modules/.pnpm/esquery@1.7.0/node_modules/esquery/README.md` | EN | README |
| `node_modules/.pnpm/esrecurse@4.3.0/node_modules/esrecurse/README.md` | EN | README |
| `node_modules/.pnpm/estraverse@5.3.0/node_modules/estraverse/README.md` | EN | README |
| `node_modules/.pnpm/estree-walker@3.0.3/node_modules/estree-walker/README.md` | EN | README |
| `node_modules/.pnpm/esutils@2.0.3/node_modules/esutils/README.md` | EN | README |
| `node_modules/.pnpm/expect-type@1.3.0/node_modules/expect-type/README.md` | EN | README |
| `node_modules/.pnpm/expect-type@1.3.0/node_modules/expect-type/SECURITY.md` | EN | other |
| `node_modules/.pnpm/fast-deep-equal@3.1.3/node_modules/fast-deep-equal/README.md` | EN | README |
| `node_modules/.pnpm/fast-glob@3.3.1/node_modules/fast-glob/README.md` | EN | README |
| `node_modules/.pnpm/fast-glob@3.3.3/node_modules/fast-glob/README.md` | EN | README |
| `node_modules/.pnpm/fast-json-stable-stringify@2.1.0/node_modules/fast-json-stable-stringify/README.md` | EN | README |
| `node_modules/.pnpm/fast-levenshtein@2.0.6/node_modules/fast-levenshtein/LICENSE.md` | EN | other |
| `node_modules/.pnpm/fast-levenshtein@2.0.6/node_modules/fast-levenshtein/README.md` | EN | README |
| `node_modules/.pnpm/fastq@1.20.1/node_modules/fastq/README.md` | EN | README |
| `node_modules/.pnpm/fastq@1.20.1/node_modules/fastq/SECURITY.md` | EN | other |
| `node_modules/.pnpm/fdir@6.5.0_picomatch@4.0.3/node_modules/fdir/README.md` | EN | README |
| `node_modules/.pnpm/file-entry-cache@6.0.1/node_modules/file-entry-cache/README.md` | EN | README |
| `node_modules/.pnpm/file-entry-cache@6.0.1/node_modules/file-entry-cache/changelog.md` | EN | other |
| `node_modules/.pnpm/fill-range@7.1.1/node_modules/fill-range/README.md` | EN | README |
| `node_modules/.pnpm/find-up@5.0.0/node_modules/find-up/readme.md` | EN | README |
| `node_modules/.pnpm/flat-cache@3.2.0/node_modules/flat-cache/README.md` | EN | README |
| `node_modules/.pnpm/flat-cache@3.2.0/node_modules/flat-cache/changelog.md` | EN | other |
| `node_modules/.pnpm/flatted@3.3.3/node_modules/flatted/README.md` | EN | README |
| `node_modules/.pnpm/for-each@0.3.5/node_modules/for-each/.github/SECURITY.md` | EN | other |
| `node_modules/.pnpm/for-each@0.3.5/node_modules/for-each/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/for-each@0.3.5/node_modules/for-each/README.md` | EN | README |
| `node_modules/.pnpm/foreground-child@3.3.1/node_modules/foreground-child/README.md` | EN | README |
| `node_modules/.pnpm/form-data@4.0.5/node_modules/form-data/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/form-data@4.0.5/node_modules/form-data/README.md` | EN | README |
| `node_modules/.pnpm/fraction.js@5.3.4/node_modules/fraction.js/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/fraction.js@5.3.4/node_modules/fraction.js/README.md` | EN | README |
| `node_modules/.pnpm/fs.realpath@1.0.0/node_modules/fs.realpath/README.md` | EN | README |
| `node_modules/.pnpm/function-bind@1.1.2/node_modules/function-bind/.github/SECURITY.md` | EN | other |
| `node_modules/.pnpm/function-bind@1.1.2/node_modules/function-bind/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/function-bind@1.1.2/node_modules/function-bind/README.md` | EN | README |
| `node_modules/.pnpm/function.prototype.name@1.1.8/node_modules/function.prototype.name/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/function.prototype.name@1.1.8/node_modules/function.prototype.name/README.md` | EN | README |
| `node_modules/.pnpm/functions-have-names@1.2.3/node_modules/functions-have-names/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/functions-have-names@1.2.3/node_modules/functions-have-names/README.md` | EN | README |
| `node_modules/.pnpm/generator-function@2.0.1/node_modules/generator-function/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/generator-function@2.0.1/node_modules/generator-function/LICENSE.md` | EN | other |
| `node_modules/.pnpm/generator-function@2.0.1/node_modules/generator-function/README.md` | EN | README |
| `node_modules/.pnpm/gensync@1.0.0-beta.2/node_modules/gensync/README.md` | EN | README |
| `node_modules/.pnpm/get-intrinsic@1.3.0/node_modules/get-intrinsic/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/get-intrinsic@1.3.0/node_modules/get-intrinsic/README.md` | EN | README |
| `node_modules/.pnpm/get-proto@1.0.1/node_modules/get-proto/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/get-proto@1.0.1/node_modules/get-proto/README.md` | EN | README |
| `node_modules/.pnpm/get-symbol-description@1.1.0/node_modules/get-symbol-description/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/get-symbol-description@1.1.0/node_modules/get-symbol-description/README.md` | EN | README |
| `node_modules/.pnpm/get-tsconfig@4.13.6/node_modules/get-tsconfig/README.md` | EN | README |
| `node_modules/.pnpm/glob-parent@5.1.2/node_modules/glob-parent/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/glob-parent@5.1.2/node_modules/glob-parent/README.md` | EN | README |
| `node_modules/.pnpm/glob-parent@6.0.2/node_modules/glob-parent/README.md` | EN | README |
| `node_modules/.pnpm/glob@10.5.0/node_modules/glob/README.md` | EN | README |
| `node_modules/.pnpm/glob@7.2.3/node_modules/glob/README.md` | EN | README |
| `node_modules/.pnpm/globals@13.24.0/node_modules/globals/readme.md` | EN | README |
| `node_modules/.pnpm/globalthis@1.0.4/node_modules/globalthis/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/globalthis@1.0.4/node_modules/globalthis/README.md` | EN | README |
| `node_modules/.pnpm/gopd@1.2.0/node_modules/gopd/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/gopd@1.2.0/node_modules/gopd/README.md` | EN | README |
| `node_modules/.pnpm/graphemer@1.4.0/node_modules/graphemer/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/graphemer@1.4.0/node_modules/graphemer/README.md` | EN | README |
| `node_modules/.pnpm/has-bigints@1.1.0/node_modules/has-bigints/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/has-bigints@1.1.0/node_modules/has-bigints/README.md` | EN | README |
| `node_modules/.pnpm/has-flag@4.0.0/node_modules/has-flag/readme.md` | EN | README |
| `node_modules/.pnpm/has-property-descriptors@1.0.2/node_modules/has-property-descriptors/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/has-property-descriptors@1.0.2/node_modules/has-property-descriptors/README.md` | EN | README |
| `node_modules/.pnpm/has-proto@1.2.0/node_modules/has-proto/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/has-proto@1.2.0/node_modules/has-proto/README.md` | EN | README |
| `node_modules/.pnpm/has-symbols@1.1.0/node_modules/has-symbols/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/has-symbols@1.1.0/node_modules/has-symbols/README.md` | EN | README |
| `node_modules/.pnpm/has-tostringtag@1.0.2/node_modules/has-tostringtag/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/has-tostringtag@1.0.2/node_modules/has-tostringtag/README.md` | EN | README |
| `node_modules/.pnpm/hasown@2.0.2/node_modules/hasown/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/hasown@2.0.2/node_modules/hasown/README.md` | EN | README |
| `node_modules/.pnpm/html-encoding-sniffer@4.0.0/node_modules/html-encoding-sniffer/README.md` | EN | README |
| `node_modules/.pnpm/html-escaper@2.0.2/node_modules/html-escaper/README.md` | EN | README |
| `node_modules/.pnpm/http-proxy-agent@7.0.2/node_modules/http-proxy-agent/README.md` | EN | README |
| `node_modules/.pnpm/https-proxy-agent@7.0.6/node_modules/https-proxy-agent/README.md` | EN | README |
| `node_modules/.pnpm/iconv-lite@0.6.3/node_modules/iconv-lite/Changelog.md` | EN | other |
| `node_modules/.pnpm/iconv-lite@0.6.3/node_modules/iconv-lite/README.md` | EN | README |
| `node_modules/.pnpm/ignore@5.3.2/node_modules/ignore/README.md` | EN | README |
| `node_modules/.pnpm/ignore@7.0.5/node_modules/ignore/README.md` | EN | README |
| `node_modules/.pnpm/import-fresh@3.3.1/node_modules/import-fresh/readme.md` | EN | README |
| `node_modules/.pnpm/imurmurhash@0.1.4/node_modules/imurmurhash/README.md` | EN | README |
| `node_modules/.pnpm/indent-string@4.0.0/node_modules/indent-string/readme.md` | EN | README |
| `node_modules/.pnpm/inflight@1.0.6/node_modules/inflight/README.md` | EN | README |
| `node_modules/.pnpm/inherits@2.0.4/node_modules/inherits/README.md` | EN | README |
| `node_modules/.pnpm/internal-slot@1.1.0/node_modules/internal-slot/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/internal-slot@1.1.0/node_modules/internal-slot/README.md` | EN | README |
| `node_modules/.pnpm/is-array-buffer@3.0.5/node_modules/is-array-buffer/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-array-buffer@3.0.5/node_modules/is-array-buffer/README.md` | EN | README |
| `node_modules/.pnpm/is-async-function@2.1.1/node_modules/is-async-function/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-async-function@2.1.1/node_modules/is-async-function/README.md` | EN | README |
| `node_modules/.pnpm/is-bigint@1.1.0/node_modules/is-bigint/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-bigint@1.1.0/node_modules/is-bigint/README.md` | EN | README |
| `node_modules/.pnpm/is-binary-path@2.1.0/node_modules/is-binary-path/readme.md` | EN | README |
| `node_modules/.pnpm/is-boolean-object@1.2.2/node_modules/is-boolean-object/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-boolean-object@1.2.2/node_modules/is-boolean-object/README.md` | EN | README |
| `node_modules/.pnpm/is-bun-module@2.0.0/node_modules/is-bun-module/README.md` | EN | README |
| `node_modules/.pnpm/is-callable@1.2.7/node_modules/is-callable/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-callable@1.2.7/node_modules/is-callable/README.md` | EN | README |
| `node_modules/.pnpm/is-core-module@2.16.1/node_modules/is-core-module/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-core-module@2.16.1/node_modules/is-core-module/README.md` | EN | README |
| `node_modules/.pnpm/is-data-view@1.0.2/node_modules/is-data-view/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-data-view@1.0.2/node_modules/is-data-view/README.md` | EN | README |
| `node_modules/.pnpm/is-date-object@1.1.0/node_modules/is-date-object/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-date-object@1.1.0/node_modules/is-date-object/README.md` | EN | README |
| `node_modules/.pnpm/is-extglob@2.1.1/node_modules/is-extglob/README.md` | EN | README |
| `node_modules/.pnpm/is-finalizationregistry@1.1.1/node_modules/is-finalizationregistry/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-finalizationregistry@1.1.1/node_modules/is-finalizationregistry/README.md` | EN | README |
| `node_modules/.pnpm/is-fullwidth-code-point@3.0.0/node_modules/is-fullwidth-code-point/readme.md` | EN | README |
| `node_modules/.pnpm/is-generator-function@1.1.2/node_modules/is-generator-function/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-generator-function@1.1.2/node_modules/is-generator-function/README.md` | EN | README |
| `node_modules/.pnpm/is-glob@4.0.3/node_modules/is-glob/README.md` | EN | README |
| `node_modules/.pnpm/is-map@2.0.3/node_modules/is-map/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-map@2.0.3/node_modules/is-map/README.md` | EN | README |
| `node_modules/.pnpm/is-negative-zero@2.0.3/node_modules/is-negative-zero/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-negative-zero@2.0.3/node_modules/is-negative-zero/README.md` | EN | README |
| `node_modules/.pnpm/is-number-object@1.1.1/node_modules/is-number-object/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-number-object@1.1.1/node_modules/is-number-object/README.md` | EN | README |
| `node_modules/.pnpm/is-number@7.0.0/node_modules/is-number/README.md` | EN | README |
| `node_modules/.pnpm/is-path-inside@3.0.3/node_modules/is-path-inside/readme.md` | EN | README |
| `node_modules/.pnpm/is-potential-custom-element-name@1.0.1/node_modules/is-potential-custom-element-name/README.md` | EN | README |
| `node_modules/.pnpm/is-regex@1.2.1/node_modules/is-regex/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-regex@1.2.1/node_modules/is-regex/README.md` | EN | README |
| `node_modules/.pnpm/is-set@2.0.3/node_modules/is-set/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-set@2.0.3/node_modules/is-set/README.md` | EN | README |
| `node_modules/.pnpm/is-shared-array-buffer@1.0.4/node_modules/is-shared-array-buffer/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-shared-array-buffer@1.0.4/node_modules/is-shared-array-buffer/README.md` | EN | README |
| `node_modules/.pnpm/is-string@1.1.1/node_modules/is-string/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-string@1.1.1/node_modules/is-string/README.md` | EN | README |
| `node_modules/.pnpm/is-symbol@1.1.1/node_modules/is-symbol/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-symbol@1.1.1/node_modules/is-symbol/README.md` | EN | README |
| `node_modules/.pnpm/is-typed-array@1.1.15/node_modules/is-typed-array/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-typed-array@1.1.15/node_modules/is-typed-array/README.md` | EN | README |
| `node_modules/.pnpm/is-weakmap@2.0.2/node_modules/is-weakmap/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-weakmap@2.0.2/node_modules/is-weakmap/README.md` | EN | README |
| `node_modules/.pnpm/is-weakref@1.1.1/node_modules/is-weakref/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-weakref@1.1.1/node_modules/is-weakref/README.md` | EN | README |
| `node_modules/.pnpm/is-weakset@2.0.4/node_modules/is-weakset/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/is-weakset@2.0.4/node_modules/is-weakset/README.md` | EN | README |
| `node_modules/.pnpm/isarray@2.0.5/node_modules/isarray/README.md` | EN | README |
| `node_modules/.pnpm/isexe@2.0.0/node_modules/isexe/README.md` | EN | README |
| `node_modules/.pnpm/istanbul-lib-coverage@3.2.2/node_modules/istanbul-lib-coverage/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/istanbul-lib-coverage@3.2.2/node_modules/istanbul-lib-coverage/README.md` | EN | README |
| `node_modules/.pnpm/istanbul-lib-report@3.0.1/node_modules/istanbul-lib-report/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/istanbul-lib-report@3.0.1/node_modules/istanbul-lib-report/README.md` | EN | README |
| `node_modules/.pnpm/istanbul-lib-source-maps@5.0.6/node_modules/istanbul-lib-source-maps/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/istanbul-lib-source-maps@5.0.6/node_modules/istanbul-lib-source-maps/README.md` | EN | README |
| `node_modules/.pnpm/istanbul-reports@3.2.0/node_modules/istanbul-reports/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/istanbul-reports@3.2.0/node_modules/istanbul-reports/README.md` | EN | README |
| `node_modules/.pnpm/iterator.prototype@1.1.5/node_modules/iterator.prototype/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/iterator.prototype@1.1.5/node_modules/iterator.prototype/README.md` | EN | README |
| `node_modules/.pnpm/jackspeak@3.4.3/node_modules/jackspeak/LICENSE.md` | EN | other |
| `node_modules/.pnpm/jackspeak@3.4.3/node_modules/jackspeak/README.md` | EN | README |
| `node_modules/.pnpm/jiti@1.21.7/node_modules/jiti/README.md` | EN | README |
| `node_modules/.pnpm/js-tokens@4.0.0/node_modules/js-tokens/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/js-tokens@4.0.0/node_modules/js-tokens/README.md` | EN | README |
| `node_modules/.pnpm/js-yaml@4.1.1/node_modules/js-yaml/README.md` | EN | README |
| `node_modules/.pnpm/jsdom@25.0.1/node_modules/jsdom/README.md` | EN | README |
| `node_modules/.pnpm/jsesc@3.1.0/node_modules/jsesc/README.md` | EN | README |
| `node_modules/.pnpm/json-buffer@3.0.1/node_modules/json-buffer/README.md` | EN | README |
| `node_modules/.pnpm/json-schema-traverse@0.4.1/node_modules/json-schema-traverse/README.md` | EN | README |
| `node_modules/.pnpm/json5@1.0.2/node_modules/json5/LICENSE.md` | EN | other |
| `node_modules/.pnpm/json5@1.0.2/node_modules/json5/README.md` | EN | README |
| `node_modules/.pnpm/json5@2.2.3/node_modules/json5/LICENSE.md` | EN | other |
| `node_modules/.pnpm/json5@2.2.3/node_modules/json5/README.md` | EN | README |
| `node_modules/.pnpm/jsx-ast-utils@3.3.5/node_modules/jsx-ast-utils/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/jsx-ast-utils@3.3.5/node_modules/jsx-ast-utils/LICENSE.md` | EN | other |
| `node_modules/.pnpm/jsx-ast-utils@3.3.5/node_modules/jsx-ast-utils/README.md` | EN | README |
| `node_modules/.pnpm/keyv@4.5.4/node_modules/keyv/README.md` | EN | README |
| `node_modules/.pnpm/language-subtag-registry@0.3.23/node_modules/language-subtag-registry/README.md` | EN | README |
| `node_modules/.pnpm/language-tags@1.0.9/node_modules/language-tags/README.md` | EN | README |
| `node_modules/.pnpm/levn@0.4.1/node_modules/levn/README.md` | EN | README |
| `node_modules/.pnpm/lilconfig@3.1.3/node_modules/lilconfig/readme.md` | EN | README |
| `node_modules/.pnpm/lines-and-columns@1.2.4/node_modules/lines-and-columns/README.md` | EN | README |
| `node_modules/.pnpm/locate-path@6.0.0/node_modules/locate-path/readme.md` | EN | README |
| `node_modules/.pnpm/lodash-es@4.17.23/node_modules/lodash-es/README.md` | EN | README |
| `node_modules/.pnpm/lodash.merge@4.6.2/node_modules/lodash.merge/README.md` | EN | README |
| `node_modules/.pnpm/loose-envify@1.4.0/node_modules/loose-envify/README.md` | EN | README |
| `node_modules/.pnpm/loupe@3.2.1/node_modules/loupe/README.md` | EN | README |
| `node_modules/.pnpm/lru-cache@10.4.3/node_modules/lru-cache/README.md` | EN | README |
| `node_modules/.pnpm/lru-cache@5.1.1/node_modules/lru-cache/README.md` | EN | README |
| `node_modules/.pnpm/lucide-react@0.469.0_react@18.3.1/node_modules/lucide-react/README.md` | EN | README |
| `node_modules/.pnpm/lz-string@1.5.0/node_modules/lz-string/README.md` | EN | README |
| `node_modules/.pnpm/magic-string@0.30.21/node_modules/magic-string/README.md` | EN | README |
| `node_modules/.pnpm/magicast@0.3.5/node_modules/magicast/README.md` | EN | README |
| `node_modules/.pnpm/make-dir@4.0.0/node_modules/make-dir/readme.md` | EN | README |
| `node_modules/.pnpm/math-intrinsics@1.1.0/node_modules/math-intrinsics/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/math-intrinsics@1.1.0/node_modules/math-intrinsics/README.md` | EN | README |
| `node_modules/.pnpm/merge2@1.4.1/node_modules/merge2/README.md` | EN | README |
| `node_modules/.pnpm/micromatch@4.0.8/node_modules/micromatch/README.md` | EN | README |
| `node_modules/.pnpm/mime-db@1.52.0/node_modules/mime-db/HISTORY.md` | EN | other |
| `node_modules/.pnpm/mime-db@1.52.0/node_modules/mime-db/README.md` | EN | README |
| `node_modules/.pnpm/mime-types@2.1.35/node_modules/mime-types/HISTORY.md` | EN | other |
| `node_modules/.pnpm/mime-types@2.1.35/node_modules/mime-types/README.md` | EN | README |
| `node_modules/.pnpm/min-indent@1.0.1/node_modules/min-indent/readme.md` | EN | README |
| `node_modules/.pnpm/minimatch@10.2.5/node_modules/minimatch/LICENSE.md` | EN | other |
| `node_modules/.pnpm/minimatch@10.2.5/node_modules/minimatch/README.md` | EN | README |
| `node_modules/.pnpm/minimatch@3.1.2/node_modules/minimatch/README.md` | EN | README |
| `node_modules/.pnpm/minimatch@9.0.5/node_modules/minimatch/README.md` | EN | README |
| `node_modules/.pnpm/minimist@1.2.8/node_modules/minimist/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/minimist@1.2.8/node_modules/minimist/README.md` | EN | README |
| `node_modules/.pnpm/minipass@7.1.3/node_modules/minipass/LICENSE.md` | EN | other |
| `node_modules/.pnpm/minipass@7.1.3/node_modules/minipass/README.md` | EN | README |
| `node_modules/.pnpm/ms@2.1.3/node_modules/ms/license.md` | EN | other |
| `node_modules/.pnpm/ms@2.1.3/node_modules/ms/readme.md` | EN | README |
| `node_modules/.pnpm/mz@2.7.0/node_modules/mz/HISTORY.md` | EN | other |
| `node_modules/.pnpm/mz@2.7.0/node_modules/mz/README.md` | EN | README |
| `node_modules/.pnpm/nanoid@3.3.11/node_modules/nanoid/README.md` | Mixed | README |
| `node_modules/.pnpm/napi-postinstall@0.3.4/node_modules/napi-postinstall/README.md` | EN | README |
| `node_modules/.pnpm/natural-compare@1.4.0/node_modules/natural-compare/README.md` | EN | README |
| `node_modules/.pnpm/next@16.1.7_@babel+core@7.29.0_@playwright+test@1.58.2_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/README.md` | EN | README |
| `node_modules/.pnpm/next@16.1.7_@babel+core@7.29.0_@playwright+test@1.58.2_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/dist/compiled/@babel/runtime/README.md` | EN | README |
| `node_modules/.pnpm/next@16.1.7_@babel+core@7.29.0_@playwright+test@1.58.2_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/dist/compiled/react-is/README.md` | EN | README |
| `node_modules/.pnpm/next@16.1.7_@babel+core@7.29.0_@playwright+test@1.58.2_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/dist/compiled/react-refresh/README.md` | EN | README |
| `node_modules/.pnpm/next@16.1.7_@babel+core@7.29.0_@playwright+test@1.58.2_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/dist/compiled/regenerator-runtime/README.md` | EN | README |
| `node_modules/.pnpm/next@16.1.7_@babel+core@7.29.0_@playwright+test@1.58.2_react-dom@18.3.1_react@18.3.1__react@18.3.1/node_modules/next/license.md` | EN | other |
| `node_modules/.pnpm/node-releases@2.0.27/node_modules/node-releases/README.md` | EN | README |
| `node_modules/.pnpm/normalize-path@3.0.0/node_modules/normalize-path/README.md` | EN | README |
| `node_modules/.pnpm/nwsapi@2.2.23/node_modules/nwsapi/README.md` | EN | README |
| `node_modules/.pnpm/object-assign@4.1.1/node_modules/object-assign/readme.md` | EN | README |
| `node_modules/.pnpm/object-inspect@1.13.4/node_modules/object-inspect/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/object-keys@1.1.1/node_modules/object-keys/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/object-keys@1.1.1/node_modules/object-keys/README.md` | EN | README |
| `node_modules/.pnpm/object.assign@4.1.7/node_modules/object.assign/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/object.assign@4.1.7/node_modules/object.assign/README.md` | EN | README |
| `node_modules/.pnpm/object.entries@1.1.9/node_modules/object.entries/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/object.entries@1.1.9/node_modules/object.entries/README.md` | EN | README |
| `node_modules/.pnpm/object.fromentries@2.0.8/node_modules/object.fromentries/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/object.fromentries@2.0.8/node_modules/object.fromentries/README.md` | EN | README |
| `node_modules/.pnpm/object.groupby@1.0.3/node_modules/object.groupby/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/object.groupby@1.0.3/node_modules/object.groupby/README.md` | EN | README |
| `node_modules/.pnpm/object.values@1.2.1/node_modules/object.values/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/object.values@1.2.1/node_modules/object.values/README.md` | EN | README |
| `node_modules/.pnpm/once@1.4.0/node_modules/once/README.md` | EN | README |
| `node_modules/.pnpm/optionator@0.9.4/node_modules/optionator/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/optionator@0.9.4/node_modules/optionator/README.md` | EN | README |
| `node_modules/.pnpm/own-keys@1.0.1/node_modules/own-keys/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/own-keys@1.0.1/node_modules/own-keys/README.md` | EN | README |
| `node_modules/.pnpm/p-limit@3.1.0/node_modules/p-limit/readme.md` | EN | README |
| `node_modules/.pnpm/p-locate@5.0.0/node_modules/p-locate/readme.md` | EN | README |
| `node_modules/.pnpm/package-json-from-dist@1.0.1/node_modules/package-json-from-dist/LICENSE.md` | EN | other |
| `node_modules/.pnpm/package-json-from-dist@1.0.1/node_modules/package-json-from-dist/README.md` | EN | README |
| `node_modules/.pnpm/parent-module@1.0.1/node_modules/parent-module/readme.md` | EN | README |
| `node_modules/.pnpm/parse5@7.3.0/node_modules/parse5/README.md` | EN | README |
| `node_modules/.pnpm/path-exists@4.0.0/node_modules/path-exists/readme.md` | EN | README |
| `node_modules/.pnpm/path-is-absolute@1.0.1/node_modules/path-is-absolute/readme.md` | EN | README |
| `node_modules/.pnpm/path-key@3.1.1/node_modules/path-key/readme.md` | EN | README |
| `node_modules/.pnpm/path-parse@1.0.7/node_modules/path-parse/README.md` | EN | README |
| `node_modules/.pnpm/path-scurry@1.11.1/node_modules/path-scurry/LICENSE.md` | EN | other |
| `node_modules/.pnpm/path-scurry@1.11.1/node_modules/path-scurry/README.md` | EN | README |
| `node_modules/.pnpm/pathe@1.1.2/node_modules/pathe/README.md` | EN | README |
| `node_modules/.pnpm/pathval@2.0.1/node_modules/pathval/README.md` | EN | README |
| `node_modules/.pnpm/picocolors@1.1.1/node_modules/picocolors/README.md` | EN | README |
| `node_modules/.pnpm/picomatch@2.3.1/node_modules/picomatch/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/picomatch@2.3.1/node_modules/picomatch/README.md` | EN | README |
| `node_modules/.pnpm/picomatch@4.0.3/node_modules/picomatch/README.md` | EN | README |
| `node_modules/.pnpm/pify@2.3.0/node_modules/pify/readme.md` | EN | README |
| `node_modules/.pnpm/pirates@4.0.7/node_modules/pirates/README.md` | EN | README |
| `node_modules/.pnpm/playwright-core@1.58.2/node_modules/playwright-core/README.md` | EN | README |
| `node_modules/.pnpm/playwright@1.58.2/node_modules/playwright/README.md` | EN | README |
| `node_modules/.pnpm/playwright@1.58.2/node_modules/playwright/lib/agents/playwright-test-coverage.prompt.md` | EN | other |
| `node_modules/.pnpm/playwright@1.58.2/node_modules/playwright/lib/agents/playwright-test-generate.prompt.md` | EN | other |
| `node_modules/.pnpm/playwright@1.58.2/node_modules/playwright/lib/agents/playwright-test-generator.agent.md` | EN | other |
| `node_modules/.pnpm/playwright@1.58.2/node_modules/playwright/lib/agents/playwright-test-heal.prompt.md` | EN | other |
| `node_modules/.pnpm/playwright@1.58.2/node_modules/playwright/lib/agents/playwright-test-healer.agent.md` | EN | other |
| `node_modules/.pnpm/playwright@1.58.2/node_modules/playwright/lib/agents/playwright-test-plan.prompt.md` | EN | other |
| `node_modules/.pnpm/playwright@1.58.2/node_modules/playwright/lib/agents/playwright-test-planner.agent.md` | EN | other |
| `node_modules/.pnpm/possible-typed-array-names@1.1.0/node_modules/possible-typed-array-names/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/possible-typed-array-names@1.1.0/node_modules/possible-typed-array-names/README.md` | EN | README |
| `node_modules/.pnpm/postcss-import@15.1.0_postcss@8.5.6/node_modules/postcss-import/README.md` | EN | README |
| `node_modules/.pnpm/postcss-js@4.1.0_postcss@8.5.6/node_modules/postcss-js/README.md` | EN | README |
| `node_modules/.pnpm/postcss-load-config@6.0.1_jiti@1.21.7_postcss@8.5.6/node_modules/postcss-load-config/README.md` | EN | README |
| `node_modules/.pnpm/postcss-nested@6.2.0_postcss@8.5.6/node_modules/postcss-nested/README.md` | EN | README |
| `node_modules/.pnpm/postcss-selector-parser@6.1.2/node_modules/postcss-selector-parser/API.md` | EN | other |
| `node_modules/.pnpm/postcss-selector-parser@6.1.2/node_modules/postcss-selector-parser/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/postcss-selector-parser@6.1.2/node_modules/postcss-selector-parser/README.md` | EN | README |
| `node_modules/.pnpm/postcss-value-parser@4.2.0/node_modules/postcss-value-parser/README.md` | EN | README |
| `node_modules/.pnpm/postcss@8.4.31/node_modules/postcss/README.md` | EN | README |
| `node_modules/.pnpm/postcss@8.5.6/node_modules/postcss/README.md` | EN | README |
| `node_modules/.pnpm/prelude-ls@1.2.1/node_modules/prelude-ls/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/prelude-ls@1.2.1/node_modules/prelude-ls/README.md` | EN | README |
| `node_modules/.pnpm/pretty-format@27.5.1/node_modules/pretty-format/README.md` | EN | README |
| `node_modules/.pnpm/prop-types@15.8.1/node_modules/prop-types/README.md` | EN | README |
| `node_modules/.pnpm/punycode@2.3.1/node_modules/punycode/README.md` | EN | README |
| `node_modules/.pnpm/queue-microtask@1.2.3/node_modules/queue-microtask/README.md` | EN | README |
| `node_modules/.pnpm/react-dom@18.3.1_react@18.3.1/node_modules/react-dom/README.md` | EN | README |
| `node_modules/.pnpm/react-is@16.13.1/node_modules/react-is/README.md` | EN | README |
| `node_modules/.pnpm/react-is@17.0.2/node_modules/react-is/README.md` | EN | README |
| `node_modules/.pnpm/react-refresh@0.18.0/node_modules/react-refresh/README.md` | EN | README |
| `node_modules/.pnpm/react@18.3.1/node_modules/react/README.md` | EN | README |
| `node_modules/.pnpm/read-cache@1.0.0/node_modules/read-cache/README.md` | EN | README |
| `node_modules/.pnpm/readdirp@3.6.0/node_modules/readdirp/README.md` | EN | README |
| `node_modules/.pnpm/redent@3.0.0/node_modules/redent/readme.md` | EN | README |
| `node_modules/.pnpm/reflect.getprototypeof@1.0.10/node_modules/reflect.getprototypeof/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/reflect.getprototypeof@1.0.10/node_modules/reflect.getprototypeof/README.md` | EN | README |
| `node_modules/.pnpm/regexp.prototype.flags@1.5.4/node_modules/regexp.prototype.flags/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/regexp.prototype.flags@1.5.4/node_modules/regexp.prototype.flags/README.md` | EN | README |
| `node_modules/.pnpm/resolve-from@4.0.0/node_modules/resolve-from/readme.md` | EN | README |
| `node_modules/.pnpm/resolve-pkg-maps@1.0.0/node_modules/resolve-pkg-maps/README.md` | EN | README |
| `node_modules/.pnpm/resolve@1.22.11/node_modules/resolve/.github/INCIDENT_RESPONSE_PROCESS.md` | EN | other |
| `node_modules/.pnpm/resolve@1.22.11/node_modules/resolve/.github/THREAT_MODEL.md` | EN | other |
| `node_modules/.pnpm/resolve@1.22.11/node_modules/resolve/SECURITY.md` | EN | other |
| `node_modules/.pnpm/resolve@2.0.0-next.5/node_modules/resolve/SECURITY.md` | EN | other |
| `node_modules/.pnpm/reusify@1.1.0/node_modules/reusify/README.md` | EN | README |
| `node_modules/.pnpm/reusify@1.1.0/node_modules/reusify/SECURITY.md` | EN | other |
| `node_modules/.pnpm/rimraf@3.0.2/node_modules/rimraf/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/rimraf@3.0.2/node_modules/rimraf/README.md` | EN | README |
| `node_modules/.pnpm/rollup@4.57.1/node_modules/rollup/LICENSE.md` | EN | other |
| `node_modules/.pnpm/rollup@4.57.1/node_modules/rollup/README.md` | EN | README |
| `node_modules/.pnpm/run-parallel@1.2.0/node_modules/run-parallel/README.md` | EN | README |
| `node_modules/.pnpm/safe-array-concat@1.1.3/node_modules/safe-array-concat/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/safe-array-concat@1.1.3/node_modules/safe-array-concat/README.md` | EN | README |
| `node_modules/.pnpm/safe-push-apply@1.0.0/node_modules/safe-push-apply/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/safe-push-apply@1.0.0/node_modules/safe-push-apply/README.md` | EN | README |
| `node_modules/.pnpm/safe-regex-test@1.1.0/node_modules/safe-regex-test/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/safe-regex-test@1.1.0/node_modules/safe-regex-test/README.md` | EN | README |
| `node_modules/.pnpm/safer-buffer@2.1.2/node_modules/safer-buffer/Porting-Buffer.md` | EN | other |
| `node_modules/.pnpm/safer-buffer@2.1.2/node_modules/safer-buffer/Readme.md` | EN | README |
| `node_modules/.pnpm/saxes@6.0.0/node_modules/saxes/README.md` | EN | README |
| `node_modules/.pnpm/scheduler@0.23.2/node_modules/scheduler/README.md` | EN | README |
| `node_modules/.pnpm/semver@6.3.1/node_modules/semver/README.md` | EN | README |
| `node_modules/.pnpm/semver@7.7.4/node_modules/semver/README.md` | EN | README |
| `node_modules/.pnpm/set-function-length@1.2.2/node_modules/set-function-length/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/set-function-length@1.2.2/node_modules/set-function-length/README.md` | EN | README |
| `node_modules/.pnpm/set-function-name@2.0.2/node_modules/set-function-name/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/set-function-name@2.0.2/node_modules/set-function-name/README.md` | EN | README |
| `node_modules/.pnpm/set-proto@1.0.0/node_modules/set-proto/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/set-proto@1.0.0/node_modules/set-proto/README.md` | EN | README |
| `node_modules/.pnpm/sharp@0.34.5/node_modules/sharp/README.md` | EN | README |
| `node_modules/.pnpm/shebang-command@2.0.0/node_modules/shebang-command/readme.md` | EN | README |
| `node_modules/.pnpm/shebang-regex@3.0.0/node_modules/shebang-regex/readme.md` | EN | README |
| `node_modules/.pnpm/side-channel-list@1.0.0/node_modules/side-channel-list/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/side-channel-list@1.0.0/node_modules/side-channel-list/README.md` | EN | README |
| `node_modules/.pnpm/side-channel-map@1.0.1/node_modules/side-channel-map/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/side-channel-map@1.0.1/node_modules/side-channel-map/README.md` | EN | README |
| `node_modules/.pnpm/side-channel-weakmap@1.0.2/node_modules/side-channel-weakmap/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/side-channel-weakmap@1.0.2/node_modules/side-channel-weakmap/README.md` | EN | README |
| `node_modules/.pnpm/side-channel@1.1.0/node_modules/side-channel/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/side-channel@1.1.0/node_modules/side-channel/README.md` | EN | README |
| `node_modules/.pnpm/siginfo@2.0.0/node_modules/siginfo/README.md` | EN | README |
| `node_modules/.pnpm/signal-exit@4.1.0/node_modules/signal-exit/README.md` | EN | README |
| `node_modules/.pnpm/source-map-js@1.2.1/node_modules/source-map-js/README.md` | EN | README |
| `node_modules/.pnpm/stable-hash@0.0.5/node_modules/stable-hash/README.md` | EN | README |
| `node_modules/.pnpm/stackback@0.0.2/node_modules/stackback/README.md` | EN | README |
| `node_modules/.pnpm/std-env@3.10.0/node_modules/std-env/README.md` | EN | README |
| `node_modules/.pnpm/stop-iteration-iterator@1.1.0/node_modules/stop-iteration-iterator/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/stop-iteration-iterator@1.1.0/node_modules/stop-iteration-iterator/README.md` | EN | README |
| `node_modules/.pnpm/string-width@4.2.3/node_modules/string-width/readme.md` | EN | README |
| `node_modules/.pnpm/string-width@5.1.2/node_modules/string-width/readme.md` | EN | README |
| `node_modules/.pnpm/string.prototype.includes@2.0.1/node_modules/string.prototype.includes/README.md` | EN | README |
| `node_modules/.pnpm/string.prototype.matchall@4.0.12/node_modules/string.prototype.matchall/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/string.prototype.matchall@4.0.12/node_modules/string.prototype.matchall/README.md` | EN | README |
| `node_modules/.pnpm/string.prototype.repeat@1.0.0/node_modules/string.prototype.repeat/README.md` | EN | README |
| `node_modules/.pnpm/string.prototype.trim@1.2.10/node_modules/string.prototype.trim/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/string.prototype.trim@1.2.10/node_modules/string.prototype.trim/README.md` | EN | README |
| `node_modules/.pnpm/string.prototype.trimend@1.0.9/node_modules/string.prototype.trimend/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/string.prototype.trimend@1.0.9/node_modules/string.prototype.trimend/README.md` | EN | README |
| `node_modules/.pnpm/string.prototype.trimstart@1.0.8/node_modules/string.prototype.trimstart/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/string.prototype.trimstart@1.0.8/node_modules/string.prototype.trimstart/README.md` | EN | README |
| `node_modules/.pnpm/strip-ansi@6.0.1/node_modules/strip-ansi/readme.md` | EN | README |
| `node_modules/.pnpm/strip-ansi@7.2.0/node_modules/strip-ansi/readme.md` | EN | README |
| `node_modules/.pnpm/strip-bom@3.0.0/node_modules/strip-bom/readme.md` | EN | README |
| `node_modules/.pnpm/strip-indent@3.0.0/node_modules/strip-indent/readme.md` | EN | README |
| `node_modules/.pnpm/strip-json-comments@3.1.1/node_modules/strip-json-comments/readme.md` | EN | README |
| `node_modules/.pnpm/styled-jsx@5.1.6_@babel+core@7.29.0_react@18.3.1/node_modules/styled-jsx/license.md` | EN | other |
| `node_modules/.pnpm/styled-jsx@5.1.6_@babel+core@7.29.0_react@18.3.1/node_modules/styled-jsx/readme.md` | EN | README |
| `node_modules/.pnpm/sucrase@3.35.1/node_modules/sucrase/README.md` | EN | README |
| `node_modules/.pnpm/supports-color@7.2.0/node_modules/supports-color/readme.md` | EN | README |
| `node_modules/.pnpm/supports-preserve-symlinks-flag@1.0.0/node_modules/supports-preserve-symlinks-flag/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/supports-preserve-symlinks-flag@1.0.0/node_modules/supports-preserve-symlinks-flag/README.md` | EN | README |
| `node_modules/.pnpm/symbol-tree@3.2.4/node_modules/symbol-tree/README.md` | EN | README |
| `node_modules/.pnpm/tailwind-merge@2.6.1/node_modules/tailwind-merge/LICENSE.md` | EN | other |
| `node_modules/.pnpm/tailwind-merge@2.6.1/node_modules/tailwind-merge/README.md` | EN | README |
| `node_modules/.pnpm/tailwindcss@3.4.19/node_modules/tailwindcss/README.md` | EN | README |
| `node_modules/.pnpm/tailwindcss@3.4.19/node_modules/tailwindcss/lib/postcss-plugins/nesting/README.md` | EN | README |
| `node_modules/.pnpm/tailwindcss@3.4.19/node_modules/tailwindcss/lib/value-parser/README.md` | EN | README |
| `node_modules/.pnpm/tailwindcss@3.4.19/node_modules/tailwindcss/src/postcss-plugins/nesting/README.md` | EN | README |
| `node_modules/.pnpm/tailwindcss@3.4.19/node_modules/tailwindcss/src/value-parser/README.md` | EN | README |
| `node_modules/.pnpm/test-exclude@7.0.2/node_modules/test-exclude/README.md` | EN | README |
| `node_modules/.pnpm/thenify-all@1.6.0/node_modules/thenify-all/History.md` | EN | other |
| `node_modules/.pnpm/thenify-all@1.6.0/node_modules/thenify-all/README.md` | EN | README |
| `node_modules/.pnpm/thenify@3.3.1/node_modules/thenify/History.md` | EN | other |
| `node_modules/.pnpm/thenify@3.3.1/node_modules/thenify/README.md` | EN | README |
| `node_modules/.pnpm/tinybench@2.9.0/node_modules/tinybench/README.md` | EN | README |
| `node_modules/.pnpm/tinyexec@0.3.2/node_modules/tinyexec/README.md` | EN | README |
| `node_modules/.pnpm/tinyglobby@0.2.15/node_modules/tinyglobby/README.md` | EN | README |
| `node_modules/.pnpm/tinypool@1.1.1/node_modules/tinypool/README.md` | EN | README |
| `node_modules/.pnpm/tinyrainbow@1.2.0/node_modules/tinyrainbow/README.md` | EN | README |
| `node_modules/.pnpm/tinyspy@3.0.2/node_modules/tinyspy/README.md` | EN | README |
| `node_modules/.pnpm/tldts-core@6.1.86/node_modules/tldts-core/README.md` | EN | README |
| `node_modules/.pnpm/tldts@6.1.86/node_modules/tldts/README.md` | EN | README |
| `node_modules/.pnpm/to-regex-range@5.0.1/node_modules/to-regex-range/README.md` | EN | README |
| `node_modules/.pnpm/tough-cookie@5.1.2/node_modules/tough-cookie/README.md` | EN | README |
| `node_modules/.pnpm/tr46@5.1.1/node_modules/tr46/LICENSE.md` | EN | other |
| `node_modules/.pnpm/tr46@5.1.1/node_modules/tr46/README.md` | EN | README |
| `node_modules/.pnpm/ts-api-utils@2.4.0_typescript@5.9.3/node_modules/ts-api-utils/LICENSE.md` | EN | other |
| `node_modules/.pnpm/ts-api-utils@2.4.0_typescript@5.9.3/node_modules/ts-api-utils/README.md` | EN | README |
| `node_modules/.pnpm/ts-interface-checker@0.1.13/node_modules/ts-interface-checker/README.md` | EN | README |
| `node_modules/.pnpm/tsconfig-paths@3.15.0/node_modules/tsconfig-paths/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/tsconfig-paths@3.15.0/node_modules/tsconfig-paths/README.md` | EN | README |
| `node_modules/.pnpm/tslib@2.8.1/node_modules/tslib/README.md` | EN | README |
| `node_modules/.pnpm/tslib@2.8.1/node_modules/tslib/SECURITY.md` | EN | other |
| `node_modules/.pnpm/type-check@0.4.0/node_modules/type-check/README.md` | EN | README |
| `node_modules/.pnpm/type-fest@0.20.2/node_modules/type-fest/readme.md` | EN | README |
| `node_modules/.pnpm/typed-array-buffer@1.0.3/node_modules/typed-array-buffer/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/typed-array-buffer@1.0.3/node_modules/typed-array-buffer/README.md` | EN | README |
| `node_modules/.pnpm/typed-array-byte-length@1.0.3/node_modules/typed-array-byte-length/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/typed-array-byte-length@1.0.3/node_modules/typed-array-byte-length/README.md` | EN | README |
| `node_modules/.pnpm/typed-array-byte-offset@1.0.4/node_modules/typed-array-byte-offset/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/typed-array-byte-offset@1.0.4/node_modules/typed-array-byte-offset/README.md` | EN | README |
| `node_modules/.pnpm/typed-array-length@1.0.7/node_modules/typed-array-length/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/typed-array-length@1.0.7/node_modules/typed-array-length/README.md` | EN | README |
| `node_modules/.pnpm/typescript@5.9.3/node_modules/typescript/README.md` | EN | README |
| `node_modules/.pnpm/typescript@5.9.3/node_modules/typescript/SECURITY.md` | EN | other |
| `node_modules/.pnpm/unbox-primitive@1.1.0/node_modules/unbox-primitive/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/unbox-primitive@1.1.0/node_modules/unbox-primitive/README.md` | EN | README |
| `node_modules/.pnpm/undici-types@6.21.0/node_modules/undici-types/README.md` | EN | README |
| `node_modules/.pnpm/unrs-resolver@1.11.1/node_modules/unrs-resolver/README.md` | EN | README |
| `node_modules/.pnpm/update-browserslist-db@1.2.3_browserslist@4.28.1/node_modules/update-browserslist-db/README.md` | EN | README |
| `node_modules/.pnpm/uri-js@4.4.1/node_modules/uri-js/README.md` | EN | README |
| `node_modules/.pnpm/util-deprecate@1.0.2/node_modules/util-deprecate/History.md` | EN | other |
| `node_modules/.pnpm/util-deprecate@1.0.2/node_modules/util-deprecate/README.md` | EN | README |
| `node_modules/.pnpm/vite-node@2.1.9_@types+node@22.19.11/node_modules/vite-node/README.md` | EN | README |
| `node_modules/.pnpm/vite@5.4.21_@types+node@22.19.11/node_modules/vite/LICENSE.md` | EN | other |
| `node_modules/.pnpm/vite@5.4.21_@types+node@22.19.11/node_modules/vite/README.md` | EN | README |
| `node_modules/.pnpm/vitest-axe@0.1.0_vitest@2.1.9_@types+node@22.19.11_jsdom@25.0.1_/node_modules/vitest-axe/README.md` | EN | README |
| `node_modules/.pnpm/vitest@2.1.9_@types+node@22.19.11_jsdom@25.0.1/node_modules/vitest/LICENSE.md` | EN | other |
| `node_modules/.pnpm/vitest@2.1.9_@types+node@22.19.11_jsdom@25.0.1/node_modules/vitest/README.md` | EN | README |
| `node_modules/.pnpm/w3c-xmlserializer@5.0.0/node_modules/w3c-xmlserializer/LICENSE.md` | EN | other |
| `node_modules/.pnpm/w3c-xmlserializer@5.0.0/node_modules/w3c-xmlserializer/README.md` | EN | README |
| `node_modules/.pnpm/webidl-conversions@7.0.0/node_modules/webidl-conversions/LICENSE.md` | EN | other |
| `node_modules/.pnpm/webidl-conversions@7.0.0/node_modules/webidl-conversions/README.md` | EN | README |
| `node_modules/.pnpm/whatwg-encoding@3.1.1/node_modules/whatwg-encoding/README.md` | EN | README |
| `node_modules/.pnpm/whatwg-mimetype@4.0.0/node_modules/whatwg-mimetype/README.md` | EN | README |
| `node_modules/.pnpm/whatwg-url@14.2.0/node_modules/whatwg-url/README.md` | EN | README |
| `node_modules/.pnpm/which-boxed-primitive@1.1.1/node_modules/which-boxed-primitive/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/which-boxed-primitive@1.1.1/node_modules/which-boxed-primitive/README.md` | EN | README |
| `node_modules/.pnpm/which-builtin-type@1.2.1/node_modules/which-builtin-type/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/which-builtin-type@1.2.1/node_modules/which-builtin-type/README.md` | EN | README |
| `node_modules/.pnpm/which-collection@1.0.2/node_modules/which-collection/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/which-collection@1.0.2/node_modules/which-collection/README.md` | EN | README |
| `node_modules/.pnpm/which-typed-array@1.1.20/node_modules/which-typed-array/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/which-typed-array@1.1.20/node_modules/which-typed-array/README.md` | EN | README |
| `node_modules/.pnpm/which@2.0.2/node_modules/which/CHANGELOG.md` | EN | other |
| `node_modules/.pnpm/which@2.0.2/node_modules/which/README.md` | EN | README |
| `node_modules/.pnpm/why-is-node-running@2.3.0/node_modules/why-is-node-running/README.md` | EN | README |
| `node_modules/.pnpm/word-wrap@1.2.5/node_modules/word-wrap/README.md` | EN | README |
| `node_modules/.pnpm/wrap-ansi@7.0.0/node_modules/wrap-ansi/readme.md` | EN | README |
| `node_modules/.pnpm/wrap-ansi@8.1.0/node_modules/wrap-ansi/readme.md` | EN | README |
| `node_modules/.pnpm/wrappy@1.0.2/node_modules/wrappy/README.md` | EN | README |
| `node_modules/.pnpm/ws@8.19.0/node_modules/ws/README.md` | EN | README |
| `node_modules/.pnpm/xml-name-validator@5.0.0/node_modules/xml-name-validator/README.md` | EN | README |
| `node_modules/.pnpm/xmlchars@2.2.0/node_modules/xmlchars/README.md` | EN | README |
| `node_modules/.pnpm/yallist@3.1.1/node_modules/yallist/README.md` | EN | README |
| `node_modules/.pnpm/yocto-queue@0.1.0/node_modules/yocto-queue/readme.md` | EN | README |
| `packages/types/node_modules/.ignored_typescript/README.md` | EN | README |
| `packages/types/node_modules/.ignored_typescript/SECURITY.md` | EN | other |
| `packages/types/node_modules/.ignored_vitest/LICENSE.md` | EN | other |
| `packages/types/node_modules/.ignored_vitest/README.md` | EN | README |
| `packages/types/node_modules/@esbuild/linux-x64/README.md` | EN | README |
| `packages/types/node_modules/@jridgewell/sourcemap-codec/README.md` | EN | README |
| `packages/types/node_modules/@rollup/rollup-linux-x64-gnu/README.md` | EN | README |
| `packages/types/node_modules/@types/estree/README.md` | EN | README |
| `packages/types/node_modules/@vitest/expect/README.md` | EN | README |
| `packages/types/node_modules/@vitest/mocker/README.md` | EN | README |
| `packages/types/node_modules/@vitest/runner/README.md` | EN | README |
| `packages/types/node_modules/@vitest/snapshot/README.md` | EN | README |
| `packages/types/node_modules/@vitest/spy/README.md` | EN | README |
| `packages/types/node_modules/assertion-error/README.md` | EN | README |
| `packages/types/node_modules/cac/README.md` | EN | README |
| `packages/types/node_modules/chai/README.md` | EN | README |
| `packages/types/node_modules/check-error/README.md` | EN | README |
| `packages/types/node_modules/debug/README.md` | EN | README |
| `packages/types/node_modules/deep-eql/README.md` | EN | README |
| `packages/types/node_modules/es-module-lexer/README.md` | EN | README |
| `packages/types/node_modules/esbuild/LICENSE.md` | EN | other |
| `packages/types/node_modules/esbuild/README.md` | EN | README |
| `packages/types/node_modules/estree-walker/README.md` | EN | README |
| `packages/types/node_modules/expect-type/README.md` | EN | README |
| `packages/types/node_modules/expect-type/SECURITY.md` | EN | other |
| `packages/types/node_modules/loupe/README.md` | EN | README |
| `packages/types/node_modules/magic-string/README.md` | EN | README |
| `packages/types/node_modules/ms/license.md` | EN | other |
| `packages/types/node_modules/ms/readme.md` | EN | README |
| `packages/types/node_modules/nanoid/README.md` | Mixed | README |
| `packages/types/node_modules/pathe/README.md` | EN | README |
| `packages/types/node_modules/pathval/README.md` | EN | README |
| `packages/types/node_modules/picocolors/README.md` | EN | README |
| `packages/types/node_modules/postcss/README.md` | EN | README |
| `packages/types/node_modules/rollup/LICENSE.md` | EN | other |
| `packages/types/node_modules/rollup/README.md` | EN | README |
| `packages/types/node_modules/siginfo/README.md` | EN | README |
| `packages/types/node_modules/source-map-js/README.md` | EN | README |
| `packages/types/node_modules/stackback/README.md` | EN | README |
| `packages/types/node_modules/std-env/README.md` | EN | README |
| `packages/types/node_modules/tinybench/README.md` | EN | README |
| `packages/types/node_modules/tinyexec/README.md` | EN | README |
| `packages/types/node_modules/tinypool/README.md` | EN | README |
| `packages/types/node_modules/tinyrainbow/README.md` | EN | README |
| `packages/types/node_modules/tinyspy/README.md` | EN | README |
| `packages/types/node_modules/vite-node/README.md` | EN | README |
| `packages/types/node_modules/vite/LICENSE.md` | EN | other |
| `packages/types/node_modules/vite/README.md` | EN | README |
| `packages/types/node_modules/why-is-node-running/README.md` | EN | README |
| `security/sbom/README.md` | EN | README |
| `spec/continuation_runtime_overview.md` | EN | other |
| `veritas_os/README.md` | EN | README |
| `veritas_os/README_JP.md` | JA | README |
| `veritas_os/WEEKLY_TASKS.md` | Mixed | other |

## old path → new path の対応表

| old | new |
|---|---|
| `chainlit.md` | `docs/en/notes/chainlit.md` |
| `docs/operations/MEMORY_PICKLE_MIGRATION.md` | `docs/en/operations/memory_pickle_migration.md` |
| `docs/review/CODE_REVIEW_2025.md` | `docs/en/reviews/code_review_2025.md` |
| `docs/review/CODE_REVIEW_REPORT.md` | `docs/en/reviews/code_review_report.md` |
| `FRONTEND_REVIEW.md` | `docs/en/reviews/frontend_review.md` |
| `REPOSITORY_REVIEW.md` | `docs/en/reviews/repository_review.md` |
| `docs/audits/markdown_information_architecture_audit_2026-04-07.md` | `docs/ja/audits/markdown_information_architecture_audit_2026_04_07_ja.md` |
| `docs/replay_audit.md` | `docs/ja/audits/replay_audit_ja.md` |
| `docs/operations/ENTERPRISE_SLO_SLI_RUNBOOK_JP.md` | `docs/ja/operations/enterprise_slo_sli_runbook_ja.md` |
| `docs/review/BACKEND_CORE_PRECISION_REREVIEW_2026_03_02_JP.md` | `docs/ja/reviews/backend_core_precision_rereview_2026_03_02_ja.md` |
| `docs/review/BACKEND_CORE_PRECISION_REVIEW_2026_03_02_JP.md` | `docs/ja/reviews/backend_core_precision_review_2026_03_02_ja.md` |
| `docs/review/CODE_IMPROVEMENT_SUMMARY_JP.md` | `docs/ja/reviews/code_improvement_summary_ja.md` |
| `docs/review/CODE_REVIEW_2026_02_10.md` | `docs/ja/reviews/code_review_2026_02_10_ja.md` |
| `docs/review/CODE_REVIEW_2026_02_11.md` | `docs/ja/reviews/code_review_2026_02_11_ja.md` |
| `docs/review/CODE_REVIEW_2026_02_11_RUNTIME_CHECK.md` | `docs/ja/reviews/code_review_2026_02_11_runtime_check_ja.md` |
| `docs/review/CODE_REVIEW_2026_02_12_AGENT.md` | `docs/ja/reviews/code_review_2026_02_12_agent_ja.md` |
| `docs/review/CODE_REVIEW_2026_02_12.md` | `docs/ja/reviews/code_review_2026_02_12_ja.md` |
| `docs/review/CODE_REVIEW_2026_02_13_AGENT_DETAILED_JP.md` | `docs/ja/reviews/code_review_2026_02_13_agent_detailed_ja.md` |
| `docs/review/CODE_REVIEW_2026_02_13_CORE.md` | `docs/ja/reviews/code_review_2026_02_13_core_ja.md` |
| `docs/review/CODE_REVIEW_2026_02_13_FULL_SCAN_JP.md` | `docs/ja/reviews/code_review_2026_02_13_full_scan_ja.md` |
| `docs/review/CODE_REVIEW_2026_02_14_SPAGHETTI_JP.md` | `docs/ja/reviews/code_review_2026_02_14_spaghetti_ja.md` |
| `docs/review/CODE_REVIEW_2026_02_15_AGENT_JP.md` | `docs/ja/reviews/code_review_2026_02_15_agent_ja.md` |
| `docs/review/CODE_REVIEW_2026_02_16_COMPLETENESS_JP.md` | `docs/ja/reviews/code_review_2026_02_16_completeness_ja.md` |
| `docs/review/CODE_REVIEW_2026_02_27_FULL_JP.md` | `docs/ja/reviews/code_review_2026_02_27_full_ja.md` |
| `docs/review/CODE_REVIEW_2026_03_06_MUST_HAVE_FEATURES_JP.md` | `docs/ja/reviews/code_review_2026_03_06_must_have_features_ja.md` |
| `docs/reviews/CODE_REVIEW_2026_03_21_JP.md` | `docs/ja/reviews/code_review_2026_03_21_ja.md` |
| `docs/code_review_2026_03_23.md` | `docs/ja/reviews/code_review_2026_03_23_ja.md` |
| `docs/code-review-2026-03-24.md` | `docs/ja/reviews/code_review_2026_03_24_ja.md` |
| `docs/reviews/CODE_REVIEW_CONSISTENCY_2026_03_15_JP.md` | `docs/ja/reviews/code_review_consistency_2026_03_15_ja.md` |
| `docs/review/CODE_REVIEW_FATAL_BUG_SCAN_2026_03_02_JP.md` | `docs/ja/reviews/code_review_fatal_bug_scan_2026_03_02_ja.md` |
| `docs/review/CODE_REVIEW_FULL_2026_02_08.md` | `docs/ja/reviews/code_review_full_2026_02_08_ja.md` |
| `docs/review/CODE_REVIEW_FULL_2026_03_04_AGENT_JP.md` | `docs/ja/reviews/code_review_full_2026_03_04_agent_ja.md` |
| `docs/review/CODE_REVIEW_FULL_2026_03_04_JP.md` | `docs/ja/reviews/code_review_full_2026_03_04_ja.md` |
| `docs/review/CODE_REVIEW_FULL_2026_03_05_AGENT2_JP.md` | `docs/ja/reviews/code_review_full_2026_03_05_agent2_ja.md` |
| `docs/review/CODE_REVIEW_FULL_2026_03_05_AGENT_JP.md` | `docs/ja/reviews/code_review_full_2026_03_05_agent_ja.md` |
| `docs/review/CODE_REVIEW_FULL_2026_03_13_JP.md` | `docs/ja/reviews/code_review_full_2026_03_13_ja.md` |
| `docs/review/CODE_REVIEW_FULL_2026_03_14_ALL_CODE_CONSISTENCY_JP.md` | `docs/ja/reviews/code_review_full_2026_03_14_all_code_consistency_ja.md` |
| `docs/review/CODE_REVIEW_FULL_2026_03_14_JP.md` | `docs/ja/reviews/code_review_full_2026_03_14_ja.md` |
| `docs/review/CODE_REVIEW_FULL_2026_03_16_AGENT_JP.md` | `docs/ja/reviews/code_review_full_2026_03_16_agent_ja.md` |
| `docs/review/CODE_REVIEW_FULL.md` | `docs/ja/reviews/code_review_full_ja.md` |
| `docs/reviews/CODE_REVIEW_REASSESSMENT_2026_03_23_JP.md` | `docs/ja/reviews/code_review_reassessment_2026_03_23_ja.md` |
| `docs/review/CODE_REVIEW_REREVIEW_2026_03_18_JP.md` | `docs/ja/reviews/code_review_rereview_2026_03_18_ja.md` |
| `docs/review/CODE_REVIEW_STATUS.md` | `docs/ja/reviews/code_review_status_ja.md` |
| `docs/review/CODEX_IMPROVEMENT_REVIEW_2026_02_24_JP.md` | `docs/ja/reviews/codex_improvement_review_2026_02_24_ja.md` |
| `docs/review/CODEX_IMPROVEMENT_REVIEW_2026_02_25_JP.md` | `docs/ja/reviews/codex_improvement_review_2026_02_25_ja.md` |
| `docs/review/CODEX_IMPROVEMENT_REVIEW_2026_02_26_JP.md` | `docs/ja/reviews/codex_improvement_review_2026_02_26_ja.md` |
| `docs/review/CODEX_START_HERE.md` | `docs/ja/reviews/codex_start_here_ja.md` |
| `docs/review/ENTERPRISE_READINESS_REVIEW_2026_03_06_JP.md` | `docs/ja/reviews/enterprise_readiness_review_2026_03_06_ja.md` |
| `docs/reviews/FRONTEND_BACKEND_CONSISTENCY_REVIEW_2026_03_30_JP.md` | `docs/ja/reviews/frontend_backend_consistency_review_2026_03_30_ja.md` |
| `docs/review/FRONTEND_CODEX_IMPROVEMENT_REREVIEW_2026_02_27_JP.md` | `docs/ja/reviews/frontend_codex_improvement_rereview_2026_02_27_ja.md` |
| `docs/review/FRONTEND_CODEX_IMPROVEMENT_REVIEW_2026_02_26_JP.md` | `docs/ja/reviews/frontend_codex_improvement_review_2026_02_26_ja.md` |
| `docs/review/FRONTEND_PRECISION_REVIEW_2026_02_23_JP.md` | `docs/ja/reviews/frontend_precision_review_2026_02_23_ja.md` |
| `docs/review/FRONTEND_REVIEW_2026_02_23_FOLLOWUP_JP.md` | `docs/ja/reviews/frontend_review_2026_02_23_followup_ja.md` |
| `frontend/FRONTEND_REVIEW.md` | `docs/ja/reviews/frontend_review_ja.md` |
| `docs/reviews/full_code_review_20260327.md` | `docs/ja/reviews/full_code_review_20260327_ja.md` |
| `docs/reviews/improvement_instructions_ja_20260320.md` | `docs/ja/reviews/improvement_instructions_ja_20260320.md` |
| `LARGE_FILE_REVIEW.md` | `docs/ja/reviews/large_file_review_ja.md` |
| `docs/review/pipeline_py_precision_review_2026-03-11.md` | `docs/ja/reviews/pipeline_py_precision_review_2026_03_11_ja.md` |
| `docs/reviews/POLICY_AS_CODE_IMPLEMENTATION_REVIEW_2026-04-02.md` | `docs/ja/reviews/policy_as_code_implementation_review_2026_04_02_ja.md` |
| `docs/reviews/precision_code_review_ja_20260319.md` | `docs/ja/reviews/precision_code_review_ja_20260319.md` |
| `docs/reviews/precision_code_review_ja_20260319_reassessment.md` | `docs/ja/reviews/precision_code_review_ja_20260319_reassessment.md` |
| `docs/review/README.md` | `docs/ja/reviews/readme_ja.md` |
| `docs/reviews/README.md` | `docs/ja/reviews/readme_ja_2.md` |
| `docs/review/README_REVIEW_2026_03_02_JP.md` | `docs/ja/reviews/readme_review_2026_03_02_ja.md` |
| `REVIEW_CURRENT_IMPROVEMENTS_2026-03-30.md` | `docs/ja/reviews/review_current_improvements_2026_03_30_ja.md` |
| `docs/review-frontend-backend-consistency.md` | `docs/ja/reviews/review_frontend_backend_consistency_ja.md` |
| `docs/review/SCHEMA_REVIEW_2026_02_23.md` | `docs/ja/reviews/schema_review_2026_02_23_ja.md` |
| `docs/review/SECURITY_AUDIT_2026_03_12.md` | `docs/ja/reviews/security_audit_2026_03_12_ja.md` |
| `docs/reviews/system_improvement_review_ja_20260327.md` | `docs/ja/reviews/system_improvement_review_ja_20260327.md` |
| `docs/system_review_2026-03-26.md` | `docs/ja/reviews/system_review_2026_03_26_ja.md` |
| `docs/review/SYSTEM_SCORECARD_2026_03_02.md` | `docs/ja/reviews/system_scorecard_2026_03_02_ja.md` |
| `docs/reviews/technical_dd_review_ja_20260314.md` | `docs/ja/reviews/technical_dd_review_ja_20260314.md` |
| `docs/reviews/technical_dd_review_ja_20260315.md` | `docs/ja/reviews/technical_dd_review_ja_20260315.md` |
| `docs/reviews/THREAT_MODEL_STRIDE_LINDDUN_20260314.md` | `docs/ja/reviews/threat_model_stride_linddun_20260314_ja.md` |

## 命名規則の決定内容
- 英語: `docs/en/**` 配下で `lowercase_snake_case.md` を採用。
- 日本語: `docs/ja/**` 配下で `lowercase_snake_case_ja.md` を基本採用。
- 既存の `README.md` / `README_JP.md` は互換性維持のため維持。

## 変更しなかったファイルと理由
- ルートの `README.md`, `README_JP.md`, `CONTRIBUTING.md`, `SECURITY.md` は入口/ポリシー文書のため維持。
- `docs/notes` 内の既存ノート群は内容改変を避け、今回は構造変更を優先。

## mixed-language 文書の扱い
- 内容保全を優先し、今回は原文を移動・改名のみ実施。
- 分離翻訳は未実施。対応表で「JA側（Mixed含む）」として管理。

## 対応翻訳が存在しない文書一覧
- `docs/en/reviews/*`: 多くが英語のみ。
- `docs/ja/reviews/*`: 多くが日本語/混在のみ。
- 正式な1:1翻訳ペアは `README.md` ↔ `README_JP.md`、`veritas_os/README.md` ↔ `veritas_os/README_JP.md` を確認。

## 今後の推奨運用ルール
1. 新規レビューは `docs/en/reviews` または `docs/ja/reviews` のみへ追加。
2. Mixed-language 新規作成を禁止し、必要時は EN/JA 別ファイルで同時作成。
3. 追加時は `docs/DOCUMENTATION_MAP.md` と各言語 README の索引を更新。
4. 大規模移行時は `git mv` とリンクチェックをセットで実施。