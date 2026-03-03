# UI/UX 各ページのプレビュー手順

## 1. フロントエンドを起動

```bash
pnpm --filter frontend dev --hostname 0.0.0.0 --port 3000
```

## 2. ブラウザで各ページを確認

- ホーム: `http://localhost:3000/`
- Console: `http://localhost:3000/console`
- Audit: `http://localhost:3000/audit`
- Governance: `http://localhost:3000/governance`
- Risk: `http://localhost:3000/risk`

## 3. スクリーンショットを一括取得（任意）

Playwright を使う場合は、ページにアクセスして `full_page=True` のスクリーンショットを取得すると、
長いダッシュボードでも見切れにくく確認できます。

## セキュリティ注意

- `next dev` は開発サーバーです。本番用途で公開しないでください。
- `--hostname 0.0.0.0` はローカルネットワークからアクセス可能になります。必要がない場合は `localhost` のみにしてください。
