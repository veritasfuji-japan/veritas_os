# UI Monorepo Quickstart

## frontend だけをローカル起動

```bash
pnpm install
pnpm --filter frontend dev
```

> `http://localhost:3000` で起動します。

## backend 接続用の環境変数

`frontend/.env.local` を作成し、API ベース URL を設定してください。

```env
VERITAS_API_BASE_URL=http://localhost:8000
```

## 最低限の開発コマンド

```bash
# frontend 開発サーバー
pnpm --filter frontend dev

# frontend lint
pnpm --filter frontend lint

# workspace 全体の型チェック
pnpm -r typecheck

# workspace 全体のテスト
pnpm -r test
```

## Decision Console の公開出力表示ルール

- `gate_decision`: FujiGate によるゲート判定（安全境界）。
- `business_decision`: 案件状態（承認/保留/却下/要審査）。
- `next_action`: 次に実行すべき行動提案（案件状態とは別物）。
- `required_evidence`: 判定に必要な証拠キー一覧。
- `human_review_required`: 人手審査必須フラグ。

**重要:** `gate_decision=allow` は「案件承認」ではなく「応答出力を継続可能」の意味です。UI では承認語として表示しないでください。

### 金融ケース UI フィクスチャ

- Mission Control Console 用の金融サンプルは `frontend/features/console/fixtures/financial-case.ts` を利用してください。
- 本フィクスチャは `financial.high_risk_wire_transfer` 想定で、`required_evidence` / `missing_evidence` / `next_action` / `human_review_required` の視認回帰をテストします。

## Mission Control pre-bind governance vocabulary

- Mission Control の pre-bind governance snapshot は `frontend/components/dashboard-types.ts` の shared frontend contract を参照してください。
- `participation_state` / `preservation_state` / `intervention_viability` / `concise_rationale` / `bind_outcome` は backend vocabulary をそのまま表示する契約です。
- Mission Control は bind outcome だけでなく pre-bind state を timeline で扱うため、component-local 型ではなく shared type (`PreBindGovernanceSnapshot`) を利用してください。
- Mission Control の backend-fed main path は `frontend/app/mission-control-ingress.ts` の `loadMissionControlIngressPayload` です。`/api/veritas/v1/report/governance` から governance feed を取得し、`mapGovernanceFeedToIngressPayload` で ingress contract に明示マッピングします。
- `frontend/app/api/veritas/v1/report/governance/route.ts` が governance feed endpoint の責務を持ち、backend の `/v1/report/governance` を server-side API key 付きで取得して shared vocabulary (`governance_layer_snapshot` / `pre_bind_governance_snapshot`) を保ったまま返します。
- Mission Control の live ingress 層は `frontend/components/mission-control-container.tsx` です。container が page loader 由来 payload を受け取り、`frontend/components/mission-governance-adapter.ts` の `resolveMissionGovernanceSnapshot` を経由して shared contract に正規化します。
- `resolveMissionGovernanceSnapshot` は `governance_layer_snapshot`（主経路）→ `pre_bind_governance_snapshot`（互換経路）→ render safety fallback（安全経路）の順で解決します。fallback は render safety 専用であり、live verification 完了を示しません。
- `frontend/components/mission-page.tsx` は adapter/container で解決済みの shared contract を受け取って render する責務に限定し、将来の server-side hydration・polling・streaming 追加時の接続点を固定します。

### Mission Control governance feed main path (repo-verifiable)

- Main path endpoint は `GET /api/veritas/v1/report/governance`（`frontend/app/api/veritas/v1/report/governance/route.ts`）です。
- 経路は `frontend/app/page.tsx` → `frontend/app/mission-control-ingress.ts` → `frontend/components/mission-control-container.tsx` → `frontend/components/mission-page.tsx` です。
- `MissionPage` は presentational component のまま維持し、data ingress は保持しません。
- endpoint unavailable 時は fallback snapshot を使う safety path を維持します。
- 回帰テストは以下で追跡できます。
  - route contract: `frontend/app/api/veritas/v1/report/governance/route.test.ts`
  - ingress mapping: `frontend/app/mission-control-ingress.test.ts`
  - container fallback/main selection: `frontend/components/mission-control-container.test.tsx`
  - page integration(main + fallback): `frontend/app/page.integration.test.tsx`
  - shared vocabulary drift regression: `frontend/components/mission-governance-adapter.test.ts`
- full frontend E2E (`frontend/e2e/mission-control-governance-feed.spec.ts`) は browser 相当で `GET /api/veritas/v1/report/governance` を route interception し、main path（backend payload 到達）と endpoint unavailable fallback path（safety snapshot 描画）をそれぞれ固定します。
- 役割分担は「route/ingress/container/page integration が層内契約を検証」「full frontend E2E が route → ingress → container → page の end-to-end 到達性と画面語彙維持を検証」です。


## Docker Compose で一括起動

```bash
cp .env.example .env
docker compose up --build
```

- frontend: `http://localhost:3000`
- backend: `http://localhost:8000`
- compose では frontend が `VERITAS_API_BASE_URL=http://backend:8000` を使用します。
- `NEXT_PUBLIC_*` で API 接続先を公開しないでください。production では BFF が fail-closed します。

> 秘密情報は `docker-compose.yml` に直書きせず、`.env` 側で上書きしてください。
