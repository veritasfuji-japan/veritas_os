# フロントエンド / バックエンド整合性 精密レビュー（2026-03-30）

## 1. 対象と観点

- 対象: `frontend/` の BFF 経由 API 利用、`veritas_os/api` の実ランタイムルート、`openapi.yaml` の公開契約。
- 観点:
  1. フロントエンド呼び出し経路と BFF 許可行列の整合。
  2. BFF 許可行列と FastAPI 実装ルートの整合。
  3. FastAPI 実装ルートと OpenAPI 契約の整合。
  4. セキュリティ上の不整合・運用上の警戒点。
- 制約確認: Planner / Kernel / Fuji / MemoryOS の責務境界を跨ぐ実装変更は行わず、レビューのみ実施。

## 2. レビュー手法（実施コマンド）

- `python` で `frontend` から `/api/veritas/v1/*` 呼び出し箇所を抽出。
- `python` で `veritas_os.api.server.app.routes` から実ルートを抽出。
- `python` で `openapi.yaml` の `paths` を突合。
- 既存回帰テスト `veritas_os/tests/test_openapi_spec.py` を実行。

## 3. 整合性判定サマリ

### 3.1 フロントエンド呼び出し経路

主要な UI 側 API 利用は以下で確認:

- `/api/veritas/v1/decide`
- `/api/veritas/v1/events`
- `/api/veritas/v1/compliance/config`
- `/api/veritas/v1/governance/policy`
- `/api/veritas/v1/trust/logs`
- `/api/veritas/v1/trust/{request_id}`（動的）

結論: 現在の主要画面（Console / Governance / Audit）で利用している経路は、BFF の許可行列と矛盾しない。

### 3.2 BFF 許可行列 vs バックエンド実装

- `route-auth.ts` の `ROUTE_POLICIES` は、`/v1/decide`, `/v1/events`, `/v1/governance/policy`, `/v1/trust/*`, `/v1/compliance/config` などの UI 主要経路をカバー。
- FastAPI 実装側も同系統ルートを提供しており、経路名レベルで重大なズレは見当たらない。

結論: **フロントで使う API の到達可能性は概ね整合**。

### 3.3 OpenAPI 契約 vs 実装

`test_openapi_spec.py` が担保している critical route（governance/trust/prov）の整合は維持されている。

- `/v1/governance/policy`
- `/v1/governance/policy/history`
- `/v1/trustlog/verify`
- `/v1/trust/{request_id}/prov`

結論: **公開契約（OpenAPI）と実装の最重要経路は整合**。

## 4. 精密レビューでの重要指摘

## 指摘A（中）: provenance 経路の BFF 非公開ギャップ

- バックエンドには `/v1/trust/{request_id}/prov` が実装・OpenAPI 定義されている一方、BFF 許可行列には同経路がない。
- そのため、ブラウザ UI から provenance を直接取得する設計へ拡張する場合、現状のままでは到達不可。

推奨:

- Audit UI で provenance 詳細を扱う計画がある場合のみ、BFF に **限定公開（viewer 以上）** を追加検討。
- 追加時は request_id の検証とレスポンス最小化を併せて実施。

## 指摘B（中）: EventSource 運用依存（認証）

- `/v1/events` は `EventSource` 利用で取得しており、ブラウザ仕様上カスタムヘッダを乗せない。
- 現設計は `httpOnly` cookie 前提で妥当だが、同一オリジン/クッキー運用の逸脱時に接続失敗しやすい。

推奨:

- 本番運用 Runbook へ「`__veritas_bff` cookie 前提」の明文化を固定化。
- 401/403 の際は UI 側で再接続ループを抑制する観測を継続。

## 指摘C（低）: OpenAPI 回帰の検証範囲

- 既存テストは critical paths を堅く押さえているが、フロントが常用する全経路の網羅チェックまでは実施していない。

推奨:

- 将来的に `frontend` 使用経路（静的抽出）と OpenAPI/BFF を自動突合する軽量チェック追加を検討。

## 5. セキュリティ警告（必読）

1. **BFF に provenance 経路を追加する場合は過剰露出リスク**に注意。
   - 監査情報は内部メタデータを含む可能性があるため、role と出力項目を最小権限で設計すること。
2. **SSE (`/v1/events`) は cookie 認証依存**のため、Cookie 設定不備があると認可失敗や監視欠落につながる。
3. **BFF 非公開エンドポイント（`/v1/replay/*`, `/v1/decision/replay/*`, `/v1/ws/trustlog`）を UI から迂回呼び出ししないこと。**
   - 署名・鍵管理・内部用途前提の境界を崩すと重大なセキュリティ事故につながる。

## 6. 総合評価

- 判定: **整合性は高い（High）**
- 理由:
  - 現行 UI の主要 API は BFF / FastAPI / OpenAPI の3層で一致。
  - 認証境界は BFF allowlist で明示され、危険経路は意図的に除外されている。
- 継続課題:
  - provenance の UI 展開計画がある場合の BFF 公開方針を明文化。
  - OpenAPI 契約検証を「critical path 以外」に段階拡張。

## 7. 2026-03-30 改善実施（本レビュー対応）

