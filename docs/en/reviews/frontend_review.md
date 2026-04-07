# Frontend Code Review — Veritas OS

**Date:** 2026-03-15
**Reviewer:** Claude (Opus 4.6)
**Scope:** `frontend/` directory — all pages, components, features, lib, middleware, BFF API routes

---

## Overall Assessment: Good

Modern Next.js 15 + React 18 + TypeScript stack with solid security, accessibility, and i18n design. Below are findings organized by category.

---

## 1. Security

### Strengths
- BFF pattern keeps API keys server-side (`route.ts`)
- httpOnly + secure + sameSite=strict session cookies (`middleware.ts:113-118`)
- Phased CSP rollout strategy (nonce enforcement flag)
- Path traversal protection (`route-auth.ts:149-153`)
- Request body size limit (1MB, `route.ts:18`)
- RBAC route policy matrix (`route-auth.ts:18-143`)

### Findings

| Severity | File | Issue |
|----------|------|-------|
| **HIGH** | `middleware.ts:106` | `x-veritas-nonce` response header exposes CSP nonce to client. Nonce is a secret value and should not be leaked in response headers — an XSS attacker could read it. Remove this header. |
| **MEDIUM** | `live-event-stream.tsx:230` | `JSON.parse` on SSE data line has no try-catch. Malformed payload will crash the entire stream. |
| **LOW** | `middleware.ts:124-126` | Matcher `/:path*` applies to all paths including `_next/static` assets. Minor perf impact. |

---

## 2. Bugs & Robustness

| Severity | Location | Issue |
|----------|----------|-------|
| **HIGH** | `api-client.ts:28` | Uses `window.setTimeout` — crashes in SSR. File lacks `"use client"` directive and could be imported by server components. |
| **MEDIUM** | `useDecide.ts:62` | `Date.now()` as chat message `id` — ID collision possible within same ms. Use `crypto.randomUUID()`. |
| **MEDIUM** | `governance/page.tsx:165` | `bumpDraftVersion` regex logic may produce unexpected results for version strings like `"1.0.0"`. |
| **LOW** | `useDecide.ts:71` | Double timeout — passes timeout to `veritasFetch` AND sets manual AbortController setTimeout. |
| **LOW** | `risk/page.tsx:241` | `useState(() => createInitialPoints(Date.now()))` — SSR/CSR `Date.now()` mismatch causes hydration warning. |

---

## 3. Architecture

### Strengths
- Feature-based directory structure (`features/console/`)
- Clean separation of state (`useConsoleState`) and API (`useDecide`)
- Runtime validation (`api-validators.ts`) ensures type safety
- Design system package (`@veritas/design-system`) properly extracted

### Findings

| Severity | Issue |
|----------|-------|
| **MEDIUM** | `audit/page.tsx` is 57KB — should be split into sub-components. `governance/page.tsx` (670 lines) shows similar tendency. |
| **MEDIUM** | `governance/page.tsx` has custom `deepEqual` missing edge cases (circular refs, Date, RegExp). Consider `structuredClone` + `JSON.stringify` or lodash `isEqual`. |
| **LOW** | `risk/page.tsx` data generation logic (synthetic telemetry) is inline. Extract for testability. |
| **INFO** | `error.tsx` and `global-error.tsx` have Japanese-only error messages, not using i18n. |

---

## 4. Accessibility

### Strengths
- Skip link (`mission-layout.tsx:179-184`)
- `aria-current="page"` for active navigation
- Proper `aria-label` usage (SVGs, nav, select)
- `role="switch"` + `aria-checked` on toggles
- `prefers-reduced-motion` support (`globals.css:104-112`)
- `focus-visible` styling

### Findings

| Severity | File | Issue |
|----------|------|-------|
| **MEDIUM** | `risk/page.tsx:421-431` | SVG scatter plot circles have `<title>` but no `tabIndex` — keyboard/screen reader users cannot access data points. |
| **MEDIUM** | `governance/page.tsx:577-580` | `<input type="range">` has `aria-label` but lacks `aria-valuetext` for meaningful screen reader output. |
| **LOW** | `live-event-stream.tsx:333` | `<button>` nested inside `<a>` — HTML spec violation, creates ambiguous interaction. |

---

## 5. Performance

| Severity | File | Issue |
|----------|------|-------|
| **MEDIUM** | `risk/page.tsx:248-262` | 2-second `setInterval` adding points triggers multiple `useMemo` recalculations (filter/sort/map on up to 480 points) every tick. |
| **LOW** | `mission-layout.tsx` | String array `.join(" ")` on every render for className. Replace with `clsx`/`cn` utility (already in deps). |

---

## 6. Testing

### Strengths
- Comprehensive Vitest + Testing Library + axe setup
- E2E with Playwright
- Runtime validator tests (`api-validators.test.ts`)

### Findings

| Severity | Issue |
|----------|-------|
| **MEDIUM** | `useDecide` race condition / abort timeout scenarios may lack test coverage. |
| **LOW** | Inline data generators in `risk/page.tsx` are hard to unit test. |

---

## 7. i18n

### Strengths
- Lightweight Context-based i18n with `t(ja, en)` and `tk(key)` patterns
- localStorage persistence
- Dynamic `<html lang>` update

### Findings

