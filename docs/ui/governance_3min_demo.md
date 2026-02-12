# Governance 3分デモ台本

## 目的
Governance統制プレーンで、`/console` → `/audit` → `/governance` の一連フローを3分で実演する。

## 事前準備（30秒）
1. Backend を起動: `uvicorn veritas_os.api.server:app --host 0.0.0.0 --port 8000`
2. Frontend を起動: `pnpm --filter frontend dev --port 3000`
3. APIキーを確認（`VERITAS_API_KEY` と同じ値をUI入力）

## デモ手順（2分）

### 1) /console でプリセット実行（40秒）
- `Decision Console` を開く。
- 危険プリセットを1つ押して実行。
- `fuji/gate` セクションで `rejected` と理由を確認。

### 2) /audit で request_id を検索（40秒）
- `TrustLog Explorer` を開く。
- 最新ログをロード。
- request_idをコピーして検索。
- `chain_ok` と `verification_result` を提示。

### 3) /governance で policy 更新（40秒）
- `Governance Control` を開く。
- ポリシー取得後、以下を変更:
  - FUJI enable/disable
  - リスク閾値
  - 自動停止条件
  - ログ保持期間/監査強度
- `差分プレビュー` の before/after を確認。
- 更新ボタンで反映。

## クロージング（30秒）
- CIで `typecheck/lint/unit/e2e/a11y` が自動検証されることを説明。
- 現状はファイル保存だが、API契約を固定しているためDB移行しやすい構成であることを説明。

## セキュリティ注意
- `governance.json` は改ざん対策として将来は署名/監査ログ連携が必須。
- APIキーはUI側で最小表示に留め、平文の保存はしない。
