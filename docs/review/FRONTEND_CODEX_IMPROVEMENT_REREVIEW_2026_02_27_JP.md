# Frontend CODEX 改善再レビュー（2026-02-27, JP）

## 0. 対象と判定基準

- 対象: `frontend/` 配下
- 参照: `docs/review/FRONTEND_CODEX_IMPROVEMENT_REVIEW_2026_02_26_JP.md` の指摘項目
- 判定: **完了 / 一部完了 / 未完了**

---

## 1. 総合判定

- **総合: A-（前回の主要改善は概ね完了）**
- P0/P1 の主要項目は実装で確認でき、特に API key 露出リスクが大きく低減。
- ただし、CSP は report-only 段階であり、運用では違反ログ監視と enforce への移行計画が必要。

---

## 2. 指摘別の再評価

## P0-1. SSE の API key query string 送信廃止

- **判定: 完了**
- クライアントは `/api/veritas/v1/events` へ接続し、URL クエリで `api_key` を送っていない。
- API key は Route Handler 側で `X-API-Key` ヘッダ注入となっており、ブラウザ露出を回避できている。

## P0-2. `NEXT_PUBLIC_*` で API key 露出

- **判定: 完了（実装上） / 一部完了（運用ガード）**
- Route Handler は `VERITAS_API_KEY` を利用し、ブラウザ側コードで API key 参照は確認されなかった。
- 一方で、CI による `NEXT_PUBLIC_.*KEY` 検知 fail ルールは確認できなかったため、運用ガードは追加余地あり。

## P0-3. Next.js セキュリティヘッダ/CSP

- **判定: 完了（report-only 導入）**
- `next.config.mjs` で `Content-Security-Policy-Report-Only` を含む主要ヘッダが全体適用されている。
- `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Strict-Transport-Security`, `X-Content-Type-Options` も設定済み。

## P1-1. `console/page.tsx` の肥大化解消

- **判定: 完了**
- `frontend/app/console/page.tsx` は 119 行まで縮小され、`features/console/*` に責務分離済み。
- 通信・状態・UI コンポーネントが分割され、保守性は大幅に改善。

## P1-2. バリデーションの意味制約

- **判定: 完了**
- `api-validators.ts` で範囲制約・順序制約・列挙制約・ISO8601 検証を実装。
- さらに `format` / `semantic` を分類して UI 表示できる構造になっている。

## P1-3. fetch キャンセル制御

- **判定: 完了**
- `useDecide` で `AbortController` と request id（最新リクエスト判定）が導入済み。
- stale response を無視するテストも存在し、再発防止の強度がある。

## P2-1. i18n 辞書化

- **判定: 一部完了**
- `locales/ja.ts`, `locales/en.ts` と `tk()` ベースのキー参照が導入済み。
- ただし全画面で完全キー化しきれていないため、段階移行の継続が望ましい。

---

## 3. セキュリティ警告（継続監視）

- **警告A（運用）:** CSP は report-only のため、違反ログ監視が形骸化すると防御効果が限定される。
- **警告B（設定）:** `VERITAS_API_KEY` 未設定時は 503 応答となる。デプロイ時の秘密情報注入チェックを必須化すべき。
- **警告C（将来）:** allow-list 方式の proxy path は安全側だが、今後の API 追加時に審査なしで path を広げると SSRF/権限逸脱リスクが再燃する。

---

## 4. 追加推奨（次アクション）

1. CI に `NEXT_PUBLIC_.*KEY` 禁止ルールを追加。
2. CSP report-only の violation を収集し、enforce 移行基準を明文化。
3. i18n の未移行文言を棚卸しし、キー方式へ統一。
