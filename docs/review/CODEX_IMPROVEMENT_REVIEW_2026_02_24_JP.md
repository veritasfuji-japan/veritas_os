# CODEX 改善再レビュー（2026-02-24, JP）

## 結論

前回の改善提案（C-1/C-2/C-3、M-13/M-14/M-15 など）に対して、主要項目は**概ね修正済み**です。  
本再レビュー時点では、重大な新規欠陥（即時停止レベル）は確認していません。

## 再レビュー結果サマリー

| ID | 項目 | 再評価 | コメント |
|---|---|---|---|
| C-1 | dataset_writer の並行書き込み | ✅ 改善済み | `RLock` と `atomic_append_line` により排他・耐久性が強化。 |
| C-2 | `atomic_write_npz` の fsync 不足 | ✅ 改善済み | `np.savez` 後の `fsync` とディレクトリ `fsync` が追加。 |
| C-3 | リクエストサイズ制限欠如 | ✅ 改善済み | `MAX_REQUEST_BODY_SIZE` と 413/400 応答を実装。 |
| H-1 | `builtins.MEM` 汚染 | ✅ 改善済み | 明示的に代入削除済み。 |
| H-5 | TrustLog ハッシュ連鎖の不整合 | ✅ 改善済み | 直近ハッシュを JSONL 側から取得する実装に更新。 |
| H-9/H-10/H-11 | TOCTOU（ポリシー/ローテーション周辺） | ✅ 改善済み（限定） | FUJI 側は fd ベース読込 + lock。rotate 側は symlink/path 防御を追加。 |
| M-13 | `/status` の内部情報露出 | ✅ 改善済み | 非デバッグ時は詳細文字列を返さず boolean 化。 |
| M-14 | セキュリティヘッダー不足 | ✅ 改善済み | `X-Frame-Options`, `nosniff`, `CSP`, `HSTS` など追加。 |
| M-15 | `web_search.max_results` 上限なし | ✅ 改善済み | 1〜100 にクランプするサニタイズ関数で制御。 |
| M-16 | LLM Safety API JSON シリアライズ | ✅ 改善済み | `json.dumps(user_payload, ensure_ascii=False)` を使用。 |

## 確認した主な実装ポイント

- `dataset_writer` は `_dataset_lock`（`RLock`）で排他しつつ JSONL 追記。統計/検索でも同ロックを利用。  
- `atomic_write_npz` は temp 保存後にファイル `fsync`、`os.replace`、親ディレクトリ `fsync` を実施。  
- API サーバーは body size 制限ミドルウェアとセキュリティヘッダーミドルウェアを導入。  
- `/status` はデバッグモード制御により、通常運用で内部エラー詳細を露出しない。  
- Web 検索は `max_results` をクランプし、極端値でのリソース消費を抑止。  

## セキュリティ観点の警告（運用上の残課題）

> 以下は「実装修正が不足」というより、**運用・設定・将来対応**として継続的に注意が必要な項目です。

1. **HSTS は HTTPS 前提**  
   開発環境の HTTP では実効しないため、本番では TLS 終端を必須にしてください。

2. **Pickle 互換移行コードは残存**  
   制限付き実装でも攻撃面が 0 にはならないため、期限付きで完全廃止する方針を維持してください。

3. **`Content-Length` 非依存の巨大ボディ対策**  
   現在はヘッダー値チェック中心です。リバースプロキシ（nginx/caddy 等）側の body 上限と併用することで、回避耐性が上がります。

## 追加提案（軽微）

- セキュリティヘッダー群の適用対象（APIのみ/静的配信含む）を設計書に明記。  
- body 上限値を運用プロファイル（dev/stg/prod）別に管理。  
- legacy pickle 廃止日を README / 運用Runbookに明文化。

## 実行した検証

- `pytest -q veritas_os/tests/test_dataset_writer.py veritas_os/tests/test_atomic_io.py veritas_os/tests/test_api_server_extra.py -q`  
  - すべて成功（外部依存ライブラリ由来の Warning のみ）。
- `pytest -q veritas_os/tests/test_web_search_extra.py veritas_os/tests/test_logging_rotate.py veritas_os/tests/test_trust_log.py -q`  
  - すべて成功。

