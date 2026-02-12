# Governance 3分デモ台本

## 目的
Governance統制プレーンで「設定 → 実行 → 監査」の一連を3分で確認する。

## 事前準備
- APIサーバ起動: `uvicorn veritas_os.api.server:app --host 0.0.0.0 --port 8000`
- Frontend起動: `pnpm --filter frontend dev --port 3000`
- APIキーを `NEXT_PUBLIC_VERITAS_API_KEY` と `VERITAS_API_KEY` に設定

## デモフロー（3分）
1. **/console (60秒)**
   - 危険プリセットを実行し、Pipeline Visualizer の **FUJI** ステージを提示。
   - 「統制が推論と同時に走っている」ことを説明。

2. **/audit (60秒)**
   - 直前requestの `request_id` を検索。
   - TrustLogの `stage`, `created_at`, `chain_ok` を確認。
   - 「後追い監査可能な統制ログ」を説明。

3. **/governance (60秒)**
   - `FUJI rule switch` を enabled/disabled 切替。
   - `risk_threshold`, `auto stop conditions`, `log retention days`, `audit intensity` を更新。
   - `Diff Preview (before/after)` で変更差分を確認。

## 成功条件
- consoleでFUJI表示が確認できる
- auditで対象requestの監査証跡が確認できる
- governance更新後にafter差分が反映される
