# CODE REVIEW 2026-02-15 (Agent)

## 対象
- `veritas_os/api/dashboard_server.py`
- `veritas_os/tools/github_adapter.py`
- `veritas_os/api/server.py`

## サマリ
- 重大なクラッシュバグは今回の範囲では未検出。
- ただし、運用時に問題化しやすい **認証運用の不整合 2件** と、設計上の注意点 1件を確認。

## 指摘事項

### 1) [Medium] ダッシュボードの自動生成パスワードが運用で再現不能になりやすい
**該当箇所**: `veritas_os/api/dashboard_server.py`

- `DASHBOARD_PASSWORD` が未設定の場合、ランダム値を生成して認証に使う実装。
- ただしその値は表示しない方針のため、オペレーターが値を取得できない。
- `uvicorn --workers N` のようなマルチワーカ構成では、ワーカごとに異なるパスワードが生成され、認証が不安定になる可能性がある。

**影響**
- 「ログインできない/たまに失敗する」という運用障害になりうる。
- セキュリティ意図（平文表示しない）は妥当だが、可用性が落ちる。

**推奨対応**
- 本番では `DASHBOARD_PASSWORD` を必須化（未設定時は起動失敗）する。
- 開発専用モードのみ自動生成を許可する。

---

### 2) [Low-Medium] GitHubトークンを import 時に固定読み込みしている
**該当箇所**: `veritas_os/tools/github_adapter.py`

- `GITHUB_TOKEN = os.environ.get(... )` をモジュールロード時に1回だけ評価。
- 実行中にトークンをローテーションしても、プロセス再起動まで反映されない。

**影響**
- 長時間稼働プロセスで、失効済みトークンを使い続ける。
- インシデント対応（鍵ローテーション）の即時性が落ちる。

**推奨対応**
- リクエストごとに環境変数を読む関数（例: `_get_github_token()`）へ置換。

---

### 3) [Note] APIキー解決ロジックの互換フォールバックは運用規約を明示した方がよい
**該当箇所**: `veritas_os/api/server.py`

- `_get_expected_api_key()` は `VERITAS_API_KEY` 未設定時、`API_KEY_DEFAULT`（テスト互換）→ `cfg.api_key` へフォールバックする。
- 実装意図は妥当だが、本番で「どの経路のキーが有効化されるか」が運用者に伝わりにくい。

**影響**
- 監査や障害調査時に、認証ソースの特定が遅れる可能性。

**推奨対応**
- 起動時に「どの経路でキーを採用したか」を安全に（値は秘匿して）INFOログ出力する。

## セキュリティ警告
- ダッシュボード認証情報を環境変数で明示設定しない運用は、可用性・運用品質の両面でリスク。
- GitHubトークンの即時ローテーションが必要な運用では、現行の import 時固定読み込みは不十分。

## 参考実行コマンド
- `rg -n "shell=True|yaml.load\(|pickle.load\(|eval\(|exec\(|os.system\(|subprocess.Popen\(|subprocess.run\(" veritas_os --glob '!**/tests/**'`
- `sed -n '1,140p' veritas_os/api/dashboard_server.py`
- `sed -n '340,430p' veritas_os/api/dashboard_server.py`
- `sed -n '1,220p' veritas_os/tools/github_adapter.py`
- `sed -n '520,690p' veritas_os/api/server.py`
