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
