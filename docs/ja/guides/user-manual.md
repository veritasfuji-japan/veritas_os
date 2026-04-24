# VERITAS OS 総合取り扱い説明書（全機能版）

- 文書ID: VERITAS-MANUAL-ALL-001
- 対象バージョン: VERITAS OS v2系
- 対象読者: 運用者 / 管理者 / 開発者 / 監査担当
- 最終更新: 2026-03-14

---

## 1. 概要

VERITAS OS は、LLM を監査可能・再現可能・安全制御付きで運用するための意思決定 OS です。中核は **意思決定パイプライン**、**FUJI Gate（安全ゲート）**、**TrustLog（監査ログ）**、**MemoryOS（記憶検索）**、**Mission Control（運用UI）** で構成されます。

### 1.0 本書の使い方

- **運用担当者**: まず「5. 代表的な運用フロー」「7. セキュリティ上の注意」を参照
- **管理者**: 「4. API取扱説明」「9. 導入時チェックリスト」を参照
- **監査担当**: 「4.4 Trust / Audit」「7.3 監査ログ」「8. トラブルシューティング」を参照
- **開発者**: 「2.2 責務分離」「6. 主要スクリプト運用ガイド」を参照

> 本書は「機能を漏れなく理解する」ことを目的としており、日常運用時は該当章のみ抜粋利用できます。

### 1.1 主要コンセプト

- **再現可能性**: リプレイ可能な決定パイプライン
- **監査可能性**: ハッシュチェーン付き TrustLog
- **安全性**: FUJI Gate による最終判定（allow/modify/rejected）
- **ガバナンス**: ポリシー管理、履歴、停止/再開制御
- **可観測性**: メトリクス、イベントストリーム、ダッシュボード
- **価値整合性**: Value Core による価値軸スコアリング（ethics / legality / harm_avoid / truthfulness など）

---

## 2. システム全体像

### 2.1 レイヤー構成

1. **入力層**: ユーザークエリ、文脈、メタ情報
2. **推論層**: Planner / Kernel / Critique / Debate / Evidence / Reflection
3. **安全層**: FUJI Gate、PIIサニタイズ、ポリシー適用
4. **記憶・世界モデル層**: MemoryOS / WorldModel
5. **監査層**: TrustLog、署名、改ざん検知
6. **公開層**: REST API、Mission Control UI、CLI/スクリプト

### 2.2 責務分離（重要）

- **Planner**: 目標に対する行動候補の生成
- **Kernel**: 意思決定パイプラインの実行制御
- **FUJI**: 安全・コンプライアンス判定
- **MemoryOS**: 記憶保存・検索

> 上記責務は相互に独立しており、運用時も責務境界を維持してください。

### 2.3 役割と責任（RACI簡易版）

| 項目 | 運用担当 | 管理者 | 開発者 | 監査担当 |
|---|---|---|---|---|
| `/v1/decide` 実行 | R | A | C | I |
| ポリシー更新 | C | A/R | C | I |
| 緊急停止/再開 | R | A | C | I |
| TrustLog検証 | C | R | C | A |
| EU AI Act報告 | I | R | C | A |

- R: 実行責任（Responsible）
- A: 最終責任（Accountable）
- C: 相談先（Consulted）
- I: 通知先（Informed）

---

## 3. 機能一覧（全体）

### 3.1 意思決定機能

- 多段パイプラインで候補生成・評価・選択
- 選択肢/代替案/棄却理由の構造化出力
- 証拠（memory/web/world）付き説明
- critique / debate / reflection を含む自己検証
- 不確実性・リスク・効用スコアの算出

#### 出力の読み方（実務向け）

- `chosen`: 採用案。まず安全判定（`fuji`）と合わせて解釈
- `alternatives`: 採用されなかったが有効な代替案。運用ではバックアップ計画に活用
- `evidence`: 根拠の出典。監査時はソース妥当性（古さ・偏り）を確認
- `critique` / `debate`: 盲点抽出。高リスク案件では必ずレビュー対象
- `risk_score` / `uncertainty`: 人間介入優先度を決める指標

#### Value Core 詳細（価値整合の中核）

Value Core は、意思決定の「何を優先するか」を数値化し、判断の一貫性を担保するモジュールです。

**主な役割**

- 複数価値軸（例: `ethics`, `legality`, `harm_avoid`, `truthfulness`, `user_benefit`）をスコア化
- クエリ文面と文脈（`context`）から価値スコアを推定
- 重み付き合成で `total`（0.0〜1.0）を計算し、上位要因（`top_factors`）を提示
- 学習許可時（`no_learn_values=False`）はオンライン更新で重みを微調整

**評価の流れ（運用理解向け）**

