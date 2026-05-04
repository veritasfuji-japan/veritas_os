# PRリスクラベル運用ガイド

## 目的

この文書は、VERITAS OS の開発における推奨PRリスクラベルを定義します。

以下の監査可能なAI支援開発ワークフローを補完します。

- `docs/ja/development/ai-assisted-development.md`
- `docs/ja/development/ai-review-matrix.md`

リスクラベルはトリアージ補助です。CI、レビュー、人間メンテナの承認を置き換えるものではありません。

## 権限モデル

- AIレビューは参考シグナルです。
- GitHub Actions / CI は客観的チェックです。
- 人間メンテナの承認が最終的な Commit Boundary です。
- リスクラベルはマージを許可するものではありません。
- リスクラベルは、セキュリティ、ガバナンス、リリース、公開主張に関するレビュー要件を下げるものではありません。

## 推奨ラベル

| ラベル | 意味 | 典型例 | 人間承認 |
|---|---|---|---|
| `risk:low` | 小さく影響が低い変更 | typo修正、docs-onlyの補足、非公開表現の軽微な整理 | 通常レビュー |
| `risk:medium` | 影響範囲が限定された意味のある変更 | 焦点を絞ったruntime修正、テスト更新、局所的なfrontend挙動、非機密docs整理 | メンテナレビュー必須 |
| `risk:high` | ガバナンス、セキュリティ、リリース、公開主張に影響し得る変更 | bind/admissibility挙動、FUJI Gate挙動、TrustLog永続化、release gates、公開主張 | 明示的な人間承認必須 |
| `docs-only` | ドキュメントのみの変更 | docsページ、ガイド、レビューマトリクス、解説ページ | 公開主張変更がなければ通常レビュー |
| `tests-only` | テストのみの変更 | unit test coverage、fixture update、regression test | 期待値変更がある場合はメンテナレビュー必須 |
| `runtime-change` | runtime挙動が変わる可能性がある変更 | backend logic、frontend behavior、API response behavior | メンテナレビュー必須 |
| `governance-sensitive` | ガバナンス挙動またはポリシー境界に影響し得る変更 | policy behavior、bind/admissibility logic、approval flow、enforcement behavior | 明示的な人間承認必須 |
| `security-sensitive` | セキュリティ姿勢に影響し得る変更 | secrets handling、auth、RBAC、encryption、PII masking、CORS、deserialization | 明示的な人間承認必須 |
| `release-gate-change` | リリースまたはCIゲートに影響し得る変更 | GitHub Actions、quality gate scripts、release workflow、coverage gate | 明示的な人間承認必須 |
| `public-claim-change` | 公開表現・外部向け主張に影響し得る変更 | README、README_JP、website文言、投資家/顧客向けdocs、SNS投稿元テキスト | 明示的な人間承認必須 |
| `needs-human-approval` | マージ前に明示的な人間承認が必要 | 高リスクまたは権限に関わる変更 | 明示的な人間承認必須 |
| `ai-assisted` | AIツールが計画、実装、レビュー、ドラフトに関与 | ChatGPT計画、Codex実装、Claude Codeレビュー、外部AI参考レビュー | 承認ルールは変わらない |

## リスク分類ルール

該当する中で最も高いリスクレベルを使います。

以下に触れるPRは `risk:high` です。

- bind/admissibility logic
- governance policy behavior
- FUJI Gate fail-closed behavior
- TrustLog persistence or encryption behavior
- release gates
- secrets or credential handling
- public claims
- website positioning
- private user/customer data handling

docs-only PR でも、公開主張、規制対応の見せ方、本番準備性の記述、外部レビュー証跡の主張を変更する場合は `risk:high` になり得ます。

tests-only PR でも、期待挙動、カバレッジ、assertion、governance/release gate の前提を弱める場合は `risk:medium` または `risk:high` になり得ます。

## 推奨レビュー経路

| リスク | 推奨レビュー |
|---|---|
| `risk:low` | 通常のメンテナレビュー |
| `risk:medium` | メンテナレビュー + 関連するAI参考レビュー |
| `risk:high` | 明示的な人間承認 + CI成功 + アーキテクチャ/セキュリティ/ガバナンス観点の targeted review |

## AIレビューの使い方

AIツールはラベル候補を提案できますが、最終ラベルは人間が決定します。

Codex は実装中に想定リスクカテゴリを示すことができます。
Claude Code は、付与ラベルが差分内容と一致しているかレビューできます。
外部AIツールは、非機密の抜粋に限って参考意見を提供できます。

## 非目的

この文書は以下を導入しません。

- 自動ラベル付け
- 自動マージ承認
- 自動リリース承認
- CIの迂回
- 人間メンテナ判断の置き換え

## 最小PRラベル例

docs-only typo修正:

- `risk:low`
- `docs-only`

bind/admissibility挙動変更:

- `risk:high`
- `runtime-change`
- `governance-sensitive`
- `needs-human-approval`

README positioning update:

- `risk:high`
- `docs-only`
- `public-claim-change`
- `needs-human-approval`
