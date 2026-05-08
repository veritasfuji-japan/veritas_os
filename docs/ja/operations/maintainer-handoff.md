# Maintainer Handoff and Support Continuity Runbook

> 英語版（`docs/en/operations/maintainer-handoff.md`）が正本です。日本語版は補助説明です。

## 1. 目的

この文書は、VERITAS OS の保守引き継ぎ時に必要な最小限の運用知識を明文化し、属人化による引き継ぎ摩擦を下げることを目的とします。

## 2. この文書で解決できること / できないこと

解決できること:

- 新しい maintainer が最初に参照すべき資料の明確化
- ローカルセットアップと品質ゲートの確認手順
- PR レビュー、リリース前確認、PoC 提出確認の観点
- インシデント初動と責任境界の整理

解決できないこと:

- バスファクターリスクを完全に解消するものではありません。
- 人員体制そのものを補うものではありません。
- 24/7 support または正式なSLAを意味しない補助文書です。
- 法務・規制・認証の保証を提供するものではありません。

## 3. 新しい maintainer の最初の60分

最初に読む:

- `README.md`
- `docs/en/operations/provider-support-matrix.md`
- `docs/en/operations/type-safety-baseline.md`
- `docs/en/poc/one-day-poc-reviewer-pack.md`
- `docs/en/poc/one-day-poc-performance-report.md`

次に実行:

    python -m pytest -q veritas_os/tests/test_one_day_poc_smoke.py
    python -m pytest -q veritas_os/tests/test_one_day_poc_benchmark.py
    python -m scripts.quality.check_type_baseline
    python -m scripts.quality.check_bilingual_docs

状態確認:

- オープン PR / Issue のうち、セキュリティ・リリース影響の高いものを把握
- 秘密情報や API key の混入がないことを確認
- `main` の CI 必須チェックがグリーンであることを確認

## 4. 品質ゲート

最低限確認するゲート:

- CI（main workflow）
- Security Gates
- CodeQL custom
- Runtime Pickle Guard
- requirements sync
- bilingual docs check
- one-day PoC smoke tests
- one-day PoC benchmark tests
- provider support matrix docs test
- compliance positioning docs test
- type safety baseline test

補足: これらに合格しても、本番運用適格性・法的適合性・セキュリティ認証・SLA準備完了を保証するものではありません。

## 5. PRレビュー観点

- runtime governance semantics を変更していないか
- bind / RBAC / TrustLog の挙動を変更していないか
- evidence packet shape を変更していないか
- benchmark packet shape を変更していないか
- provider tier を変更していないか
- compliance claim を過度に強化していないか
- runtime dependency を追加していないか
- secrets を露出していないか
- EN/JA ドキュメント同期が必要か
- One-Day PoC reviewer pack の更新が必要か
- CI ゲート前提を壊していないか

## 6. リリース前確認

- `main` の CI がグリーン
- 必要時に release gate がグリーン
- 変更内容に対応する docs 更新が反映済み
- provider support matrix / compliance positioning が最新
- benchmark 導線が実行可能
- 未レビューの provider tier 変更がない
- 法務・規制保証の過剰主張がない
- runtime dependency 追加に正当化がある
- secret handling / logging 退行がない

## 7. PoC提出確認

- reviewer pack
- evidence JSON
- evidence Markdown
- benchmark JSON
- benchmark Markdown
- provider support matrix 参照
- EU AI Act positioning 参照
- type safety baseline 参照
- known limitations 明記

## 8. secret handling

- API key をコミットしない
- secret を Issue / PR / docs / benchmark へ生で貼らない
- secret を含みうる raw request/response を安易に共有しない
- reviewer 向け成果物は sanitize された出力のみ使う
- customer data は機密として扱う
- evidence packet は secret-safe を維持する

## 9. incident triage

初動では以下に限定:

- failing gate / failing path の特定
- failing run へのリンク
- 対象コマンドで再現
- runtime 変更か docs/tooling 変更か切り分け
- incident fix で広範囲リファクタをしない
- PR に root cause と mitigation を記録

対象インシデント例:

- CI failure
- security gate failure
- evidence validation failure
- benchmark failure
- provider failure
- TrustLog / RBAC / bind behavior regression
- docs compliance claim regression

## 10. subsystem map

| Area | Primary docs/tests | Maintainer concern |
|---|---|---|
| Bind / admissibility | `docs/en/architecture/bind_time_admissibility_evaluator.md`, `docs/en/architecture/bind-boundary-governance-artifacts.md` | fail-closed を弱めない。 |
| RBAC | `docs/en/architecture/decision-semantics.md`, `veritas_os/tests/test_role_guard_escalation.py` | denial visibility と escalation 境界を維持。 |
| TrustLog | `docs/en/architecture/authority-evidence-vs-audit-log.md`, `veritas_os/tests/test_audit_log_writer.py` | append/audit semantics を維持。 |
| Evidence packets | `docs/en/poc/one-day-poc-reviewer-pack.md`, `veritas_os/tests/test_docs_poc_samples.py` | schema shape と sanitize 保証を維持。 |
| Provider support | `docs/en/operations/provider-support-matrix.md`, `veritas_os/tests/test_provider_support_matrix_docs.py` | 非本番 provider の過剰主張をしない。 |
| Compliance positioning | `docs/en/positioning/public-positioning.md`, `veritas_os/tests/test_compliance_positioning_docs.py` | legal certification を主張しない。 |
| Type safety | `docs/en/operations/type-safety-baseline.md`, `veritas_os/tests/test_type_safety_baseline.py` | baseline は段階的運用であり、全域 strict typing ではない。 |

## 11. 既知の継続性リスク

- 単一 primary maintainer リスクは残存
- staffed support organization は未整備
- formal support SLA は未提供
- 一部運用知識は暗黙知のまま残る可能性
- 法務/セキュリティの第三者レビューはリポジトリ外の責務
- 本番デプロイ責任は customer/operator 側

## 12. 今後の roadmap

- maintainer onboarding issue template を追加
- release manager checklist template を追加
- incident report template を追加
- type baseline の core modules カバレッジを拡張
- provider contract tests を段階的に追加
- major subsystems の ADR を整備
- dev/full/runtime dependency profile 分離を整備
- 実体あるサポート体制が存在する場合のみ SLA を定義
