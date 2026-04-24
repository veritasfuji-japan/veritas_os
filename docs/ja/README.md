# ドキュメント（日本語）

VERITAS OS の日本語ドキュメント入口です。日本語で概要を把握し、必要に応じて各ページから英語正本へ遷移できる構成にしています。

- 総合インデックス: [../INDEX.md](../INDEX.md)
- ドキュメント対応表: [../DOCUMENTATION_MAP.md](../DOCUMENTATION_MAP.md)
- 英語ハブ: [../en/README.md](../en/README.md)

## はじめに
- [README_JP（日本語エントリポイント）](../../README_JP.md)
- [README（英語正本）](../../README.md)

## クイックスタート
- [AML/KYC PoC クイックスタート](guides/aml-kyc-poc-quickstart.md)
- [金融PoCパック（既存ガイド）](guides/poc-pack-financial-quickstart.md)
- 英語正本: [docs/en/guides/poc-pack-financial-quickstart.md](../en/guides/poc-pack-financial-quickstart.md)

## VERITASの基本概念
- [Decision Semantics（意思決定セマンティクス）](architecture/decision-semantics.md)
- [公開ポジショニング](positioning/public-positioning.md)

## Decision Governance
- [Decision Semantics（意思決定セマンティクス）](architecture/decision-semantics.md)
- [Required Evidence Taxonomy](governance/required-evidence-taxonomy.md)

## Bind-Boundary Control
- [Bind-Boundary Governance Artifacts](architecture/bind-boundary-governance-artifacts.md)
- [Bind-Time Admissibility Evaluator](architecture/bind_time_admissibility_evaluator.md)

## FUJI Gate
- [FUJI エラーコードリファレンス](guides/fuji-error-codes.md)
- [FUJI EU Strict Pack 使い方](guides/fuji-eu-enterprise-strict-usage.md)

## TrustLog
- [外部監査準備性](validation/external-audit-readiness.md)
- 英語正本: [TrustLog Observability](../en/operations/trustlog_observability.md)

## Mission Control
- [運用者デモフロー](guides/operator-playbook-demo-flow.md)
- 英語正本: [UI Docs](../ui/README_UI.md)

## Replay
- [リプレイ監査](audits/replay_audit_ja.md)
- 英語正本: [Implemented vs Pending Boundary](../en/validation/implemented-vs-pending-boundary.md)

## ガバナンス設定
- [ポリシーバンドル昇格ガイド](guides/governance-policy-bundle-promotion.md)
- [ガバナンス成果物署名運用](operations/governance-artifact-signing.md)

## 監査・外部レビュー
- [外部監査準備性](validation/external-audit-readiness.md)
- [第三者レビュー準備性](validation/third-party-review-readiness.md)

## 技術証明・検証
- [技術証明パック](validation/technical-proof-pack.md)
- [バックエンド・パリティ検証](validation/backend-parity-coverage.md)
- [本番検証](validation/production-validation.md)

## 運用・本番準備
- [PostgreSQL 本番運用ガイド](operations/postgresql-production-guide.md)
- [PostgreSQL ドリル Runbook](operations/postgresql-drill-runbook.md)
- [セキュリティハードニング](operations/security-hardening.md)

## PostgreSQL / Database
- [データベースマイグレーション](operations/database-migrations.md)
- [PostgreSQL 本番運用ガイド](operations/postgresql-production-guide.md)

## Security Hardening
- [セキュリティハードニング](operations/security-hardening.md)
- [ランタイムデータポリシー](operations/runtime-data-policy.md)

## 金融 / AML-KYC PoC
- [金融ガバナンステンプレート](guides/financial-governance-templates.md)
- [AML/KYC Beachhead ショートポジショニング](positioning/aml-kyc-beachhead-short-positioning.md)
- [Evidence Handoff テンプレート](guides/evidence-handoff-audit-pack-template.md)

## UI / Frontend / Mission Control
- [運用者デモフロー](guides/operator-playbook-demo-flow.md)
- 英語正本: [UI Architecture](../ui/architecture.md)

## 英語正本との関係
- 日本語ページは説明レイヤです。仕様差分がある場合は英語正本を優先してください。
- 各日本語ページ末尾の「英語正本」節に canonical ドキュメントを明記しています。

## ドキュメント対応表
- [docs/DOCUMENTATION_MAP.md](../DOCUMENTATION_MAP.md)