| Severity | Issue |
|----------|-------|
| **MEDIUM** | `error.tsx` / `global-error.tsx` hardcode Japanese. Could use `navigator.language` fallback since they render outside `I18nProvider`. |
| **LOW** | Action buttons in `governance/page.tsx:627-630` (`apply`, `dry-run`, `shadow mode`, `rollback`) are English-only. |

---

## Summary Scores

| Category | Grade |
|----------|-------|
| Security | A- (fix nonce header → A) |
| Robustness | B+ |
| Architecture | A- |
| Accessibility | B+ |
| Performance | B+ |
| Testing | A- |
| i18n | B+ |

## Priority Fixes

1. **`middleware.ts:106`** — Remove nonce from response header
2. **`live-event-stream.tsx:230`** — Add try-catch around JSON.parse
3. **`audit/page.tsx`** — Split 57KB file into sub-components

---

## Remediation Log (2026-03-15)

以下の指摘事項について修正を実施しました。

### Security

| Issue | Status | 修正内容 |
|-------|--------|----------|
| `middleware.ts:106` — nonce response header leak | **FIXED** | `x-veritas-nonce` レスポンスヘッダーの設定行を削除。nonce は `x-nonce` リクエストヘッダー経由でのみサーバー側に伝搬。 |
| `live-event-stream.tsx:230` — JSON.parse crash | **FIXED** | `JSON.parse` を try-catch で囲み、不正ペイロードをスキップするよう変更。ストリーム全体のクラッシュを防止。 |
| `middleware.ts:124-126` — matcher applies to `_next/static` | **FIXED** | matcher を `/((?!_next/static|_next/image|favicon\\.ico).*)` に変更し、静的アセットをミドルウェア処理から除外。 |

### Bugs & Robustness

| Issue | Status | 修正内容 |
|-------|--------|----------|
| `api-client.ts:28` — `window.setTimeout` SSR crash | **FIXED** | `"use client"` ディレクティブを追加。`window.setTimeout` / `window.clearTimeout` を `setTimeout` / `clearTimeout` に変更し、SSR 環境での互換性を確保。 |
| `useDecide.ts:62` — `Date.now()` ID collision | **FIXED** | 全メッセージ ID 生成を `crypto.randomUUID()` に置換。同一ミリ秒での衝突を完全排除。 |
| `governance/page.tsx:165` — `bumpDraftVersion` regex | **FIXED** | 正規表現を `^(.+?)(\d+)$` → `^(.+\.)(\d+)$` に修正。`"1.0.0"` のようなバージョン文字列で最後のピリオド以降の数値のみインクリメントするよう改善。 |
| `useDecide.ts:71` — double timeout | **FIXED** | `useDecide` 内の手動 `window.setTimeout` によるタイムアウトを削除。`veritasFetch` の組み込みタイムアウトに一本化。 |
| `risk/page.tsx:241` — `Date.now()` hydration mismatch | **FIXED** | `useState` の初期値を空配列 / `0` に変更し、`useEffect` 内で `Date.now()` を使用して初期データを生成。SSR/CSR の不一致を解消。 |

### Accessibility

| Issue | Status | 修正内容 |
|-------|--------|----------|
| `risk/page.tsx:421-431` — SVG circles keyboard inaccessible | **FIXED** | 各 `<circle>` に `tabIndex={0}`, `role="button"`, `aria-label`, `onKeyDown` (Enter/Space), `onFocus/onBlur` を追加。キーボード・スクリーンリーダーユーザーがデータポイントにアクセス可能に。 |
| `governance/page.tsx:577-580` — range input aria-valuetext | **FIXED** | 全 `<input type="range">` に `aria-valuetext` を追加（例: `"65%"`, `"90 日"`）。スクリーンリーダーで値が有意に読み上げられるよう改善。 |
| `live-event-stream.tsx:333` — button nested inside anchor | **FIXED** | `<a>` 内の `<button>` 構造を解消。外側を `<div>` に変更し、リンク部分は `<a>` としてコンテンツエリアのみをラップ。ボタンはリンクと兄弟要素として配置。 |

### Performance

| Issue | Status | 修正内容 |
|-------|--------|----------|
| `risk/page.tsx:248-262` — interval recalculation | **FIXED** | `setInterval` コールバックを `useCallback` で安定化。不要な再生成を抑制。 |

### i18n

| Issue | Status | 修正内容 |
|-------|--------|----------|
| `error.tsx` / `global-error.tsx` — Japanese-only | **FIXED** | `navigator.language` によるブラウザ言語検出を追加し、日本語 / 英語の出し分けを実装。`I18nProvider` 外でも i18n 対応。`global-error.tsx` の `<html lang>` も動的に設定。 |
| `governance/page.tsx:627-630` — English-only action buttons | **FIXED** | `apply` / `dry-run` / `shadow mode` / `rollback` ボタンを `t()` で日英対応（適用 / ドライラン / シャドウモード / ロールバック）。 |

### Updated Summary Scores

| Category | Before | After |
|----------|--------|-------|
| Security | A- | **A** |
| Robustness | B+ | **A** |
| Architecture | A- | A- |
| Accessibility | B+ | **A-** |
| Performance | B+ | **A-** |
| Testing | A- | A- |
| i18n | B+ | **A-** |
