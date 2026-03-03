# Frontend Review (2026-03-03)

## スコープ

- Next.js App Router 構成、API プロキシ、CSP/セキュリティヘッダ、主要 UI（Dashboard / Console / Live Event Stream）を対象にレビュー。
- 既存実装の責務（Planner / Kernel / Fuji / MemoryOS）を越える提案は除外し、フロントエンド層に限定。

## 総評

- UI とテストの整備度は高く、`vitest` も現時点で全件パス。
- 一方で、**CSP の強度**と**エラー情報の露出**に改善余地がある。
- いずれも大規模改修なしで段階的に改善可能。

## 主要な指摘事項

### 1) [High] 実効 CSP が `unsafe-inline` を許可している

- 現在の実効 CSP は `script-src 'unsafe-inline'` を含むため、XSS 耐性が低下。
- `Report-Only` 側では nonce ベースが定義済みで、移行の下地はある。
- 推奨:
  1. まず `Content-Security-Policy-Report-Only` の violation を収集。
  2. インラインスクリプト依存を段階的に削減。
  3. 実効 CSP を nonce/strict ベースへ移行。

### 2) [Medium] API エラーボディをそのまま UI 表示している

- `HTTP ${status}: ${bodyText}` をそのままチャットに表示しており、上流 API の内部情報（実装断片・環境情報）を露出する可能性。
- 推奨:
  - ユーザ向けには定型メッセージを表示。
  - 詳細は Sentry / server log 側に限定。

### 3) [Low] 文字列ローカライズの漏れが一部に残る

- `Clear events` や `message` など一部文言が i18n ヘルパー未使用。
- 推奨:
  - `tk()` キーへ統合し、テストに「未翻訳キー検知」を追加。

### 4) [Low] SSE 再接続ループの運用観点

- 接続失敗時に指数バックオフ再接続する設計は妥当。
- ただし `401/403` の恒久エラーでも再接続を継続するため、認証不整合時に無駄リトライ化しやすい。
- 推奨:
  - `401/403` の場合は UI に再認証導線を出し、一定時間は再試行停止。

## 良い点

- API プロキシで許可パスを明示的にホワイトリスト化しており、ブラウザからの任意バックエンド到達を抑止。
- API key をサーバ側で注入し、ブラウザへ直接露出しない設計。
- `useDecide` は `AbortController` と request id で race condition を抑制。
- フロントエンド単体テストが豊富で、回帰検知の基盤がある。

## 優先対応ロードマップ（フロントのみ）

1. **今週**: エラーメッセージのサニタイズ（ユーザ向け簡略化）
2. **来週**: i18n 漏れの解消 + テスト追加
3. **今月**: CSP `Report-Only` の violation 収集と `unsafe-inline` 削減計画

## セキュリティ警告（要対応）

- **警告 1:** 実効 CSP に `unsafe-inline` が含まれ、XSS の防御層が弱まっています。
- **警告 2:** API エラーレスポンス本文の UI 露出により、情報漏えいの起点となる可能性があります。
