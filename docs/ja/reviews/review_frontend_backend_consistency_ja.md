# フロントエンド・バックエンド整合性レビュー報告書

**日付:** 2026-03-08（初版） / 2026-03-10（更新）
**レビュー担当:** Claude（自動実行）
**対象範囲:** OpenAPI 仕様、バックエンド（Python/FastAPI）、フロントエンド（Next.js/TypeScript）、共有型

---

## サマリー

全体として、フロントエンドとバックエンドは**良好に整合**しています。共有型パッケージ（`@veritas/types`）はバックエンドの Pydantic スキーマを忠実に反映しており、BFF プロキシルートもパス変換を正しく行っています。

**2026-03-10 更新:** PR #699, #700, #701, #703, #704 により、以下の課題が修正されました。
また、本 PR にて以下の追加修正を実施しました：
- `PersonaState`、`EvoTips`、`ChatRequest` 型をフロントエンド共有型に追加
- `isTrustLogItem` バリデータにパイプライン付与フィールド（`query`、`gate_status`、`gate_risk`）の型検証を追加
- OpenAPI 仕様に `PersonaState`、`EvoTips`、`ChatRequest` スキーマを追加
- OpenAPI 仕様にガバナンスポリシー関連スキーマ（`GovernancePolicy`、`FujiRules`、`RiskThresholds`、`AutoStop`、`LogRetention`、`GovernancePolicyResponse`）を追加
- OpenAPI 仕様に `TrustFeedbackRequest` スキーマを追加
- OpenAPI の `/v1/governance/policy` エンドポイントを正式なスキーマ参照に更新
- OpenAPI の `/v1/trust/feedback` エンドポイントを正式なスキーマ参照に更新
- OpenAPI の `Context`、`EvidenceItem`、`Option` フィールドに `maxLength` 制約を追加

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

### 15. ~~フロントエンド共有型に `PersonaState`/`EvoTips`/`ChatRequest` が未定義~~ ✅ 修正済み (本 PR)

バックエンド `schemas.py` に定義されている `PersonaState`、`EvoTips`、`ChatRequest` モデルに対応する TypeScript インターフェースを `packages/types/src/decision.ts` に追加。ランタイム型ガード `isPersonaState()`、`isEvoTips()` も追加。OpenAPI にも対応するスキーマを追加。

### 16. ~~`isTrustLogItem` バリデータがパイプライン付与フィールドを未検証~~ ✅ 修正済み (本 PR)

`TrustLogItem` インターフェースには `query`、`gate_status`、`gate_risk` フィールドが定義されていたが、`isTrustLogItem()` バリデータではこれらのフィールドの型チェックが行われていなかった。`Optional[str]`/`Optional[float]` に対応する `undefined | null | string`/`undefined | null | number` の型検証を追加。

### 17. ~~OpenAPI にガバナンスポリシー関連スキーマが未定義~~ ✅ 修正済み (本 PR)

バックエンド（`governance.py`）とフロントエンド（`api-validators.ts`）にはガバナンスポリシーの完全な型定義が存在していたが、OpenAPI 仕様にはコンポーネントスキーマが定義されておらず、エンドポイントのレスポンスは汎用的な `additionalProperties: true` になっていた。`FujiRules`、`RiskThresholds`、`AutoStop`、`LogRetention`、`GovernancePolicy`、`GovernancePolicyResponse` をコンポーネントスキーマとして追加し、`/v1/governance/policy` の GET/PUT エンドポイントを正式なスキーマ参照に更新。

### 18. ~~OpenAPI の `/v1/trust/feedback` リクエストスキーマが未定義~~ ✅ 修正済み (本 PR)

バックエンド `TrustFeedbackRequest`（`schemas.py`）には `user_id`、`score`、`note`、`source` の各フィールドが型制約付きで定義されていたが、OpenAPI では `additionalProperties: true` のみとなっていた。`TrustFeedbackRequest` コンポーネントスキーマを追加し、エンドポイントを正式なスキーマ参照に更新。

