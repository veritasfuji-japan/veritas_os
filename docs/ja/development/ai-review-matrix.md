# AIレビューマトリクス

## 目的

この文書は、VERITAS OS の開発において複数のAIツールをどの役割で使うかを定義します。

`docs/ja/development/ai-assisted-development.md` で定義した、監査可能なAI支援開発ワークフローを補完する文書です。

AIレビューは参考シグナルです。GitHub Actions / CI は客観的チェックです。人間メンテナの承認が最終的な Commit Boundary です。

## 役割マトリクス

| ツール | 主な役割 | 向いている用途 | 権限を持たないもの |
|---|---|---|---|
| ChatGPT | 計画・戦略レビュー | PR目的、スコープ、リスク整理、市場/開発者/ユーザー価値、公開メッセージ確認 | マージ承認、CI上書き、セキュリティ/ガバナンス承認 |
| Codex | 主実装 | 焦点を絞った修正、テスト、CI失敗修正、小さなdocs更新 | 単独マージ、セキュリティ重要変更の承認、公開主張の承認 |
| Claude Code | アーキテクチャ・実装レビュー | 構造整合、エッジケース、用語一貫性、不足テスト、ガバナンス重要変更の確認 | CI上書き、最終承認、自律的な大規模リファクタ承認 |
| GitHub Copilot | GitHub上のレビュー・ローカル補助 | 小さなバグ指摘、可読性、ローカル実装補助 | 最終承認、ガバナンス/セキュリティ承認 |
| Gemini | 外部視点での明瞭性レビュー | ドキュメント可読性、プロダクト説明、外部レビュアー視点 | merge blocker、機密情報レビュー |
| Grok | 辛口レビュー | 不要な複雑性の検出、市場/メッセージ面の違和感、過剰設計検出 | 最終アーキテクチャ権限 |
| Meta AI | 軽量な二次レビュー | 用語の明瞭性、読みやすさ、セカンドオピニオン | merge blocker、機密レビュー |
| GitHub Actions | 客観的検証 | テスト、品質ゲート、リリースゲート、CodeQL、自動チェック | プロダクト戦略や公開メッセージ判断 |
| 人間メンテナ | 最終権限 | 最終承認、マージ判断、セキュリティ/ガバナンス/リリース/公開主張の承認 | なし |

## フィードバック分類

AIのフィードバックは以下に分類します。

- `blocker`: マージ前に対応が必要
- `recommended`: 明確な理由がない限り対応すべき
- `optional`: スタイル、可読性、代替実装、非重大な提案

AIの参考意見を merge blocker にするかどうかは、人間メンテナが判断します。

## レビュー優先度

1. CI/test failures
2. Security or data exposure
3. Runtime behavior mismatch
4. Public documentation mismatch
5. Missing tests for code changes
6. Refactor or style suggestions

## 高リスク変更

以下の変更には明示的な人間承認が必要です。

- bind/admissibility logic
- governance policy behavior
- release gates
- secrets or credential handling
- TrustLog persistence or encryption behavior
- FUJI Gate fail-closed behavior
- README、docs、website、SNS投稿における公開主張
- 非公開のユーザー情報または顧客情報の取り扱い

## 外部AIレビューの安全ルール

外部AIまたは無料版AIツールには、非機密の抜粋のみを渡します。

secrets、credentials、API keys、`.env` content、private customer data、unpublished internal strategy、non-public security details を貼り付けてはいけません。
