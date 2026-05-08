# Docker Compose セキュリティノート

> 英語版が正本であり、日本語版は補助説明です。

`docker-compose.yml` は DB password / admin BFF token のデフォルト値を提供しません。

- `.env.example` を `.env` にコピーする
- `CHANGE_ME` をすべて置き換える
- `.env` をコミットしない
- local compose secrets を staging / production で使い回さない
- 本番では managed secrets / managed database を使う
- これは本番SLAではない、また本番ハードニング完了を意味しない
