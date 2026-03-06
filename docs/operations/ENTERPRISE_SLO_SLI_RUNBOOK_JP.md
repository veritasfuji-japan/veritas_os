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

## 6. セキュリティ上の警告
- `trace_id` は監査相関用であり、認可判定には使用しない。
- 外部入力の `trace_id` は形式検証を行い、ヘッダ/ログインジェクションを防止する。
- `trace_id` に秘密情報（APIキー、トークン、PII）を含めない。