1. ヒューリスティクスで初期スコア生成
2. `context.value_scores` があれば明示上書き
3. `ValueProfile`（保存済み重み）をロード
4. `context.value_weights` があれば重みに反映
5. 加重平均で `total` を算出
6. `top_factors` と `rationale` を作成
7. 必要に応じて重みを学習更新

**主要入力パラメータ（context）**

- `value_scores`: 軸ごとのスコア明示指定（0.0〜1.0）
- `value_weights`: 軸ごとの重み明示指定（0.0〜1.0）
- `value_lr`: 学習率（既定 0.02）
- `no_learn_values`: `true` で学習更新を禁止（監査モード推奨）

**主要出力フィールド**

- `scores`: 軸ごとの評価値
- `total`: 総合価値スコア
- `top_factors`: 支配的な価値要因（上位）
- `rationale`: 人間可読な判断理由

**運用ガイドライン**

- 高リスク運用では `total` 単体で判断せず、必ず FUJI 判定と併読
- 監査時は `value_scores`/`value_weights` の上書き有無を記録
- 本番で重み学習を有効にする場合、変更履歴（いつ・誰が・なぜ）を残す
- 重大案件は `no_learn_values=true` で再現性重視の再評価を実施


### 3.2 安全・ガバナンス機能

- FUJI Gate による最終判定
- PII検出とサニタイズ
- ポリシー駆動の制約適用
- システム停止（halt）/再開（resume）
- ドリフト監視（value drift）

### 3.3 監査・可観測性機能

- TrustLog のチェーン検証
- 監査ログの抽出（export）
- フィードバック記録
- イベントストリーミング
- メトリクス取得

### 3.4 記憶機能（MemoryOS）

- 記憶の保存（put）
- ID指定の取得（get）
- 類似検索（search）
- 消去（erase）

### 3.5 コンプライアンス機能

- ガバナンスレポート生成
- EU AI Act 向けレポート生成
- コンプライアンス設定の取得・更新
- デプロイ準備状態の確認

### 3.6 フロントエンド機能（Mission Control）

- `/` 運用ダッシュボード（ヘルス、重要イベント）
- `/console` Decision Console（実行・可視化・差分）
- `/audit` TrustLog探索・検証・エクスポート
- `/governance` ポリシー編集・履歴管理
- `/risk` リスク監視ビュー

---

## 4. API 取扱説明（エンドポイント完全版）

> 認証が必要な環境では `X-API-Key` を付与してください。

### 4.0 共通利用ルール

- ベースURL例: `http://localhost:8000`
- `Content-Type: application/json` を使用
- 失敗時はHTTPステータスとレスポンス本文を必ず保存（監査・障害分析に利用）
- 高権限操作（halt/resume/policy更新）は実行者・理由・時刻を運用台帳へ記録

**cURLテンプレート**

```bash
curl -sS -X POST "http://localhost:8000/v1/decide" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${VERITAS_API_KEY}" \
  -d '{"query":"新規事業の初期市場を選定したい"}'
```

### 4.1 基本

| Method | Path | 用途 |
|---|---|---|
| GET | `/health` | 稼働確認 |

### 4.2 意思決定

| Method | Path | 用途 |
|---|---|---|
| POST | `/v1/decide` | フル意思決定パイプライン実行 |
| POST | `/v1/fuji/validate` | 単発アクションのFUJI判定 |
| POST | `/v1/replay/{decision_id}` | 決定リプレイ |
| POST | `/v1/decision/replay/{decision_id}` | 互換リプレイ経路 |

**運用ポイント**

- `/v1/decide`: 本番運用の入口。`decision_status` と `fuji` を同時確認
- `/v1/fuji/validate`: 導入前検証・ルール改訂前検証に有効
- `/v1/replay/*`: 事故調査・品質改善・監査報告で使用

**確認すべき代表フィールド**

- `request_id`, `decision_id`
- `gate.decision_status`
- `fuji.status`（allow / modify / rejected）
- `extras.metrics`（遅延・ヒット率など）
- `telos_score` / `value.total`（価値整合の確認指標）
- `value.top_factors`（判断に効いた価値軸）

### 4.3 MemoryOS

| Method | Path | 用途 |
|---|---|---|
| POST | `/v1/memory/put` | 記憶の保存 |
| POST | `/v1/memory/get` | 記憶の取得 |
| POST | `/v1/memory/search` | 記憶の類似検索 |
| POST | `/v1/memory/erase` | 記憶の消去 |

**運用ポイント**

- `put` 前にデータ分類（公開/社外秘/個人情報）を判定
- `search` 結果は時刻・出典を確認し、古い記憶の混入を防止
- `erase` は監査要件に応じて実施可否を定義（無条件削除は禁止）

### 4.4 Trust / Audit

