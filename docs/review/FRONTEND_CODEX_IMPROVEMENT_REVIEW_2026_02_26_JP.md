# Frontend CODEX 改善精密レビュー（2026-02-26, JP）

## 0. レビュー対象と前提

- 対象: `frontend/` 配下（Next.js App Router + design-system 連携 UI）
- 目的: CODEX 運用画面の改善余地を、**保守性・安全性・信頼性・UX**の観点で精密に整理
- 責務境界: Planner / Kernel / Fuji / MemoryOS のドメインロジックは変更対象外（本レビューは frontend 表層のみ）

---

## 1. 総合判定

- **現状評価: B+（運用UIとしては成立、ただし拡張性とセキュリティで改善余地が大きい）**
- 特に優先すべきは以下:
  1. **P0: API key のクエリ文字列送信を停止（漏えいリスク）**
  2. **P0: フロントのセキュリティヘッダ/CSP 方針を明示**
  3. **P1: `console/page.tsx` の巨大化解消（責務分割）**
  4. **P1: バリデータの「型一致のみ」から「業務制約チェック」への拡張**
  5. **P2: i18n辞書化・文言管理の集中化**

---

## 2. 重要指摘（優先度順）

## P0-1. SSE の API key を query string で送っている（高リスク）

### 観測
- `buildEventUrl` で `api_key` を URL クエリに付与している。
- UI上も「query string で送る」と明示している。

### リスク
- URL はブラウザ履歴、プロキシログ、監視基盤、Referer 派生ログに残留しやすく、**認証情報漏えい**に直結。
- 「運用UIだから許容」は成立しない。社内環境でも監査ログ経由で二次流出しうる。

### 改善案
- 第一候補: SSE をやめて `fetch + ReadableStream` もしくは WebSocket 化し、`Authorization` / `X-API-Key` をヘッダ送信。
- 代替: same-origin の BFF エンドポイントを挟み、ブラウザから機密キーを直接持たせない。
- 最低限: 短寿命トークン + スコープ限定 + サーバ側ログマスキングを必須化。

---

## P0-2. `NEXT_PUBLIC_*` で API key を露出する設計

### 観測
- `NEXT_PUBLIC_VERITAS_API_KEY` を複数画面で読み取り、ブラウザ実行時に参照している。

### リスク
- `NEXT_PUBLIC_*` はクライアントバンドルに埋め込まれるため、**秘匿情報の配置場所として不適切**。
- 誤って本番キーを設定した場合、誰でも DevTools から取得可能。

### 改善案
- 本番運用では `NEXT_PUBLIC_VERITAS_API_KEY` を禁止。
- API 呼び出しをサーバ側 Route Handler に寄せ、ブラウザはセッション/CSRF 保護下の短命トークンのみ利用。
- CI で「`NEXT_PUBLIC_.*KEY`」を検出して fail させるガードを追加。

---

## P0-3. Next.js 側のセキュリティヘッダ/CSP方針が未定義

### 観測
- `next.config.mjs` は `transpilePackages` のみで、`headers()` による保護ヘッダ設定がない。

### リスク
- 将来の機能追加時に XSS/クリックジャッキング/混在コンテンツなどの防護が「個別実装頼み」になる。

### 改善案
- `Content-Security-Policy`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Strict-Transport-Security` を段階導入。
- 運用監査向けUIなので、まずは report-only CSP で可視化してから enforce へ移行。

---

## P1-1. `frontend/app/console/page.tsx` の単一ファイル肥大化（815行）

### 観測
- 1ファイルに UI、状態管理、通信、可視化、分析ロジックが集中。

### リスク
- 変更の局所性が低く、リグレッション発生時の原因追跡が困難。
- テストの粒度が粗くなり、障害時の切り分けコストが高い。

### 改善案
- 例: 以下へ分割
  - `features/console/api/useDecide.ts`（通信）
  - `features/console/state/useConsoleState.ts`（状態）
  - `features/console/components/*`（UI）
  - `features/console/analytics/*`（解析関数）
- 目標: 1コンポーネント 200–300行以下、関数責務単位でテスト可能化。

---

## P1-2. API バリデーションが「型」中心で、業務制約を検証していない

### 観測
- `api-validators.ts` は型チェック中心（boolean/number/string）で、値域・整合性・列挙制約が未検証。

### リスク
- 形式上は正しいが、意味的に壊れた値（例: negative threshold, deny<allow）を受け入れる。
- UI表示が正でも、オペレータ判断を誤らせる可能性。

### 改善案
- Zod / Valibot 等で schema + refine を定義し、以下を強制:
  - 範囲: `0 <= allow <= warn <= human_review <= deny <= 1`
  - 列挙: `audit_level`
  - 文字列: `updated_at` は ISO8601
- バリデーション失敗時は UI上で「形式エラー」と「意味エラー」を分離表示。

---

## P1-3. fetch のキャンセル制御不足（連打/ページ遷移時）

### 観測
- `runDecision` は `fetch` を実行するが `AbortController` を使っていない。

### リスク
- 連続送信やページ遷移時に旧レスポンスが遅延到着し、最新状態を上書きする競合が起こりうる。

### 改善案
- `AbortController` + request id ガードを導入。
- `loading` 状態のみではなく「最後に有効なリクエストID」一致時のみ `setResult` を実行。

---

## P2-1. 文言の重複と i18n 辞書未整備

### 観測
- `t(ja, en)` のインライン文言が多数散在。

### リスク
- 文言修正・翻訳レビュー・用語統一が難しく、機能追加ほど翻訳負債が増える。

### 改善案
- `locales/ja.ts`, `locales/en.ts` のキー方式へ移行。
- 操作系文言（エラー、ボタン、説明）を優先抽出して段階移行。

---

## 3. 既存の良い点（維持推奨）

- API レスポンスに対する型ガードを既に導入しており、未検証JSONの生利用を抑制できている。
- a11y を Playwright + axe で継続確認している。
- ライブイベント表示に URL バリデーションと再接続処理があり、運用監視UIとしての基本品質は確保されている。

---

## 4. 実行優先ロードマップ（提案）

1. **Sprint 1 (P0):**
   - Query API key 送信廃止
   - `NEXT_PUBLIC_*KEY` 利用禁止ルール
   - `next.config` に security headers report-only 導入
2. **Sprint 2 (P1):**
   - `console/page.tsx` 分割
   - `AbortController` と race 防止
3. **Sprint 3 (P1/P2):**
   - schema バリデーション強化（意味制約）
   - i18n 辞書化

---

## 5. セキュリティ警告（明示）

- **警告A:** API key を URL クエリで送る実装は、ログ経由漏えいの代表パターン。
- **警告B:** `NEXT_PUBLIC_*` に機密鍵を置く運用は本番禁止。
- **警告C:** ヘッダ/CSP 未整備のまま機能追加を続けると、将来の脆弱性対応コストが指数的に増加。

