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
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
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
