# Documentation Map (Bilingual Structure)

## Entrypoints

- Universal Index: [docs/INDEX.md](INDEX.md)
- English Hub: [docs/en/README.md](en/README.md)
- Japanese Hub: [docs/ja/README.md](ja/README.md)

## Bilingual Correspondence Table

| Area | English Canonical | Japanese Page | Status | Notes |
|---|---|---|---|---|
| Public overview | `README.md` | `README_JP.md` | EN/JA fully paired | 公開導線は双方維持 |
| Documentation hub | `docs/en/README.md` | `docs/ja/README.md` | EN/JA fully paired | JA-first 導線を強化 |
| Architecture: Decision Semantics | `docs/en/architecture/decision-semantics.md` | `docs/ja/architecture/decision-semantics.md` | JA explanation / EN canonical | 仕様判断は EN |
| Architecture: Bind artifacts | `docs/en/architecture/bind-boundary-governance-artifacts.md` | `docs/ja/architecture/bind-boundary-governance-artifacts.md` | JA explanation / EN canonical | bind成果物解説 |
| Architecture: Bind admissibility | `docs/en/architecture/bind_time_admissibility_evaluator.md` | `docs/ja/architecture/bind_time_admissibility_evaluator.md` | JA explanation / EN canonical | 互換リンクあり |
| Architecture: Regulated action governance kernel | `docs/en/architecture/regulated-action-governance-kernel.md` | — | EN canonical only | Regulated action governance primitives |
| Architecture: Authority evidence vs audit log | `docs/en/architecture/authority-evidence-vs-audit-log.md` | — | EN canonical only | 役割分離の明確化 |
| Use case: AML/KYC regulated action path | `docs/en/use-cases/aml-kyc-regulated-action-path.md` | — | EN canonical only | 決定論fixture実行手順 |
| Validation: Regulated action governance proof pack | `docs/en/validation/regulated-action-governance-proof-pack.md` | — | EN canonical only | レビュー証跡パック |
| Validation: External audit readiness | `docs/en/validation/external-audit-readiness.md` | `docs/ja/validation/external-audit-readiness.md` | JA explanation / EN canonical | 外部監査準備性 |
| Validation: Technical proof pack | `docs/en/validation/technical-proof-pack.md` | `docs/ja/validation/technical-proof-pack.md` | JA explanation / EN canonical | DD/監査前の提出導線 |
| Validation: Third-party review readiness | `docs/en/validation/third-party-review-readiness.md` | `docs/ja/validation/third-party-review-readiness.md` | JA explanation / EN canonical | 省略版レビュー入口 |
| Validation: Backend parity coverage | `docs/en/validation/backend-parity-coverage.md` | `docs/ja/validation/backend-parity-coverage.md` | JA explanation / EN canonical | バックエンド差分確認 |
| Validation: Production validation | `docs/en/validation/production-validation.md` | `docs/ja/validation/production-validation.md` | JA explanation / EN canonical | 本番検証導線 |
| Validation: PostgreSQL proof map | `docs/en/validation/postgresql-production-proof-map.md` | `docs/ja/validation/postgresql-production-proof-map.md` | JA explanation / EN canonical | 本番証跡索引 |
| Validation: Bilingual docs quality gate | — | `docs/ja/validation/bilingual-docs-quality-gate.md` | JA primary | 日本語ファースト導線と英日整合性チェックの実行確認 |
| Operations: PostgreSQL production | `docs/en/operations/postgresql-production-guide.md` | `docs/ja/operations/postgresql-production-guide.md` | JA explanation / EN canonical | PostgreSQL本番運用 |
| Operations: PostgreSQL drill | `docs/en/operations/postgresql-drill-runbook.md` | `docs/ja/operations/postgresql-drill-runbook.md` | JA explanation / EN canonical | 復旧ドリル |
| Operations: Security hardening | `docs/en/operations/security-hardening.md` | `docs/ja/operations/security-hardening.md` | JA explanation / EN canonical | ハードニング観点 |
| Operations: Database migrations | `docs/en/operations/database-migrations.md` | `docs/ja/operations/database-migrations.md` | JA explanation / EN canonical | 移行手順 |
| Operations: Governance artifact signing | `docs/en/operations/governance-artifact-signing.md` | `docs/ja/operations/governance-artifact-signing.md` | JA explanation / EN canonical | 署名運用 |
| Operations: Legacy path cleanup | `docs/en/operations/legacy-path-cleanup.md` | `docs/ja/operations/legacy-path-cleanup.md` | JA explanation / EN canonical | 旧経路整理 |
| Governance: Required evidence taxonomy | `docs/en/governance/required-evidence-taxonomy.md` | `docs/ja/governance/required-evidence-taxonomy.md` | JA explanation / EN canonical | taxonomy語彙 |
| Governance: Artifact lifecycle | `docs/en/governance/governance-artifact-lifecycle.md` | `docs/ja/governance/governance-artifact-lifecycle.md` | JA explanation / EN canonical | lifecycle管理 |
| Guides: Financial templates | `docs/en/guides/financial-governance-templates.md` | `docs/ja/guides/financial-governance-templates.md` | JA explanation / EN canonical | AML/KYC導線 |
| Guides: Bundle promotion | `docs/en/guides/governance-policy-bundle-promotion.md` | `docs/ja/guides/governance-policy-bundle-promotion.md` | JA explanation / EN canonical | ポリシーバンドル昇格 |
| Guides: PoC quickstart | `docs/en/guides/poc-pack-financial-quickstart.md` | `docs/ja/guides/poc-pack-financial-quickstart.md` | EN/JA fully paired | JAファースト導線 |
| Positioning: AML/KYC | `docs/en/positioning/aml-kyc-beachhead-short-positioning.md` | `docs/ja/positioning/aml-kyc-beachhead-short-positioning.md` | JA explanation / EN canonical | 公開向け短縮版 |
| Positioning: Public positioning | `docs/en/positioning/public-positioning.md` | `docs/ja/positioning/public-positioning.md` | JA explanation / EN canonical | 内部再評価含む |
| UI docs | `docs/ui/README_UI.md` | `docs/ui/PREVIEW_PAGES_JP.md` | Mixed | UI本体は EN、プレビュー案内は JA |
| Reviews | `docs/en/reviews/` | `docs/ja/reviews/` | Mixed | JAはレビュー蓄積多め |
| Benchmarks | `docs/benchmarks/VERITAS_EVIDENCE_BENCHMARK_PLAN.md` | `docs/ja/validation/technical-proof-pack.md` | JA explanation / EN canonical | ベンチ証跡案内 |
| JA manuals | — | `docs/ja/guides/user-manual.md` | JA primary | 日本語中心運用文書 |
| EN notes | `docs/en/notes/chainlit.md` | — | EN canonical only | 補助ノート |