| Method | Path | 用途 |
|---|---|---|
| GET | `/v1/trust/{request_id}` | 単一要求の監査情報取得 |
| GET | `/v1/trust/logs` | 監査ログ一覧 |
| POST | `/v1/trust/feedback` | 監査対象へのフィードバック記録 |
| GET | `/v1/trustlog/verify` | チェーン整合性検証 |
| GET | `/v1/trustlog/export` | 監査ログエクスポート |

**運用ポイント**

- `verify` を定期実行し、破損時は即時インシデント化
- `export` は提出先要件に合わせて期間・PIIリダクションを設定
- `feedback` は運用改善の根拠になるため、主観ではなく事実ベースで記録

### 4.5 監視

| Method | Path | 用途 |
|---|---|---|
| GET | `/v1/events` | イベントストリーム |
| GET | `/v1/metrics` | 運用メトリクス |

### 4.6 ガバナンス・コンプライアンス

| Method | Path | 用途 |
|---|---|---|
| GET | `/v1/governance/value-drift` | 価値ドリフト監視 |
| GET | `/v1/governance/policy` | 現行ポリシー取得 |
| PUT | `/v1/governance/policy` | ポリシー更新 |
| GET | `/v1/governance/policy/history` | ポリシー履歴 |
| GET | `/v1/compliance/config` | コンプライアンス設定取得 |
| PUT | `/v1/compliance/config` | コンプライアンス設定更新 |
| GET | `/v1/compliance/deployment-readiness` | デプロイ準備状態 |
| GET | `/v1/report/eu_ai_act/{decision_id}` | EU AI Actレポート |
| GET | `/v1/report/governance` | ガバナンスレポート |

**運用ポイント**

- `PUT /v1/governance/policy` 実施前に必ず差分レビューを行う
- 変更後 24 時間は `metrics` / `events` を重点監視
- EU AI Act対象案件では `report/eu_ai_act` を案件単位で保存

### 4.7 システム制御

| Method | Path | 用途 |
|---|---|---|
| POST | `/v1/system/halt` | システム停止 |
| POST | `/v1/system/resume` | システム再開 |
| GET | `/v1/system/halt-status` | 停止状態確認 |

**運用ポイント**

- `halt` は「誰が・なぜ・いつ」を必須記録
- `resume` は復旧条件（原因除去・再発防止策）を満たした後に実施
- `halt-status` は定期監視に組み込み、誤停止の長期化を防止

---

## 5. 代表的な運用フロー

### 5.0 日次運用チェック（推奨）

1. `/health` で稼働確認
2. `/v1/metrics` でエラー率・遅延を確認
3. `/v1/events` で重大イベント有無を確認
4. `/v1/trustlog/verify` を実行
5. 重要案件の `decision_status` と `fuji` をサンプリング監査

### 5.1 意思決定の標準運用

1. `/v1/decide` を実行
2. `fuji` 判定と `decision_status` を確認
3. `chosen / alternatives / evidence / critique` をレビュー
4. 必要なら `/v1/replay/{decision_id}` で再現確認
5. `/v1/trust/{request_id}` で監査情報を取得

**レビュー基準（簡易）**

- `uncertainty` が高い場合: 追加証拠を要求
- `risk_score` が高い場合: 人間承認必須
- `fuji=modify` の場合: 修正案反映後に再評価
- `fuji=rejected` の場合: 実行禁止、理由を運用台帳へ記録
- `value.total` が低い場合: 価値軸（`top_factors`）を確認して方針修正

### 5.2 ガバナンス更新運用

1. `/v1/governance/policy` で現行ポリシー取得
2. 変更案を適用し `PUT /v1/governance/policy`
3. `/v1/governance/policy/history` で履歴監査
4. `/v1/metrics` と `/v1/events` で影響監視

### 5.3 緊急停止運用

1. 重大インシデント検知
2. `POST /v1/system/halt`
3. 原因分析（TrustLog / Events / Metrics）
4. 安全確認後 `POST /v1/system/resume`

---

## 6. 主要スクリプト運用ガイド（抜粋）

`veritas_os/scripts/` には運用・保守・検証スクリプトが用意されています。

- 意思決定系: `decide.py`, `decide_plan.py`
- 健全性確認系: `doctor.py`, `health_check.py`, `alert_doctor.py`
- 自己修復系: `self_heal_tasks.py`, `heal.sh`, `auto_heal.sh`
- 監査系: `verify_trust_log.py`, `merge_trust_logs.py`, `generate_consistency_certificate.py`
- 記憶系: `memory_train.py`, `search_memory.py`, `memory_sync.py`, `distill_memory.py`
- レポート系: `generate_report.py`, `bench_summary.py`, `pr_impact_summary.py`
- ベンチマーク系: `bench.py`, `bench_plan.py`, `run_benchmarks_enhanced.py`
- 運用補助系: `start_server.sh`, `weekly_maintenance.sh`, `backup_logs.sh`, `veritas_monitor.sh`

