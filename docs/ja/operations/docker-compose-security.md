# Docker Compose セキュリティノート

> 英語版が正本であり、日本語版は補助説明です。

## 1. 目的

この文書は VERITAS OS の Docker Compose におけるローカル認証情報の扱いを定義します。

## 2. なぜ認証情報を明示必須にするのか

`docker-compose.yml` は、意図的にデフォルトの DB パスワードおよび admin BFF トークンを提供しません。既知の弱い値での誤起動を防ぐためです。

## 3. 必須の `.env` 設定

1. `.env.example` を `.env` にコピーします。
2. すべての `CHANGE_ME` を置き換えます。
3. 次の値を明示設定します。
   - `VERITAS_DB_PASSWORD`
   - `VERITAS_DATABASE_URL`
   - `VERITAS_BFF_SESSION_TOKEN`
   - `VERITAS_BFF_AUTH_TOKENS_JSON`

`.env` はコミットしないでください。

## 4. ローカル専用シークレットの生成

ローカル検証用に十分にランダムな値を利用し、共有環境へ再利用しないでください。

## 5. やってはいけないこと

- プレースホルダー値のまま compose を起動しない。
- ローカル compose の秘密情報を staging/production で使い回さない。
- 実シークレットをコミットしない。

## 6. 本番境界

Compose は、別途レビューがない限り local / 制御された PoC 用です。本番では適切に managed secrets と managed database を使用してください。これは本番SLAを意味しません。

## 7. トラブルシューティング

起動前に compose が失敗する場合は `.env` の必須変数不足を確認し、`VERITAS_BFF_SESSION_TOKEN` が `VERITAS_BFF_AUTH_TOKENS_JSON` のキーと一致することを確認してください。
