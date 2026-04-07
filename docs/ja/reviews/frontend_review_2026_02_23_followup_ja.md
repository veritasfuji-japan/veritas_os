# Frontend レビュー（フォローアップ, 2026-02-23）

## 対象
- `frontend/app`
- `frontend/components`
- `frontend/lib`

## 実施内容
- コード静的確認（主要UI・API連携・入力処理）
- テスト実行（Vitest）
- 型検査（TypeScript）
- Lint 実行（Next.js ESLint）

---

## 総評
フロントエンドは、型安全性・テスト整備・UI責務分離の観点で概ね良好です。`lint` / `typecheck` / `test` はすべて通過しました。

一方で、**SSE 接続時に API キーをクエリ文字列へ付与している点は継続して High のセキュリティリスク**です。

---

## 指摘事項

### 1. [High / Security] SSE URL クエリへ API キーを付与
- 対象: `frontend/components/live-event-stream.tsx`
- 内容: `buildEventUrl` で `api_key` を query param に設定して `EventSource` 接続している。
- リスク:
  - URL がブラウザ履歴・プロキシ・アクセスログ・監視基盤へ残ると機密情報漏えいにつながる。
  - UI 上の Security note は注意喚起として有効だが、漏えい経路自体は残る。
- 推奨:
  1. Cookie + サーバーセッション（HttpOnly / SameSite）へ移行。
  2. 互換性要件で query が必要なら、短命・単用途トークン化し、長期 API キー直載せを回避。
  3. バックエンド・プロキシでクエリログマスクを強制。

### 2. [Low / Operability] Lint 実行方式の将来互換
- 対象: `frontend/package.json` の `next lint` 利用
- 内容: 実行時に Next.js 側から `next lint` 廃止予定の警告が表示される。
- リスク: 直近では低いが、将来の Next.js 更新時に CI で破綻し得る。
- 推奨: ESLint CLI ベースへ段階移行。

---

## 良い点
- API レスポンスのランタイムバリデーション（`frontend/lib/api-validators.ts`）が整備されている。
- `live-event-stream` のイベント受信テストで `act` が導入され、以前の安定性懸念が軽減されている。
- 主要画面（console / governance / audit / risk）のテストカバレッジが維持されている。

---

## セキュリティ警告（必読）
- **警告:** 現行の SSE 実装は API キーを URL クエリに載せるため、ログ経由の漏えいリスクがあります。運用環境では短命トークン化または Cookie ベース認証への移行を推奨します。
