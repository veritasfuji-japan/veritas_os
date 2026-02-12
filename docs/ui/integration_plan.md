# UI Integration Plan (Task 1)

## 1. リポジトリ構造（`tree -L 4` 相当の要約）

- ルート直下の主要ディレクトリ
  - `.github/workflows`（CI 定義）
  - `docs/`（設計・調査メモ）
  - `veritas_os/`（実装本体）
- アプリ実装の主要領域（`veritas_os/` 配下）
  - `api/`（FastAPI エンドポイント）
  - `core/`（Planner/Kernel/Fuji/MemoryOS を含むコアロジック）
  - `logging/`（TrustLog 等の監査ログ機能）
  - `tests/`（pytest テスト群）

## 2. backend_root の確定

- **backend_root: `veritas_os/`**
- 根拠:
  - FastAPI app は `veritas_os/api/server.py` の `app = FastAPI(...)` で生成。
  - 公開 API（`/v1/decide` ほか）も同ファイルで直接定義。
  - 意思決定ロジックは `veritas_os/core/pipeline.py` を lazy import して実行。

## 3. FastAPI エントリポイント（uvicorn 起動箇所・app 生成・router 登録）

### 3.1 uvicorn 起動箇所

- 推奨起動コマンド（README）:

```bash
python -m uvicorn veritas_os.api.server:app --reload --port 8000
```

### 3.2 app 生成

- `veritas_os/api/server.py`
  - `cfg = get_cfg()`
  - `app = FastAPI(title="VERITAS Public API", version="1.0.3")`

### 3.3 router 登録

- `include_router(...)` は未使用。
- `@app.get`, `@app.post` で各 API を **直接登録**する構成。

## 4. `/v1/decide` 実装位置と実行フロー

### 4.1 実装位置

- ルーティング: `veritas_os/api/server.py` の `@app.post("/v1/decide")`
- 実処理: `veritas_os/core/pipeline.py` の `async def run_decide_pipeline(...)`

### 4.2 呼び出しフロー

1. API 層 (`server.py`) で `DecideRequest` を受理。
2. `get_decision_pipeline()` で `veritas_os.core.pipeline` を lazy import。
3. `await p.run_decide_pipeline(req=req, request=request)` を実行。
4. 戻り値を `_coerce_decide_payload(...)` で安全整形。
5. `DecideResponse.model_validate(...)` でレスポンス確定（失敗時もフォールバック JSON を返す）。

## 5. `/v1/decide` レスポンス JSON 構造（現行）

`DecideResponse`（`veritas_os/api/schemas.py`）および pipeline のレスポンス組み立てから、主要フィールドは以下。

- 共通メタ
  - `ok`, `error`, `request_id`, `version`
- 意思決定本体
  - `chosen`, `alternatives`, `options`, `decision_status`, `rejection_reason`
- 評価・ガードレール
  - `values`, `telos_score`, `fuji`, `gate`
- 推論素材
  - `evidence`, `critique`, `debate`
- 補助情報
  - `extras`, `plan`, `planner`, `persona`, `memory_citations`, `memory_used_count`, `trust_log`

備考:
- `trust_log` は API スキーマ上 `TrustLog | dict | null` を許容。
- pipeline 内で監査エントリ作成後に TrustLog へ追記するが、レスポンス内 `trust_log` は `raw` 依存で `null` の場合あり。

## 6. FUJI / TrustLog 関連モジュールの特定

### 6.1 FUJI 関連

- 主要実装: `veritas_os/core/fuji.py`
  - `validate_action(...)`
- API 層の呼び出し:
  - `server.py` の `get_fuji_core()` が `veritas_os.core.fuji` を lazy import
  - `/v1/fuji/validate` で `_call_fuji(...)` 経由実行
- `/v1/decide` では `pipeline.py` 内で FUJI 判定結果を `fuji`, `gate` に反映。

### 6.2 TrustLog 関連

- Canonical 実装:
  - `veritas_os/logging/trust_log.py`（append・lock 等）
