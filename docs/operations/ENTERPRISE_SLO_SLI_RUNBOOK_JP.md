# Enterprise SLO/SLI & 運用Runbook（2026-03-06）

## 目的
本ドキュメントは、エンタープライズ運用に必要な SLO/SLI と、障害時の標準運用手順を定義する。
対象は Veritas API（`veritas_os/api`）およびフロント BFF（`frontend/app/api/veritas/[...path]`）。

## 1. SLI 定義

### 1.1 可用性（Availability）
- 指標: `2xx + 4xx` を成功、`5xx` を失敗として 5分窓で計測
- 対象: `/health`, `/v1/decide`, `/v1/fuji/validate`, `/v1/trust/*`
- 収集キー: `service`, `route`, `status_class`, `trace_id`

### 1.2 レイテンシ（Latency）
- 指標: P50 / P95 / P99 の応答時間
- 対象: `/v1/decide`（主監視）、その他主要 API
- 収集キー: `route`, `method`, `status`, `trace_id`

### 1.3 エラーレート（Error rate）
- 指標: `5xx / total_requests`
- 収集キー: `route`, `error_type`, `trace_id`

### 1.4 BFF→API 相関（Trace propagation）
- 指標: BFF リクエストのうち、`X-Trace-Id` が API レスポンスまで維持される割合
- 目標値: 99.9% 以上
- 検証方法: BFF/ API のアクセスログを `trace_id` で突合

## 2. SLO 目標値

| 区分 | SLO | 評価窓 |
|---|---|---|
| 可用性 | 99.9% 以上 | 30日 |
| `/v1/decide` P95 | 1200ms 以下 | 7日 |
| `/v1/decide` P99 | 2500ms 以下 | 7日 |
| 5xx エラーレート | 0.5% 未満 | 1日 |
| Trace 伝播成功率 | 99.9% 以上 | 7日 |

## 3. Error Budget 運用
- 月次 Error Budget: 43.2分（99.9% 前提）
- 消費率 50% 到達時:
  - 新規機能投入を凍結し、安定化対応を優先
  - 直近7日の `trace_id` 上位障害クラスタを分析
- 消費率 100% 到達時:
  - 重大変更の本番反映を停止
  - 24時間以内に RCA（Root Cause Analysis）を作成

## 4. 監視とアラート

### 4.1 アラート条件（推奨）
1. `5xx rate > 1%` が 10分継続
2. `/v1/decide` P95 > 1200ms が 15分継続
3. Trace 伝播成功率 < 99.9% が 30分継続

### 4.2 アラート通知先
- Primary: on-call backend
- Secondary: platform/security

## 5. 障害対応 Runbook

### 5.1 初動（0–15分）
1. `/health` と主要 API の状態確認
2. エラー増加の route を特定
3. 代表 `trace_id` を抽出して BFF→API 連鎖を確認

### 5.2 切り分け（15–45分）
1. API 側 5xx の発生ポイントを特定
2. BFF 側で認証失敗 / payload 制限 / upstream 失敗を分類
3. 影響範囲（顧客・機能・時間帯）を記録

### 5.3 緩和策（45–90分）
1. 高リスクエンドポイントにレート制限を強化
2. 必要に応じて feature flag / canary rollback を実施
3. 監査向けに対応ログと `trace_id` 一覧を保全

### 5.4 復旧後（24時間以内）
1. RCA を作成し、再発防止策をチケット化
2. SLO 逸脱分を Error Budget 台帳へ反映
3. アラート閾値と runbook の妥当性を再評価

## 6. デプロイ前セキュリティ確認（P0）
- backend / frontend ともに本番プロファイルでは `VERITAS_ENV=production` を明示設定する。`NODE_ENV=production` 単独では frontend の strict CSP 既定適用に乗らない。
- production では `NEXT_PUBLIC_VERITAS_API_BASE_URL` を必ず未設定にする。残っていると BFF は安全側で `503 server_misconfigured` になり、内部 API 経路の公開リスクも生む。
- `VERITAS_AUTH_ALLOW_FAIL_OPEN=true` は検証専用の危険フラグであり、production へ混入させない。backend startup は fail-fast するが、環境定義から除去しておくこと。
- デプロイ担当者はリリース前に環境変数一覧をレビューし、不要な `NEXT_PUBLIC_*` と fail-open 系フラグが含まれていないことを確認する。

## 6.1 TrustLog degraded 状態 runbook

### `trust_json_status` の意味
- `unreadable`: `trust_log.json` の読込時に例外が発生し、aggregate JSON を安全側で無視した状態。JSONL 追記は継続しても aggregate JSON 更新は停止される。
- `invalid`: `trust_log.json` が list / `{"items": [...]}` 以外で、監査集計に使えない状態。
- `too_large`: aggregate JSON が保護上限を超え、破壊的な再読込を避けるため更新を停止した状態。

### 監査上の影響
- いずれも **自動修復ではなく degraded 保護**。既存 aggregate JSON を黙って上書きしないことで監査証跡の破壊を防ぐ。
- JSONL 側に新規追記が残る可能性はあるため、監査時は aggregate JSON と JSONL の乖離有無を確認する。

