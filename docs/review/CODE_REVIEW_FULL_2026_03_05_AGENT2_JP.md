# 全コードレビュー（2026-03-05, Agent）

## 実施範囲
- バックエンド: `veritas_os/` 全体
- フロントエンド: `frontend/` 全体
- 補助: 主要スクリプト/設定/既存テスト

## 実行した検証
1. `ruff check veritas_os` → **pass**
2. `pytest -q` → **2697 passed, 3 skipped**
3. セキュリティ観点の静的走査（`rg` による危険API/秘密情報パターン確認）

## 総合評価
- **品質**: 高い（テストカバレッジが広く、lint clean）
- **安定性**: 高い（回帰を示す失敗なし）
- **セキュリティ**: 全体として配慮あり。ただし運用時に注意すべきポイントが 2 件

## 指摘事項（優先度順）

### 1) [Medium] フロントのリクエストサイズ上限が「文字数」ベース
- 対象: `frontend/app/api/veritas/[...path]/route.ts`
- 現状: `MAX_PROXY_BODY_BYTES` は bytes を想定した定数名ですが、判定は `body.length`（UTF-16コードユニット数）を使っています。
- リスク: マルチバイト文字を含む payload で実バイト数とズレるため、想定より大きい request を通す/止める可能性があります。
- 根拠:
  - `MAX_PROXY_BODY_BYTES` 定義【F:frontend/app/api/veritas/[...path]/route.ts†L6-L7】
  - 判定ロジック `if (body.length > MAX_PROXY_BODY_BYTES)`【F:frontend/app/api/veritas/[...path]/route.ts†L85-L89】
- 推奨:
  - `new TextEncoder().encode(body).length` でバイト長を評価する。

### 2) [Medium] SSE の query API key 許可フラグは運用ミス時に漏えい面積を拡大
- 対象: `veritas_os/api/server.py`
- 現状: 既定では禁止だが `VERITAS_ALLOW_SSE_QUERY_API_KEY=1` で query API key を受け入れます。
- リスク: URL 経由のキーはアクセスログ・監視URL・ブラウザ履歴へ残る可能性があり、資格情報漏えいリスクが上がります。
- 根拠:
  - 認証ポリシー説明【F:veritas_os/api/server.py†L938-L946】
  - query key 許可時の warning ログ【F:veritas_os/api/server.py†L957-L963】
- 推奨:
  - 本番でフラグを常時 `0` 固定。
  - 一時有効化時は WAF/ログマスキング/短命キーをセットで適用。

## 良好ポイント（確認できた点）
- API proxy 側で許可パスを明示制限し、unsafe segment を遮断している。【F:frontend/app/api/veritas/[...path]/route.ts†L13-L17】【F:frontend/app/api/veritas/[...path]/route.ts†L25-L57】
- サーバ側の SSE 認証にヘッダ優先 + 比較時 `compare_digest` を使用している。【F:veritas_os/api/server.py†L955-L972】
- benchmark スクリプトは `yaml.safe_load` を使っており、unsafe load を避けている。【F:veritas_os/scripts/run_benchmarks_enhanced.py†L68-L71】

## 変更不要と判断した事項
- Planner / Kernel / Fuji / MemoryOS の責務境界を壊す設計変更は今回は不要。
- 現時点では「即時修正必須（High/Critical）」の欠陥は未検出。

## 追跡提案（任意）
- 次回リリース前にフロント API proxy のサイズ計測を bytes 基準へ統一。
- 運用 Runbook に `VERITAS_ALLOW_SSE_QUERY_API_KEY` の禁止ポリシーを明文化。

## 対応状況（2026-03-05 追記）

### 対応済み: 1) フロントのリクエストサイズ上限が「文字数」ベース
- 変更対象: `frontend/app/api/veritas/[...path]/route.ts`
- 対応内容:
  - UTF-8 バイト長を正確に計測する `getBodySizeBytes` を追加。
  - 上限判定を `body.length` から `getBodySizeBytes(body)` に置換。
- 追加テスト: `frontend/app/api/veritas/[...path]/route.test.ts`
  - ASCII 文字列のバイト長が文字数と一致することを確認。
  - 日本語・絵文字などマルチバイト文字で UTF-8 バイト長を正しく計測することを確認。

### 未対応（運用ポリシー事項）: 2) SSE query API key 許可フラグ
- 理由:
  - 本指摘はコード修正よりも運用ポリシー（本番で `VERITAS_ALLOW_SSE_QUERY_API_KEY=0` を徹底）に依存するため。
- セキュリティ警告:
  - `VERITAS_ALLOW_SSE_QUERY_API_KEY=1` を有効化すると、URL 経由で資格情報がログ/履歴等へ露出するリスクがあります。短時間・限定環境以外での有効化は避けてください。