- API 層:
  - `server.py` の `append_trust_log(...)`（フォールバック実装、json/jsonl 書き込み）
  - `/v1/trust/feedback` は `value_core.append_trust_log(...)` を利用
- pipeline 層:
  - `pipeline.py` で `append_trust_log`, `write_shadow_decide` を呼び出し

## 7. リアルタイム（ログ/イベント発火）の現状

### 7.1 既存実装

- `/v1/decide` 実行時に、best-effort で以下を実施:
  - TrustLog 追記（`append_trust_log`）
  - Shadow ログ書き込み（`write_shadow_decide`）
- 取得系として `/v1/metrics` は存在するが、**ポーリング型**。

### 7.2 未実装（リアルタイム配信）

- WebSocket / SSE / サブスクライブ API は見当たらない。
- UI のリアルタイム更新が必要な場合、以下の順で拡張する。
  1. `GET /v1/events` (SSE) 追加
  2. `decide` 完了時にイベント publish
  3. 監査ログ取得 API（例: `GET /v1/trust/logs?cursor=...`）追加

## 8. ローカル起動方法（現行）

1. 依存インストール
   - `pip install -r requirements.txt`
2. 環境変数設定
   - `OPENAI_API_KEY`
   - `VERITAS_API_KEY`
   - `VERITAS_API_SECRET`（HMAC 用）
3. 起動
   - `python -m uvicorn veritas_os.api.server:app --reload --port 8000`
4. 確認
   - `http://127.0.0.1:8000/docs`

## 9. API 仕様の要点

### 9.1 `POST /v1/decide`

- 認証: `X-API-Key`（必須）
- リクエスト: `DecideRequest`
  - 最低限 `query` を想定
- レスポンス: `DecideResponse`（上記 5章）
- 失敗時:
  - pipeline 取得/実行失敗時は 503 + `{"ok": false, "error": "service_unavailable", ...}`

### 9.2 監査ログ取得 API の有無

- **専用の TrustLog 一覧取得 API は未実装**。
- 近い機能:
  - `GET /v1/metrics`（件数などの集計）
  - ログファイル直接参照（運用者向け、API ではない）

## 10. 既存 CI の有無

- **あり**（GitHub Actions）
  - `.github/workflows/main.yml`
    - lint（ruff, bandit）
    - test（pytest + coverage, Python 3.11/3.12）
  - `.github/workflows/publish-ghcr.yml`
    - GHCR publish 系

## 11. 未整合点 / リスク / 今後の対応方針

1. 型集約方針とのギャップ
   - 現在は Python/Pydantic 中心で、`packages/types` または `shared/types` は未確認。
   - UI 連携時は OpenAPI 生成型 or 単一 shared schema に寄せる必要。

2. 監査ログ API 不足
   - TrustLog は書き込み中心で、UI が直接使える取得 API が不足。
   - 100k ログ表示要件に対し、ページング API（cursor / limit）を追加すべき。

3. リアルタイム配信不足
   - 現状はポーリング前提（`/v1/metrics`）で、更新 <200ms 要件に不利。
   - SSE/WebSocket を最小追加で導入検討。

4. CORS 設定依存
   - `cors_allow_origins` 未設定時は許可 origin が空。
   - UI 別オリジン運用時は config 側で明示設定が必須。

5. セキュリティ注意
   - `VERITAS_API_KEY`, `VERITAS_API_SECRET`, `OPENAI_API_KEY` の漏洩防止を徹底。
   - TrustLog/Shadow ログに機微情報が入る可能性があるため、PII マスキングとアクセス制御を要確認。

---

## 12. 今後タスクの実装原則（この Plan を基準）

- 以降の UI 統合実装は **backend_root=`veritas_os/` を前提**に進める。
- `/v1/decide` の型は `DecideRequest/DecideResponse` を唯一の真実源として扱う。
- 既存責務境界（Planner / Kernel / Fuji / MemoryOS）を越える改変は行わない。
- 監査・リアルタイム要件は API 追加で解決し、既存 decide パイプラインの破壊的変更を避ける。