### 19. ~~OpenAPI の入力フィールドに `maxLength` 制約が欠如~~ ✅ 修正済み (本 PR)

バックエンド Pydantic モデルには `max_length` 制約が定義されていたが、OpenAPI 仕様に反映されていなかった。以下のフィールドに `maxLength` を追加：
- `Context`: `user_id`（500）、`session_id`（500）、`query`（10000）
- `EvidenceItem`: `source`（500）、`uri`（2000）、`title`（1000）、`snippet`（50000）
- `Option`: `id`（500）、`title`（1000）、`description`（20000）、`text`（1000）

### 20. ~~OpenAPI の `/v1/system/halt` リクエストスキーマに `operator` フィールドが欠如~~ ✅ 修正済み (本 PR)

バックエンド `SystemHaltRequest`（`server.py`）には `reason`（必須、max_length=500）と `operator`（必須、max_length=200）の両フィールドが定義されていたが、OpenAPI 仕様には `reason` のみが記載されていた。`operator` フィールドと `required` 制約、`minLength`/`maxLength` 制約を追加。

### 21. ~~OpenAPI の `/v1/system/resume` リクエストスキーマが不正~~ ✅ 修正済み (本 PR)

バックエンド `SystemResumeRequest`（`server.py`）には `operator`（必須、max_length=200）と `comment`（任意、default=""、max_length=500）が定義されていたが、OpenAPI 仕様には存在しないフィールド `reason` のみが記載されていた。正しいフィールド `operator`（必須）と `comment`（任意）に修正し、`minLength`/`maxLength` 制約を追加。

### 22. ~~OpenAPI の `/v1/compliance/config` PUT リクエストスキーマが未定義~~ ✅ 修正済み (本 PR)

バックエンド `ComplianceConfigBody`（`server.py`）には `eu_ai_act_mode`（bool、default=false）と `safety_threshold`（float、default=0.8、ge=0.0、le=1.0）が定義されていたが、OpenAPI では `additionalProperties: true` のみとなっていた。正式なプロパティ定義に更新。

### 23. ~~フロントエンド `MemoryPutRequest.kind` が `string` 型~~ ✅ 修正済み (本 PR)

バックエンドの `VALID_MEMORY_KINDS`（`constants.py`）には `"semantic" | "episodic" | "skills" | "doc" | "plan"` の5種が定義されており、フロントエンドにも `MemoryKind` リテラル型が存在するにもかかわらず、`MemoryPutRequest.kind` は汎用 `string` 型だった。`MemoryKind` に修正。

### 24. ~~フロントエンド `MemorySearchRequest.kinds` が `string` 型~~ ✅ 修正済み (本 PR)

`MemorySearchRequest.kinds` が `string | string[] | null` と汎用型で定義されていたが、バックエンドの検証に合わせて `MemoryKind | MemoryKind[] | null` に修正。

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
| PersonaState/EvoTips 型 | OK | OK | OK |
| ChatRequest 型 | OK | OK | OK |
| TrustLogItem バリデータ | OK | OK | OK |
| 認証方式 | OK（BFF プロキシ） | OK | N/A |
| エラーハンドリング | OK | OK | N/A |
| SSE イベント | OK | OK | N/A |
| ガバナンスバリデーション | OK | OK | OK |
| ガバナンスポリシースキーマ | OK | OK | OK |
| TrustFeedbackRequest | OK | OK | OK |
| 入力フィールド制約（maxLength） | OK | OK | OK |
| SystemHaltRequest | OK | OK | OK |
| SystemResumeRequest | OK | OK | OK |
| ComplianceConfigBody | OK | OK | OK |
| MemoryPutRequest.kind 型 | OK | OK | OK |
| MemorySearchRequest.kinds 型 | OK | OK | OK |

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
