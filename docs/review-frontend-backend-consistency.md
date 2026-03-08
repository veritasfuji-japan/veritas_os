# フロントエンド・バックエンド整合性レビュー報告書

**日付:** 2026-03-08
**レビュー担当:** Claude（自動実行）
**対象範囲:** OpenAPI 仕様、バックエンド（Python/FastAPI）、フロントエンド（Next.js/TypeScript）、共有型

---

## サマリー

全体として、フロントエンドとバックエンドは**良好に整合**しています。共有型パッケージ（`@veritas/types`）はバックエンドの Pydantic スキーマを忠実に反映しており、BFF プロキシルートもパス変換を正しく行っています。一方で、重要度 3 段階にまたがるいくつかの不整合・ギャップが確認されました。

---

## 重大な課題（要対応）

### 1. OpenAPI 仕様の `rsi_note` 型不一致

| レイヤー | 型 |
|-------|------|
| **openapi.yaml** (L196) | `type: string` |
| **バックエンド** `schemas.py` (L461) | `Optional[Dict[str, Any]]` |
| **フロントエンド** `decision.ts` (L87) | `Record<string, unknown> \| null` |

**影響:** OpenAPI 仕様では `rsi_note` は文字列ですが、実際のバックエンドは dict/object を返します。OpenAPI 仕様から自動生成されたクライアントは、実レスポンス受信時に破綻する可能性があります。

**修正案:** `openapi.yaml` の型を `type: object`（nullable）に更新する。

### 2. OpenAPI 仕様の `DecideResponse` に多数のフィールド欠落

OpenAPI の `DecideResponse` スキーマ（L152-196）には、バックエンドとフロントエンドの双方が前提としている以下のフィールドが不足しています。

| 欠落フィールド | バックエンド型 | フロントエンド型 |
|---------------|-------------|---------------|
| `version` | `str` | `string` |
| `options` | `List[Alt]` | `DecisionAlternative[]` |
| `decision_status` | `Literal[...]` | `DecisionStatus` |
| `rejection_reason` | `Optional[str]` | `string \| null` |
| `values` | `Optional[ValuesOut]` | `ValuesOut \| null` |
| `gate` | `Gate` | `GateOut` |
| `extras` | `Dict[str, Any]` | `Record<string, unknown>` |
| `meta` | `Dict[str, Any]` | `Record<string, unknown>` |
| `persona` | `Dict[str, Any]` | `Record<string, unknown>` |
| `plan` | `Optional[Dict]` | `Record<string, unknown> \| null` |
| `planner` | `Optional[Dict]` | `Record<string, unknown> \| null` |
| `reason` | `Optional[Any]` | `unknown` |
| `evo` | `Optional[Dict]` | `Record<string, unknown> \| null` |
| `memory_citations` | `List[Any]` | `unknown[]` |
| `memory_used_count` | `int` | `number` |
| `ai_disclosure` | `str` | `string`（optional） |
| `regulation_notice` | `str` | `string`（optional） |
| `affected_parties_notice` | `Optional[Dict]` | `Record<string, unknown> \| null` |

**影響:** OpenAPI 仕様が実際の API 契約に対して大きく遅れており、`openapi.yaml` を前提にする外部利用者はこれらのフィールドを認識できません。

**修正案:** `openapi.yaml` の DecideResponse スキーマを全フィールド含む形に更新する。

### 3. OpenAPI の `DecideRequest` と実バックエンド仕様の不整合

| フィールド | openapi.yaml | バックエンド（schemas.py） |
|-------|-------------|---------------------|
| `context` | **必須**、`$ref: Context` | **任意**（デフォルト `{}`）、任意の dict を受理 |
| `query` | 記載なし | 受理（デフォルト `""`） |
| `min_evidence` | デフォルト `2` | デフォルト `1` |
| `stream` | `boolean` として定義 | DecideRequest には存在しない |
| `alternatives` | 記載なし | 受理 |
| `memory_auto_put` | 記載なし | 受理（デフォルト `true`） |
| `persona_evolve` | 記載なし | 受理（デフォルト `true`） |

