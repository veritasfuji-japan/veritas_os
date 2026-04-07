# 致命的バグ観点レビュー（2026-03-02）

## 対象
- API サーバー認証・イベント配信まわり
- 既存の責務境界・セキュリティチェック
- 主要回帰テスト（Kernel / Memory / Trust Log API）

## 実施コマンド
- `pytest -q veritas_os/tests/test_kernel.py veritas_os/tests/test_memory_engine.py veritas_os/tests/test_trust_log_api.py`
- `python scripts/security/check_next_public_key_exposure.py`
- `python scripts/architecture/check_responsibility_boundaries.py`

## 結論（要約）
- **即時クラッシュ級（サービス停止を直接引き起こす）致命的バグは、このスキャン範囲では未検出。**
- ただし、以下 2 点は運用条件次第で重大インシデント化しうるため、優先修正を推奨。

---

## 重要指摘 1（High / Security）
### SSE 認証で `api_key` クエリ許容によりキー漏えい面が広い

`/v1/events` は `require_api_key_header_or_query` を利用し、`X-API-Key` ヘッダだけでなく `api_key` クエリでも認証可能。
クエリキーはアクセスログ・リバースプロキシログ・ブラウザ履歴・監視URLに残りやすく、**APIキー漏えいの実務リスク**が高い。

- 認証関数（query 受理）: `veritas_os/api/server.py` L861-L875
- SSE エンドポイント: `veritas_os/api/server.py` L2041-L2043

**推奨対応**
1. デフォルトをヘッダ認証のみへ変更（query は feature flag で明示 opt-in）。
2. query 使用時は警告ログ + 短期失効トークンへ限定。
3. 既存クライアント移行期間を設け、段階的に query 認証を廃止。

---

## 重要指摘 2（Medium-High / Reliability）
### import 時に再帰 `threading.Timer` を起動（停止フックなし）

`_schedule_nonce_cleanup()` が import 時に即実行され、再帰的に Timer を生成。
明示停止フックがないため、再読込・マルチワーカー・テスト実行形態によってはバックグラウンドスレッドが増殖し、**運用時の不安定化要因**になる。

- タイマー再帰処理: `veritas_os/api/server.py` L954-L964
- import 時起動: `veritas_os/api/server.py` L966-L967

**推奨対応**
1. FastAPI lifespan (`startup`/`shutdown`) に移し、終了時に確実 cancel。
2. 単一インスタンスガード（重複起動防止）。
3. 可能なら非同期タスク化し、アプリケーションライフサイクル管理下に統合。

---

## 参考（今回パスした検証）
- 主要回帰テスト（Kernel / Memory / Trust Log API）: 10件 pass
- public exposure 簡易チェック: pass
- 責務境界チェック: pass

## 責務境界への適合
本レビューは監査ドキュメント追加のみで、Planner / Kernel / Fuji / MemoryOS の責務変更は行っていない。
