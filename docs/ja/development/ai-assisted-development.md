# AI支援開発ガードレール

## 目的

VERITAS OS では、実装、レビュー、ドキュメント整理、リリース準備を加速するために複数のAIツールを利用することがあります。

この文書は、AI支援開発を監査可能な形で運用するためのガードレールを定義します。

これは完全自動開発、自動マージ、人間メンテナの置き換えを意味しません。

## 基本原則

AIツールは、変更の提案、実装、レビュー、要約を行うことができます。

ただし、以下の承認は人間メンテナが行います。

- セキュリティ上重要な変更
- ガバナンス境界に関わる変更
- リリース判断
- 公開表現・公開主張
- 非公開のユーザー情報または顧客情報に関わる変更

## 権限モデル

- AIレビューは参考シグナルです。
- GitHub Actions / CI は客観的チェックです。
- 人間メンテナの承認が最終的な Commit Boundary です。

## ツールごとの役割

| ツール | 主な役割 |
|---|---|
| ChatGPT | PR目的、スコープ、リスク整理、設計判断、市場価値レビュー |
| Codex | 主実装、焦点を絞ったPR修正、テスト更新、CI失敗修正 |
| Claude Code | アーキテクチャレビュー、エッジケース確認、実装補助、用語一貫性レビュー |
| GitHub Copilot | GitHub上のPRレビュー、ローカル実装補助、小さなバグ指摘 |
| Gemini | 外部視点での明瞭性レビュー、ドキュメント可読性、プロダクト説明レビュー |
| Grok | 辛口レビュー、不要な複雑性の検出、市場・メッセージ面の違和感検出 |
| Meta AI | 軽量な二次レビュー、用語の明瞭性、読みやすさ確認 |
| GitHub Actions | CI、テスト、品質ゲート、リリースゲート |
| 人間メンテナ | 最終承認、マージ判断、セキュリティ・ガバナンス・リリース・公開表現の権限 |

## 推奨ワークフロー

1. ChatGPT が PR の目的、スコープ、リスク、非目的を整理する。
2. Codex が焦点を絞った変更を実装する。
3. Claude Code がアーキテクチャ、エッジケース、用語、整合性をレビューする。
4. GitHub Actions がテストと品質ゲートを検証する。
5. 外部AIツールは、非機密の抜粋に限って参考レビューを行う。
6. 人間メンテナが承認、却下、または修正依頼を行う。

## 自動化してはいけないもの

AIは以下を自動マージまたは単独承認してはいけません。

- bind/admissibility logic の変更
- governance policy の変更
- release gate の変更
- secret handling の変更
- TrustLog の永続化または暗号化挙動の変更
- FUJI Gate の fail-closed 挙動の変更
- 公開主張の変更
- website positioning の変更
- 非公開のユーザー情報または顧客情報に関わる変更

## 外部AIレビューの安全ルール

外部AIまたは無料版AIレビューには、非機密の抜粋のみを使います。

貼り付けてはいけないもの:

- secrets
- credentials
- API keys
- `.env` content
- private customer data
- unpublished internal strategy
- non-public security details

使ってよいもの:

- 公開ドキュメント
- サニタイズ済みdiff
- 限定されたファイル抜粋
- 秘密情報を含まないエラーメッセージ
- 抽象化した設計相談

外部AIのフィードバックは、それ単独では merge blocker になりません。

## レビュー優先度

1. CI/test failures
2. Security or data exposure
3. Runtime behavior mismatch
4. Public documentation mismatch
5. Missing tests for code changes
6. Refactor or style suggestions

## 非目的

この文書は以下を導入しません。

- 完全自動開発
- 自動PR承認
- 自動マージ
- 人間メンテナの置き換え
- runtime governance behavior の変更
- CI/release gates の変更

## VERITAS開発ステートメント

VERITAS OS は、監査可能なAI支援ワークフローによって開発されます。

- Codex は実装を支援できる。
- Claude Code はレビューを支援できる。
- GitHub Actions は検証する。
- 外部モデルは参考レビューを提供できる。
- 人間メンテナの承認が最終的な Commit Boundary である。