**影響:** OpenAPI 仕様では `context` が必須かつ構造化スキーマですが、実際のバックエンドは `query` + 空 `context` を受け付けます（これはフロントエンドが実際に送っている形です）。また、仕様にある `stream` はバックエンドに存在せず、`min_evidence` のデフォルト値も一致しません。

**修正案:** 実際の DecideRequest スキーマに合わせて `openapi.yaml` を整合させる。

---

## 中程度の課題（推奨対応）

### 4. OpenAPI 仕様にバックエンドのエンドポイントが未記載

以下のエンドポイントはバックエンドに存在しますが、`openapi.yaml` には定義がありません。

| エンドポイント | 用途 |
|----------|---------|
| `GET /v1/events` | SSE イベントストリーム |
| `GET /v1/trust/logs` | 信頼ログのページング一覧 |
| `POST /v1/trust/feedback` | 人手フィードバック記録 |
| `GET /v1/trustlog/verify` | 信頼ログチェーン検証 |
| `GET /v1/trustlog/export` | 信頼ログエクスポート |
| `GET /v1/governance/value-drift` | 価値ドリフト指標 |
| `GET /v1/governance/policy` | ガバナンスポリシー取得 |
| `PUT /v1/governance/policy` | ガバナンスポリシー更新 |
| `GET /v1/compliance/config` | コンプライアンス設定取得 |
| `PUT /v1/compliance/config` | コンプライアンス設定更新 |
| `GET /v1/compliance/deployment-readiness` | デプロイ準備状況チェック |
| `POST /v1/system/halt` | 緊急システム停止 |
| `POST /v1/system/resume` | システム再開 |
| `GET /v1/system/halt-status` | 停止状態確認 |
| `GET /v1/metrics` | システムメトリクス |
| `GET /v1/report/eu_ai_act/{decision_id}` | EU AI Act レポート |
| `GET /v1/report/governance` | ガバナンスレポート |
| `POST /v1/memory/search` | メモリ検索 |
| `POST /v1/memory/erase` | メモリ削除 |
| `POST /v1/decision/replay/{decision_id}` | 意思決定リプレイ（v2） |
| `WS /v1/ws/trustlog` | WebSocket 信頼ログストリーム |

**影響:** 外部 API 利用者やツール（Swagger UI、コードジェネレータ）から見える API 表面が不完全になります。

### 5. OpenAPI `EvidenceItem` にバックエンド未対応の `hash` がある

`openapi.yaml`（L83）の `EvidenceItem` には `hash` フィールドがありますが、これはバックエンド `EvidenceItem` スキーマにもフロントエンド `EvidenceItem` インターフェースにも存在しません。逆に、バックエンドにある `title` は OpenAPI 仕様にありません。

| フィールド | openapi.yaml | バックエンド | フロントエンド |
|-------|-------------|---------|----------|
| `hash` | あり | なし | なし |
| `title` | なし | `Optional[str]` | `string \| null` |

### 6. OpenAPI `TrustLog.fuji` の必須/任意不一致

| レイヤー | 制約 |
|-------|-----------|
| **openapi.yaml** (L125) | `required` に `fuji` を含む |
| **バックエンド** `schemas.py` (L228) | `fuji: Optional[Dict[str, Any]] = None` |
| **フロントエンド** `decision.ts` (L64) | `fuji?: Record<string, unknown> \| null` |

バックエンド・フロントエンドとも `fuji` を任意扱いしていますが、OpenAPI 仕様では必須です。厳密な OpenAPI バリデーションを行うクライアントで検証失敗につながる可能性があります。

### 7. BFF ルートポリシーが一部バックエンドエンドポイントを未カバー

