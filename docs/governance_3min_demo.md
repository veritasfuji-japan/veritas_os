# Governance 3分デモ台本

## 目的
Governance統制プレーンが、Console / Audit / Governanceを通して一貫して機能することを3分で示す。

## 事前準備
1. APIサーバー起動
2. Frontend起動
3. `X-API-Key` を入力できる状態にする

## デモ手順（3分）
1. **/console（約60秒）**
   - 危険プリセットを実行する。
   - `fuji/gate` セクションで拒否判定（例: `rejected`）を確認する。

2. **/audit（約60秒）**
   - `最新ログを読み込み` を実行。
   - Consoleで発生した `request_id` を検索して、監査証跡が追跡可能であることを示す。

3. **/governance（約60秒）**
   - `現在のpolicyを取得`。
   - FUJI有効/無効、リスク閾値、自動停止条件、ログ保持期間、監査強度を更新。
   - 差分プレビュー（before/after）で反映内容を確認する。

## 期待される結果
- ConsoleでFUJI関連の判定が表示される。
- Auditで該当requestのトレースが可能。
- Governanceで更新したpolicyが即時反映され、差分を確認できる。
