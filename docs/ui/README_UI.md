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
- `frontend/app/api/veritas/v1/report/governance/route.ts` が governance feed endpoint の責務を持ち、backend の `/v1/governance/live-snapshot` を server-side API key 付きで取得して shared vocabulary (`governance_layer_snapshot` / `pre_bind_governance_snapshot`) を保ったまま返します。
- Mission Control の live ingress 層は `frontend/components/mission-control-container.tsx` です。container が page loader 由来 payload を受け取り、`frontend/components/mission-governance-adapter.ts` の `resolveMissionGovernanceSnapshot` を経由して shared contract に正規化します。
- `resolveMissionGovernanceSnapshot` は `governance_layer_snapshot`（主経路）→ `pre_bind_governance_snapshot`（互換経路）→ render safety fallback（安全経路）の順で解決します。fallback は render safety 専用であり、live verification 完了を示しません。
- `frontend/components/mission-page.tsx` は adapter/container で解決済みの shared contract を受け取って render する責務に限定し、将来の server-side hydration・polling・streaming 追加時の接続点を固定します。

### Mission Control governance feed main path (repo-verifiable)

- Main path endpoint は `GET /api/veritas/v1/report/governance`（BFF）→ backend `GET /v1/governance/live-snapshot`（`frontend/app/api/veritas/v1/report/governance/route.ts`）です。
- 経路は `frontend/app/page.tsx` → `frontend/app/mission-control-ingress.ts` → `frontend/components/mission-control-container.tsx` → `frontend/components/mission-page.tsx` です。
- `MissionPage` は presentational component のまま維持し、data ingress は保持しません。
- endpoint unavailable 時は fallback snapshot を使う safety path を維持します。
- 回帰テストは以下で追跡できます。
  - route contract: `frontend/app/api/veritas/v1/report/governance/route.test.ts`
  - ingress mapping: `frontend/app/mission-control-ingress.test.ts`
  - container fallback/main selection: `frontend/components/mission-control-container.test.tsx`
  - page integration(main + fallback): `frontend/app/page.integration.test.tsx`
  - shared vocabulary drift regression: `frontend/components/mission-governance-adapter.test.ts`
- full frontend E2E (`frontend/e2e/mission-control-governance-feed.spec.ts`) は browser request header (`x-veritas-e2e-governance-scenario`) を使って `GET /api/veritas/v1/report/governance` の deterministic test scenario を起動し、main path（backend payload 到達）と fallback safety path（safety snapshot 描画）をそれぞれ固定します。
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

### Mission Control E2E governance scenario safety

- `e2e_governance_scenario` と `x-veritas-e2e-governance-scenario` は test-only の deterministic scenario 注入です。
- 上記 scenario 注入は `NODE_ENV === "test"` または `VERITAS_ENABLE_E2E_SCENARIOS=1` の明示 opt-in 時のみ有効です。
- production では query/header での scenario injection は無視され、Mission Control は backend-fed governance data を優先します。
- deterministic scenario は UI regression 用フィクスチャであり、production governance data source ではありません。
- `/v1/report/governance` は date-range governance/compliance report 用であり、Mission Control live snapshot source とは役割を分離します。
- backend `/v1/governance/live-snapshot` は latest BindReceipt 由来の bind metadata（`bind_receipt_id` / `execution_intent_id` / `decision_id`）、target metadata（`target_path` / `target_type` / `target_label` / `operator_surface` / `relevant_ui_href`）、reason fields（`bind_reason_code` / `bind_failure_reason` / `failure_category` など）を返し、`bind_summary` が存在する場合は operator-facing artifact summary として利用できます。
- Mission Control UI は上記 live snapshot fields を operator-facing details として表示します（pre-bind source / pre-bind summaries / bind reason / target metadata / check results）。
- `pre_bind_source` は artifact 取得元と fallback 状態を示し、`trustlog_matching_*` は matched、`trustlog_recent_decision` と `latest_bind_receipt` は fallback、`none` は unavailable、`malformed_pre_bind_artifact` と `pre_bind_artifact_retrieval_failed` は degraded source として扱います。
- `pre_bind_detection_summary` / `pre_bind_preservation_summary` / detail fields / check result fields が `null` または `unknown` の場合、Mission Control UI は fake data を生成せず unavailable 表示を維持します。
- 同 endpoint は optional enrichment として pre-bind detection / preservation fields（`pre_bind_source` / `pre_bind_detection_summary` / `pre_bind_preservation_summary` / `pre_bind_detection_detail` / `pre_bind_preservation_detail`）も返します。TrustLog pre-bind artifact 利用時は latest BindReceipt の `decision_id` / `request_id` / `execution_intent_id` と一致する artifact を優先し、`trustlog_matching_decision` → `trustlog_matching_request` → `trustlog_matching_execution_intent` の順で選択します。一致が無い場合のみ `trustlog_recent_decision` に fallback し、さらに TrustLog 側に signal が無い場合は latest BindReceipt payload fallback（`latest_bind_receipt`）を使います。どちらにも signal が無い場合は fake data を作らず `unknown` / `null` を返し、`pre_bind_source`（`trustlog_matching_decision` / `trustlog_matching_request` / `trustlog_matching_execution_intent` / `trustlog_recent_decision` / `latest_bind_receipt` / `none` / `pre_bind_artifact_retrieval_failed` / `malformed_pre_bind_artifact`）で取得元を明示します。
- degraded fallback snapshot は fake success を示さず render safety path です。latest BindReceipt enrichment に失敗しても `/v1/governance/live-snapshot` は 500 ではなく degraded snapshot を返し、`source` に `degraded_artifact_retrieval_failed` / `degraded_invalid_latest_bind_receipt` / `degraded_bind_summary_enrichment_failed` などの理由を載せます。

