# Frontend 精密レビュー（2026-02-23）

## 対象
- `frontend/app`
- `frontend/components`
- `packages/design-system`（UI基盤の参照のみ）

## 実施観点
- セキュリティ（認証情報、通信、入力処理）
- UX / アクセシビリティ
- 信頼性（非同期・状態管理・テスト安定性）
- 保守性（型安全性、責務分離、拡張性）

---

## 総評
現状フロントエンドは **UI構成・可読性・基本的な型付けは良好** で、`lint/typecheck/test` も通過しています。一方で、運用フェーズで問題化しやすい論点として、**SSEでのAPIキーのクエリ文字列送信**、**APIレスポンスの実行時バリデーション不足**、**テストの `act(...)` warning** が確認できました。特に1点目はセキュリティ上の優先対応項目です。

---

## 重要指摘（優先度順）

### 1) [High / Security] SSE接続でAPIキーをクエリ文字列へ付与
- 対象: `LiveEventStream` の `buildEventUrl`
- 現状: `api_key` を URL の query param に載せて `EventSource` 接続しています。
- リスク:
  - URL は各種ログ（ブラウザ履歴、リバースプロキシ、アクセスログ、監視基盤）に残りやすく、**秘匿情報漏えい面積が広い**。
  - 画面にも Security note はありますが、実装上の根本対策にはなっていません。
- 推奨対応:
  1. 可能なら **Cookieベース認証 + SameSite/HttpOnly** へ移行。
  2. 互換性上 query が不可避なら、短命トークン（1回/短TTL）を発行し、長期APIキーを直接使わない。
  3. バックエンド・プロキシ側で query の秘匿化/マスクを徹底。

### 2) [Medium / Reliability] APIレスポンスの実行時検証不足（型アサーション依存）
- 対象: `governance` / `audit` ページの `await res.json() as ...`
- 現状: TypeScript型へキャストしていますが、実行時には未検証のため、仕様逸脱レスポンスでUI破綻リスクがあります。
- 推奨対応:
  - `@veritas/types` 側にランタイムガード（`isGovernancePolicy`, `isTrustLogsResponse` など）を追加し、表示前に検証。
  - 不一致時は安全なエラーパスへフォールバック（現在より診断しやすいメッセージを返す）。

### 3) [Medium / Test Stability] `live-event-stream.test.tsx` で `act(...)` warning
- 対象: SSEイベント受信テスト
- 現状: 非同期状態更新が `act` で包まれておらず、将来React/Vitest更新で flaky 化の可能性。
- 推奨対応:
  - イベント発火部分を `await act(async () => { ... })` でラップ。
  - あるいは `waitFor` ベースでUI反映完了を待って assertion。

### 4) [Low / Maintainability] `governance` の初期ロード effect で依存配列を明示的に無効化
- 対象: `useEffect` + `eslint-disable-next-line react-hooks/exhaustive-deps`
- 現状: 意図はコメントで説明されており妥当ですが、将来の変更で stale closure リスクを生む余地があります。
- 推奨対応:
  - 「初回のみ自動ロード」と「手動再読込」を明確分離した小関数化、あるいは `useRef` フラグ等で lint disable を減らす。

---

## 良い点
- ナビゲーション、カード分割、ページ責務が明確で可読性が高い。
- Governance画面の差分プレビュー（`collectChanges`）は変更可視化に有効。
- a11y テストが存在し、主要画面の単体テストも整備されている。

---

## 推奨アクションプラン
1. **直近（最優先）**
   - SSE認証方式の見直し（query文字列APIキーの段階的廃止）。
2. **短期（次スプリント）**
   - API応答のランタイムバリデーション導入。
   - `LiveEventStream` テストの `act` warning 解消。
3. **中期**
   - fetch層を共通化し、エラー型/再試行/タイムアウト/abort方針を統一。

---

## セキュリティ警告（明示）
- **警告:** 現行のSSE実装はAPIキーをURLクエリに付与するため、ログ経由での漏えいリスクがあります。運用環境では短命トークン化またはCookieベース認証へ移行することを強く推奨します。