無駄な機能追加は避け、指摘C（OpenAPI 回帰の検証範囲）に限定して以下を実施。

- `scripts/quality/check_frontend_api_contract_consistency.py` を追加。
  - `frontend/` の静的な `/api/veritas/v1/*` 利用（`veritasFetch` / `EventSource`）を抽出。
  - 抽出した経路・メソッドを BFF 許可行列（`route-auth.ts`）と OpenAPI（`openapi.yaml`）へ自動突合。
  - 不一致時に CI で失敗させ、フロント/BFF/OpenAPI のドリフトを早期検知。
- `Makefile` の `quality-checks` に本チェックを組み込み。
- `veritas_os/tests/test_frontend_api_contract_consistency.py` にユニットテストを追加。

セキュリティ補足:
- 本改善は「未許可経路の BFF 露出」を防ぐ監視強化であり、BFF 境界を緩める変更は含まない。
- なお provenance 経路（`/v1/trust/{request_id}/prov`）を今後 BFF 公開する場合は、引き続き最小権限・最小レスポンス原則を必須とする。

### 7.1 2026-03-30 追加改善（この依頼で実施）

上記の自動突合チェックに対し、実運用で使われる `fetch(...)` の抽出漏れを最小範囲で補強した。

- `scripts/quality/check_frontend_api_contract_consistency.py`
  - `veritasFetch` / `EventSource` に加えて、`fetch("/api/veritas/v1/...")` の直接呼び出しを抽出対象に追加。
  - `const streamUrl = "/api/veritas/v1/events"` のような **定数経由の URL 参照** を `fetch(streamUrl)` / `veritasFetch(streamUrl)` / `EventSource(streamUrl)` で解決できるよう改善。
- `veritas_os/tests/test_frontend_api_contract_consistency.py`
  - 直接 `fetch` と定数経由 URL の両方を検証するテストを追加し、回帰を防止。

セキュリティ補足:
- 本変更は検出精度の向上のみであり、BFF の許可境界や認可ロジック自体は変更していない。
- したがって、権限昇格・経路露出の新規リスクは増やしていない（監視の見落としリスクを低減）。

### 7.2 2026-03-30 追加改善（最小差分）

無駄な機能追加を避け、既存チェックの抽出精度に限定して最小改善を実施。

- `scripts/quality/check_frontend_api_contract_consistency.py`
  - `const apiUrl = baseUrl; const endpoint = apiUrl;` のような **URL 定数エイリアス連鎖** を解決し、`fetch(endpoint)` でも `/api/veritas/v1/*` 経路を抽出できるよう改善。
  - 実装は 1 ファイル内の静的代入のみを対象とし、責務境界（Planner / Kernel / Fuji / MemoryOS）を跨ぐ変更は行っていない。
- `veritas_os/tests/test_frontend_api_contract_consistency.py`
  - URL 定数の one-hop / chained alias を経由した `fetch` 呼び出しを検証するテストを追加。

セキュリティ補足:
- 本改善は「検査の見落とし低減」のみを目的とし、BFF の許可行列・認可判定・公開 API の挙動自体は不変。
- そのため新規の経路露出は発生しないが、将来 alias が動的生成に拡大した場合は静的解析の限界を越えるため、過信せず実行時監査を併用すること。

### 7.3 2026-03-30 追加改善（最小・運用安定化）

無駄な機能追加を避け、指摘B（`/v1/events` の認証運用依存）に限定して最小改善を実施。

- `frontend/lib/managed-sse.ts` を追加。
  - `fetch(..., credentials: "same-origin")` による事前疎通確認を行い、`401/403` の場合は **60秒の待機** を挟んで再試行する制御を共通化。
  - `EventSource` のエラー時は指数バックオフで再接続し、無制御な再接続ループを抑制。
- `frontend/app/console/page.tsx`
  - 既存の直接 `EventSource` 接続を上記共通制御へ置換。
- `frontend/features/console/components/eu-ai-act-governance-dashboard.tsx`
  - 同様に直接 `EventSource` 接続を共通制御へ置換。
- `frontend/lib/managed-sse.test.ts`
  - `401` 時に待機してから再接続すること、`withCredentials: true` で接続することを検証するテストを追加。

セキュリティ補足:
- 本変更は cookie 認証前提（`__veritas_bff`）を壊さず、未認証時の過剰な再試行を抑える安定化である。
- BFF の許可行列・公開経路は変更していないため、API 露出面の増加はない。

### 7.4 2026-03-31 追加改善（CI 回帰修正）

`frontend` の品質ゲートで 1 件失敗していたため、最小差分でテストのモック順序を実運用の呼び出し順へ合わせた。

- `frontend/app/governance/page.test.tsx`
  - `EUAIActGovernanceDashboard` 初期化時の `compliance/config` 取得に加え、
    `managed-sse` 導入で追加された `/api/veritas/v1/events` の事前プローブ呼び出しをモックに反映。
  - その後に `governance/policy`（不正 payload）を返すようにし、
    期待どおり「レスポンス検証エラー」を検証できるよう修正。

セキュリティ補足:
- 本修正はテストの整合性のみを対象としており、実行時の認可・公開 API・BFF 境界は変更していない。
