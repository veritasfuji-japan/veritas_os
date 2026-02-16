# TASK 10 — 3分デモ台本（Governance Control Plane）

## 目的
Governance API と UI が連動し、
1) Console で FUJI が可視化されること
2) Audit で該当 request を追跡できること
3) Governance で policy 更新と差分確認ができること
を 3 分で実演する。

## 事前準備
- API を起動（`uvicorn veritas_os.api.server:app --host 0.0.0.0 --port 8000`）
- Frontend を起動（`pnpm --filter frontend dev --port 3000`）
- `VERITAS_API_KEY` と `NEXT_PUBLIC_VERITAS_API_KEY` を同じ値に設定

## デモ手順（3分）

### 0:00 - 0:50 Console 実行（FUJI表示）
1. `/console` を開く。
2. `X-API-Key` を入力。
3. 危険プリセットをクリックして実行。
4. `fuji/gate` セクションが表示されることを確認。

トーク例:
- 「ここで FUJI 判定と gate 情報が同時に見えるので、安全統制が意思決定結果と切り離されず追えます。」

### 0:50 - 1:40 Audit 追跡（request検索）
1. `/audit` を開く。
2. 同じ API キーを入力。
3. request_id が取得できた場合は検索、取得できなければ `最新ログを読み込み`。
4. タイムラインと JSON で該当処理を確認。

トーク例:
- 「意思決定の結果だけでなく、監査証跡を時系列で再現できます。」

### 1:40 - 3:00 Governance 更新（反映+差分）
1. `/governance` を開く。
2. `現在のpolicyを読み込み`。
3. FUJI on/off、リスク閾値、自動停止条件、保持期間、監査強度を編集。
4. `policy更新` を押す。
5. 差分プレビューに before/after が表示されることを確認。

トーク例:
- 「統制パラメータは API と UI が同期され、変更差分が即時に可視化されます。」

## セキュリティ留意点
- API キー必須。未設定・不一致時は更新不可。
- Policy はサーバ側で型/範囲バリデーション（閾値0〜1、保持期間1〜3650日など）を実施。
- 現状はファイル保存のため、将来的には DB 化と RBAC を導入する。