BFF プロキシ（`route-auth.ts`）では 9 ルートに対してのみポリシーが定義されています。`/v1/metrics`、`/v1/system/halt`、`/v1/report/*`、`/v1/memory/*`、`/v1/fuji/validate` などはポリシー未定義のため、バックエンドに存在していても BFF 経由では 401/403 になる可能性があります。

意図的（これらはバックエンド直アクセス想定）かもしれませんが、文書化が必要です。

---

## 軽微な課題（参考）

### 8. フロントエンドで `ai_disclosure` と `regulation_notice` が optional 扱い

`decision.ts`（L98-100）では `ai_disclosure` と `regulation_notice` に `?`（optional）が付いていますが、バックエンドはデフォルト値付きで常にこれらを含めます。`isDecideResponse` バリデータもこれらを検証していません。実行時の問題にはなりにくいですが、TypeScript 型はより厳密にできます。

### 9. リスクページが合成データのみを使用

リスクページ（`app/risk/page.tsx`）はすべてのデータをクライアント側でランダム生成しており、バックエンド API を呼び出していません。デモ/可視化としては問題ありませんが、実データを想定するなら API 連携が必要です。

### 10. フロントエンド型定義に `DecideResponse.coercion_events` がない

バックエンドは `DecideResponse` に `coercion_events` を含みます（`exclude=True` で JSON から除外）。そのためフロントエンドに見えない現状は妥当です。万一漏れた場合でも、フロントエンド側の `[key: string]: unknown` インデックスシグネチャで受け止められます。対応不要ですが、留意点として記載します。

### 11. `Gate` と `GateOut` の命名差

バックエンドの Pydantic モデル名は `Gate`（schemas.py L419）、フロントエンドの TypeScript インターフェース名は `GateOut`（decision.ts L47）です。フィールドは同一で、機能的な問題はありません。

### 12. openapi.yaml の `Option` スキーマに `score` と `score_raw` がない

OpenAPI の `Option` スキーマ（L61-69）には `id`、`title`、`description` しかありません。一方、バックエンド `Option`/`Alt` モデルとフロントエンド `DecisionAlternative` には `score`、`score_raw`、`world`、`meta` が含まれます。

---

## 整合性マトリクス

| 項目 | バックエンド ↔ フロントエンド | バックエンド ↔ OpenAPI | フロントエンド ↔ OpenAPI |
|------|:------------------:|:-----------------:|:------------------:|
| `/v1/decide` URL パス | OK | OK | OK |
| DecideRequest フィールド | OK | 不一致 | 不一致 |
| DecideResponse フィールド | OK | 不一致 | 不一致 |
| DecisionStatus 列挙値 | OK | OK | OK |
| EvidenceItem フィールド | OK | 不一致 | 不一致 |
| TrustLog フィールド | OK | 不一致（required） | 不一致 |
| Gate/GateOut フィールド | OK | N/A（未定義） | N/A |
| 認証方式 | OK（BFF プロキシ） | OK | N/A |
| エラーハンドリング | OK | N/A | N/A |
| SSE イベント | OK | N/A（未定義） | N/A |

---

## 推奨事項

1. **優先度 1:** 実際のバックエンドスキーマに合わせて `openapi.yaml` を更新する。現在の主要な不整合源は OpenAPI 仕様です。フロントエンドとバックエンド間は概ね同期されています。

2. **優先度 2:** BFF プロキシから意図的に除外しているバックエンドエンドポイントと、その理由を文書化する。

3. **優先度 3:** 将来の乖離防止のため、OpenAPI 仕様から TypeScript 型を生成する（またはその逆）運用を検討する。

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
| `frontend/app/governance/page.tsx` | ガバナンスページ |
| `frontend/app/audit/page.tsx` | 監査ページ |
| `frontend/app/risk/page.tsx` | リスクページ |
| `frontend/components/live-event-stream.tsx` | SSE クライアント |
| `frontend/middleware.ts` | Next.js ミドルウェア |
