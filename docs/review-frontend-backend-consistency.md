# フロントエンド・バックエンド整合性レビュー報告書

**日付:** 2026-03-08（初版） / 2026-03-10（更新）
**レビュー担当:** Claude（自動実行）
**対象範囲:** OpenAPI 仕様、バックエンド（Python/FastAPI）、フロントエンド（Next.js/TypeScript）、共有型

---

## サマリー

全体として、フロントエンドとバックエンドは**良好に整合**しています。共有型パッケージ（`@veritas/types`）はバックエンドの Pydantic スキーマを忠実に反映しており、BFF プロキシルートもパス変換を正しく行っています。

**2026-03-10 更新:** PR #699, #700, #701, #703 により、以下の課題が修正されました。

---

## 修正済み課題

### 1. ~~OpenAPI 仕様の `rsi_note` 型不一致~~ ✅ 修正済み (PR #701)

`openapi.yaml` の `rsi_note` を `type: object`（nullable）に修正。

### 2. ~~OpenAPI 仕様の `DecideResponse` に多数のフィールド欠落~~ ✅ 修正済み (PR #701)

DecideResponse スキーマを全フィールド含む形に更新。

### 3. ~~OpenAPI の `DecideRequest` と実バックエンド仕様の不整合~~ ✅ 修正済み (PR #701)

`context` を任意（デフォルト `{}`）に変更、`stream` 削除、`min_evidence` デフォルトを `1` に修正、`alternatives`/`memory_auto_put`/`persona_evolve` を追加。

### 4. ~~OpenAPI 仕様にバックエンドのエンドポイントが未記載~~ ✅ 修正済み (PR #701, #703)

全エンドポイントを追加。`/v1/governance/policy/history` も追加（PR #703）。

### 5. ~~OpenAPI `EvidenceItem` にバックエンド未対応の `hash` がある~~ ✅ 修正済み (PR #701)

`hash` を削除、`title` を追加。

### 6. ~~OpenAPI `TrustLog.fuji` の必須/任意不一致~~ ✅ 修正済み (PR #701)

`fuji` を `required` から除外。

### 7. ~~BFF ルートポリシーが一部バックエンドエンドポイントを未カバー~~ ✅ 修正済み (PR #701)

全エンドポイントにポリシーを追加。除外対象は `route-auth.ts` にコメントで文書化済み。

### 8. ~~フロントエンドで `ai_disclosure` と `regulation_notice` が optional 扱い~~ ✅ 修正済み (PR #700)

`decision.ts` で必須フィールドとして定義。`isDecideResponse` バリデータでも検証。

### 9. ~~フロントエンド型定義に `DecideResponse.coercion_events` がない~~ ✅ 対応不要

バックエンドで `exclude=True` のため JSON には含まれない。`[key: string]: unknown` で受け止め可能。

### 10. ~~`Gate` と `GateOut` の命名差~~ ✅ 対応不要

フィールドは同一。フロントエンドの命名（`GateOut`）は UI 層の慣習に従う。

### 11. ~~openapi.yaml の `Option` スキーマに `score` と `score_raw` がない~~ ✅ 修正済み (PR #701)

`score`、`score_raw`、`world`、`meta` を追加。

### 12. ~~ガバナンスバリデータの上限値チェック欠如~~ ✅ 修正済み (PR #703)

バックエンドの `ge`/`le` 制約に合わせて `api-validators.ts` の上限チェックを追加。

### 13. ~~TrustLog にパイプライン付与フィールドが未定義~~ ✅ 修正済み (PR #703)

`query`、`gate_status`、`gate_risk` を `TrustLog` モデル、`TrustLogItem` 型、OpenAPI に追加。

### 14. ~~schemas.py のコメントが openapi.yaml の実態と不一致~~ ✅ 修正済み (PR #703)

`fuji` フィールドのコメントを「任意フィールド」に更新。

---

## 整合性マトリクス（更新版）

| 項目 | バックエンド ↔ フロントエンド | バックエンド ↔ OpenAPI | フロントエンド ↔ OpenAPI |
|------|:------------------:|:-----------------:|:------------------:|
| `/v1/decide` URL パス | OK | OK | OK |
| DecideRequest フィールド | OK | OK | OK |
| DecideResponse フィールド | OK | OK | OK |
| DecisionStatus 列挙値 | OK | OK | OK |
| EvidenceItem フィールド | OK | OK | OK |
| TrustLog フィールド | OK | OK | OK |
| Gate/GateOut フィールド | OK | OK | OK |
| 認証方式 | OK（BFF プロキシ） | OK | N/A |
| エラーハンドリング | OK | OK | N/A |
| SSE イベント | OK | OK | N/A |
| ガバナンスバリデーション | OK | OK | OK |

---

## 推奨事項（残存）

1. **優先度 3:** 将来の乖離防止のため、OpenAPI 仕様から TypeScript 型を生成する（またはその逆）運用を検討する。

---

## レビュー対象ファイル

| ファイル | 役割 |
|------|------|
| `openapi.yaml` | API 契約仕様 |
| `veritas_os/api/schemas.py` | バックエンド Pydantic モデル |
| `veritas_os/api/constants.py` | バックエンド定数 |
| `veritas_os/api/server.py` | バックエンド FastAPI エンドポイント |
| `packages/types/src/decision.ts` | 共有 TypeScript 型 |
| `packages/types/src/index.ts` | 共有型バリデータ |
| `frontend/app/api/veritas/[...path]/route.ts` | BFF プロキシ |
| `frontend/app/api/veritas/[...path]/route-auth.ts` | BFF 認可ポリシー |
| `frontend/features/console/api/useDecide.ts` | フロントエンド API クライアント |
| `frontend/lib/api-validators.ts` | フロントエンド API バリデータ |
| `frontend/app/governance/page.tsx` | ガバナンスページ |
| `frontend/app/audit/page.tsx` | 監査ページ |
| `frontend/app/risk/page.tsx` | リスクページ |
| `frontend/components/live-event-stream.tsx` | SSE クライアント |
| `frontend/middleware.ts` | Next.js ミドルウェア |