### 初動確認手順
1. `/health` や system status で `trust_json_status` を確認する。
2. `trust_log.json` と `trust_log.jsonl` のサイズ・更新時刻・権限差分を確認する。
3. backend log の warning `write trust_log.json skipped: aggregate log status=...` を確認し、`unreadable|invalid|too_large` のどれかを特定する。

### 復旧手順
1. `unreadable` の場合は権限・所有者・破損ファイルの有無を確認し、読める状態へ戻す。
2. `invalid` の場合は JSON 構造を修復し、list もしくは `{"items": [...]}` へ正規化する。
3. `too_large` の場合はバックアップ取得後に分割・アーカイブし、上限内サイズへ縮退する。
4. 修復後に `trust_json_status=ok` へ戻ること、かつ append warning が止まることを確認する。

### 再発防止の確認項目
- aggregate JSON を手編集しない運用に統一する。
- 監査ジョブで `trust_json_status != ok` を検知する。
- 大容量化しやすい環境では rotate / archive 手順を定期化する。

## 6.2 fail-open 設定の検知経路

### startup warning / fail-fast の確認手順
1. backend startup log で `[SECURITY] VERITAS_AUTH_ALLOW_FAIL_OPEN=true is enabled.` の warning を確認する。
2. `VERITAS_ENV=prod|production` では startup が `RuntimeError` で fail-fast することを確認する。
3. `VERITAS_ENV` が `dev|development|local|test` 以外の shared 環境では warning に加え、auth store fallback logic が `open` を無視して `closed` に戻すことを確認する。

### CI / deployment check
- `scripts/quality/check_deployment_env_defaults.py` の smoke check で、テンプレートに危険な public env や不足設定がないことを継続検証する。
- 本番前レビューでは環境変数一覧に `VERITAS_AUTH_ALLOW_FAIL_OPEN=true` が残っていないことをチェックリスト化する。

### 環境別ポリシー
- production / shared staging / preview: **禁止**。残置は認証保護低下のセキュリティ事故につながる。
- local / isolated test: 明示的な検証時のみ一時許容。終了後は必ず削除する。


## 6.3 capability profile / strict mode 推奨

### production 推奨設定
- `VERITAS_CAP_FUJI_TRUST_LOG=1`: FUJI 判定の TrustLog 監査証跡を維持する。production では常時有効を推奨。
- `VERITAS_CAP_EMIT_MANIFEST=1`: startup 時に capability manifest を出力し、optional dependency の欠落や capability drift を観測可能にする。
- `VERITAS_CAP_MEMORY_POSIX_FILE_LOCK=1`（POSIX 環境）: Memory store のファイル更新競合を抑制するため有効を維持する。
- `VERITAS_CAP_FUJI_TOOL_BRIDGE=1` は、FUJI が外部 safety tool を使う運用でのみ有効化する。無効化する場合は capability manifest と運用手順で明示する。

### local / test でのみ許容する設定
- `VERITAS_CAP_MEMORY_SENTENCE_TRANSFORMERS=0`: 依存未導入環境で fallback 検証を行うときのみ許容。本番推奨構成では embedding 差分による挙動差を避けるため、使用有無を固定する。
- `VERITAS_CAP_FUJI_TOOL_BRIDGE=0`: ローカル単体試験やオフライン検証では許容できるが、shared 環境では FUJI capability 差分として扱う。
- `VERITAS_AUTH_ALLOW_FAIL_OPEN=true`: 認証 fail-open の危険フラグであり、isolated local/test の一時検証以外では禁止する。

### strict mode を推奨する箇所
- `VERITAS_CAP_FUJI_YAML_POLICY=1`: production で YAML policy を正規運用する場合は明示有効化し、依存（PyYAML）欠落を fail-fast させる。
- `VERITAS_FUJI_STRICT_POLICY_LOAD=1`: policy file の欠損・破損時に permissive fallback へ流さず、deny policy へ倒す strict load を推奨する。
- `VERITAS_CAP_MEMORY_SENTENCE_TRANSFORMERS=1`: ベクトル検索品質を production で固定したい場合は明示有効化し、依存欠落を設定不整合として表面化させる。

### fallback / degraded の観測方法
- startup log の `[CapabilityManifest] component=... manifest=... disabled=...` を確認し、想定外に disabled になった capability がないかを監視する。
- FUJI policy fallback は `FUJI policy fallback triggered:` warning と strict mode 時の error で検知する。
- Memory sentence-transformers fallback は `[CONFIG_MISMATCH] sentence-transformers is unavailable...` warning で検知する。
- auth fail-open は §6.2 の startup warning / fail-fast / deployment check を併用し、shared 環境に残置しない。

### セキュリティ注意
- optional dependency fallback は可用性向上に役立つ一方、shared 環境では capability drift により安全性・監査性・検索品質の非決定性を生む。
- 特に `VERITAS_AUTH_ALLOW_FAIL_OPEN=true` と permissive policy fallback の併用は、防御低下の複合リスクになるため避ける。

## 7. セキュリティ上の警告
- `trace_id` は監査相関用であり、認可判定には使用しない。
- 外部入力の `trace_id` は形式検証を行い、ヘッダ/ログインジェクションを防止する。
- `trace_id` に秘密情報（APIキー、トークン、PII）を含めない。
