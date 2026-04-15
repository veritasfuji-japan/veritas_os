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