## Mission Control governance artifact link hardening

- `relevant_ui_href` は backend artifact 由来の untrusted-ish display input として扱います。
- Mission Control UI は `relevant_ui_href` が app 内部 path（例: `/governance`, `/audit?receipt=...`）の場合のみ Link として表示します。
- external URL / protocol 付き URL / malformed href（`\\`, 改行, タブなど）は Link 化せず、plain text または `not available` として表示します。
- unsafe input から fake internal link は生成しません。
- `Governance artifacts` パネル内の `Operator actions` は artifact 由来 metadata を compact に表示します。
- `Open target surface` は `normalizeSafeInternalHref()` で safe internal path と判定できる場合のみ Link 化します。
- `bind_receipt_id` / `decision_id` / `execution_intent_id` は `/audit` route が repository で確認できる場合のみ、`buildAuditArtifactHref()` により `/audit?bind_receipt_id=...` などの safe query link を生成して Link 化します。
- artifact ID は untrusted-ish input として conservative validation（string / trim 後 non-empty / 制御文字禁止 / `^[A-Za-z0-9._:-]+$`）を通過した場合のみ Link 化し、unsafe / malformed ID は Link 化せず `route unavailable` を維持します。
- `pre_bind_source` は source state として表示し、TrustLog 含む未確認 route への fake navigation は生成しません。

## Audit query navigation behavior

- `/audit` は query input を untrusted-ish として扱い、`bind_receipt_id` / `decision_id` / `execution_intent_id` を `^[A-Za-z0-9._:-]{1,128}$` で検証します。
- 無効値（例: `../secret`, `javascript:...`, 改行を含む値）は拒否し、error 表示のみ行い、unsafe query による検索・遷移は行いません。
- query priority は `bind_receipt_id` > `decision_id` > `execution_intent_id` です。複数指定時は最優先 query を workflow focus として consume します。
- `bind_receipt_id` は従来どおり dedicated lookup（governance bind receipt API）を実行し、timeline match があれば select/focus、miss 時は fallback detail を表示します。
- `decision_id` は valid query の場合、timeline 未ロードなら latest logs を自動ロードし、loaded timeline 内で一致する item (`item.decision_id`) を探索します。見つかれば select/focus、見つからなければ not-found trace を表示します。
- `execution_intent_id` は valid query の場合、timeline 未ロードなら latest logs を自動ロードし、loaded timeline 内で `item.execution_intent_id` / `item.metadata.execution_intent_id` / `item.bind_receipt.execution_intent_id` を探索します。見つかれば select/focus、見つからなければ not-found trace を表示します。
- invalid `decision_id` / `execution_intent_id` は reject され、auto-load は実行されません。
- query なしの `/audit` は従来どおり手動の `Load latest logs` 操作で読み込みます。