> 各スクリプトの詳細オプションは `--help` で確認してください。

### 6.1 スクリプト実行時の安全原則

- 本番環境では事前にドライラン可否を確認
- 出力先ファイル（ログ/レポート）の保存先権限を最小化
- 監査系スクリプトはタイムスタンプ付きで保管
- 自動修復系スクリプトは影響範囲を限定し、実行後に差分監査

---

## 7. セキュリティ上の注意（必読）

### 7.1 入力データ

- 個人情報・機密情報は最小限にしてください。
- プロンプトインジェクション対策のため、外部ソース由来テキストは検証して投入してください。

### 7.2 認証・権限

- APIキーは環境変数または秘密管理基盤で管理し、ソースに埋め込まないでください。
- `/v1/system/halt` などの高権限APIはアクセス制限してください。

### 7.3 監査ログ

- TrustLog は改ざん検知のため削除・上書きを禁止し、WORM/署名運用を推奨します。
- エクスポート時はPIIリダクション設定を確認してください。

### 7.4 重大リスク警告

- 高リスク領域（医療・法務・金融・雇用）での最終決定を AI 出力のみに依存する運用は危険です。
- FUJI が `rejected` または `modify` を返した結果を無視して実行することは、重大なコンプライアンス/安全違反につながります。

### 7.5 追加セキュリティ警告（運用事故防止）

- 外部ナレッジ投入時にプロンプトインジェクションを未検査で通す運用は、意図しない行動誘導リスクがあります。
- 監査ログをローカル単一ディスクのみに保管すると、障害時に検証不能となる恐れがあります。
- ポリシー更新をレビューなしで即時適用すると、安全ゲートの無効化や過剰遮断を招く恐れがあります。
- APIキーをCIログやチャットへ貼り付ける運用は漏えいリスクが非常に高く、厳禁です。
- Value Core の重みを無審査で更新すると、意思決定の価値整合がドリフトするリスクがあります（変更管理必須）。

---

## 8. トラブルシューティング

### 8.0 典型アラートと一次対応

| 症状 | 可能性 | 一次対応 |
|---|---|---|
| FUJI拒否が急増 | ポリシー変更/入力品質低下 | 直近のpolicy差分確認、入力テンプレート点検 |
| レイテンシ急上昇 | 外部依存遅延/負荷増大 | metrics確認、負荷平準化、再試行戦略確認 |
| TrustLog検証失敗 | ログ欠損/改ざん/同期不整合 | export保全、書込経路停止、復旧手順開始 |
| replay差分拡大 | メモリ更新/環境差分 | 入力・メモリ・ポリシー時点を突合 |

### 8.1 `decide` が期待通り動かない

- `/health` を確認
- `/v1/metrics` でエラー増加を確認
- `/v1/events` で直近エラーイベントを確認
- `/v1/trustlog/verify` でログ破損有無を確認

### 8.2 ポリシー反映に失敗する

- `PUT /v1/governance/policy` のレスポンス検証
- `/v1/governance/policy/history` に更新履歴が追加されたか確認
- UI利用時はBFFのセッション有効期限を確認

### 8.3 リプレイ差分が大きい

- 入力差分（時刻・メモリ内容・外部情報）を確認
- MemoryOS 検索結果の更新有無を確認
- ガバナンスポリシー更新時刻を確認

---

## 9. 導入時チェックリスト

- [ ] APIキー・認証方式の設定
- [ ] ポリシー初期値のレビュー
- [ ] TrustLog保全（保存先・バックアップ・署名）
- [ ] メトリクス/イベント監視の接続
- [ ] 停止/再開の運用手順整備
- [ ] EU AI Act 対象時の報告導線確認

### 9.1 初期運用の推奨閾値（例）

- `uncertainty >= 0.7` は人間レビュー必須
- `risk_score = HIGH` は自動実行禁止
- `trustlog/verify` は最低 1 日 1 回（推奨: 1 時間毎）
- ポリシー更新は 4-eyes（最低2名承認）

---

## 10. 変更管理

- 本マニュアルは機能追加・API変更・セキュリティポリシー更新時に改訂してください。
- 改訂時は「API表」「セキュリティ注意」「運用フロー」を優先更新してください。

### 10.1 改訂時の最小確認項目

1. `openapi.yaml` と API一覧表の差分確認
2. 新規機能の責務境界（Planner/Kernel/FUJI/MemoryOS）確認
3. セキュリティ章への影響有無確認
4. 運用フローへの追記漏れ確認

## 英語正本

- [docs/en/README.md](../../en/README.md)
