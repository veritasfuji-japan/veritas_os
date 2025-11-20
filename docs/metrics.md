# VERITAS Metrics 仕様書

Version: 1.0  
Scope: /v1/decide・Self-Improve ループの評価に使う共通メトリクス定義  
Owner: 藤下 + VERITAS OS  
Status: Draft（Self-Improve で更新対象）

---

## 1. Overview（目的）

本ドキュメントは、VERITAS OS の挙動を数値で監視・評価するための  
「公式メトリクス」を定義する。

役割は大きく 3つ：

1. 「良くなった / 悪くなった」を **数値で** 判定できるようにする  
2. Self-Improve ループの **評価軸** を固定し、Before/After 比較を可能にする  
3. world_state / doctor_report / bench_* / metrics_* の間で  
   **同じキー名・同じ意味** で扱うための共通辞書になる

メトリクスは主に以下に保存される：

- `veritas_os/scripts/logs/metrics_YYYYMMDD_HHMMSS.json`  
  → snapshot（1回分の集計値）
- `veritas_os/scripts/logs/doctor_report.json`  
  → 直近の健康状態レポート（メトリクス一部を含む）
- `veritas_os/scripts/logs/bench_*.json`  
  → ベンチ単位の詳細ログ
- `veritas_os/scripts/logs/world_state.json`  
  → `metrics` フィールドとして、中長期の傾向

---

## 2. メトリクス分類（カテゴリ）

### 2.1 Runtime Metrics（実行系）

- `decision_latency_ms_median`  
  - 説明: /v1/decide のレスポンス時間の中央値（ミリ秒）。  
  - 意味: 体感速度・応答性のコア指標。
- `decision_latency_ms_p95`  
  - 説明: レイテンシの 95 パーセンタイル。  
  - 意味: 「たまにすごく遅い」がどの程度か。

- `crash_free_rate`  
  - 説明: /v1/decide 呼び出しのうち、エラー / 例外にならなかった割合（0〜1）。  
  - 意味: 安定性の指標。1.0 に近いほど良い。

### 2.2 Quality / Value Metrics（品質・価値系）

- `value_ema`  
  - 説明: ValueCore が評価した「価値スコア」の指数移動平均（0〜1）。  
  - 意味: 「最近の決定はどれくらい良かったか」を滑らかに表現。

- `truthfulness_score_avg`（任意 / 将来）  
  - 説明: FUJI / ログ解析から推定される「真実性」の平均スコア。  
  - 意味: ハルシネーション抑制の進捗を見る。

- `user_benefit_score_avg`（任意 / 将来）  
  - 説明: decision.values.user_benefit の平均。  
  - 意味: 藤下にとっての実利。

### 2.3 Safety Metrics（安全性・リスク系）

- `risk_effective`  
  - 説明: FUJI Gate によって計算された「実効リスク」（0〜1）。  
  - 意味: 0 に近いほど安全。Self-Improve ループの暴走検知に使う。

- `fuji_reject_rate`  
  - 説明: FUJI Gate によって `decision_status="reject"` となった決定の割合。  
  - 意味: 危険な決定案がどれくらい出てきているか。

### 2.4 Usage / Automation Metrics（運用・自動化系）

- `decision_count_total`  
  - 説明: /v1/decide の累積呼び出し回数。
- `self_improve_cycle_count`（任意 / 将来）  
  - 説明: Self-Improve ループを 1サイクル回した回数。  
- `automation_success_rate`（任意 / 将来）  
  - 説明: 「自動で完結できたタスク」の割合。

---

## 3. 共通 JSON スキーマ

### 3.1 metrics_snapshot.json の例

`scripts/logs/metrics_YYYYMMDD_HHMMSS.json` は、以下のような形を想定する。

```json
{
  "meta": {
    "generated_at": "2025-11-19T02:34:56+09:00",
    "source": "metrics_snapshot.py",
    "window": {
      "from": "2025-11-18T00:00:00+09:00",
      "to": "2025-11-19T00:00:00+09:00"
    }
  },
  "metrics": {
    "decision_latency_ms_median": 3100.5,
    "decision_latency_ms_p95": 6400.0,
    "crash_free_rate": 0.99,

    "value_ema": 0.54,
    "truthfulness_score_avg": 0.92,
    "user_benefit_score_avg": 0.88,

    "risk_effective": 0.05,
    "fuji_reject_rate": 0.02,

    "decision_count_total": 241,
    "self_improve_cycle_count": 3
  }
}

3.2 world_state.json との連携

world_state.json 側では、より長期的な “トレンド” として同じキーを持つ：

{
  "projects": {
    "veritas_agi": {
      "name": "VERITASのAGI化",
      "status": "in_progress",
      "progress": 1.0,
      "decision_count": 241,
      "last_risk": 0.05,
      "metrics": {
        "value_ema": 0.54,
        "decision_latency_ms_median": 3100.5,
        "risk_effective": 0.05,
        "crash_free_rate": 0.99
      }
    }
  }
}

ポイント：
	•	metrics_snapshot.json …「ある時間窓の集計結果」（日次 / 週次）
	•	world_state.json ……「最新の代表値」（中期状態）

⸻

4. メトリクス定義（詳細）

4.1 decision_latency_ms_median
	•	カテゴリ: Runtime
	•	キー名: decision_latency_ms_median
	•	定義:
	•	対象期間内に記録された /v1/decide 呼び出しのレイテンシ（ミリ秒）の中央値。
	•	レイテンシは response_json.extras.metrics.latency_ms などから取得する想定。
	•	算出方法（擬似コード）:

latencies = [rec["extras"]["metrics"]["latency_ms"] for rec in decisions]
median_latency = np.median(latencies)

•	目標値の例:
	•	初期ベースラインから 30%以上短縮 を 6ヶ月目標とする。
	•	アラート条件の例:
	•	直近1週間で baseline 比 +50% 超え → 要調査。

⸻

4.2 decision_latency_ms_p95
	•	カテゴリ: Runtime
	•	キー名: decision_latency_ms_p95
	•	定義:
	•	レイテンシ分布の 95 パーセンタイル。

	•	算出方法:

p95_latency = np.percentile(latencies, 95)

	•	意味:
	•	「たまにすごく重い」ケースがどの程度か。

⸻

4.3 crash_free_rate
	•	カテゴリ: Runtime / Safety
	•	キー名: crash_free_rate
	•	定義:
	•	crash_free_rate = 成功応答数 / 全試行数
	•	成功応答: HTTP 200 & decision_status in ["allow", "warn"]

	•	算出方法:

total = len(calls)
ok = sum(1 for c in calls if c["status_code"] == 200)
crash_free_rate = ok / total if total > 0 else 1.0

	•	目標:
	•	0.99 以上（= 100回に1回以下の失敗）

⸻

4.4 value_ema
	•	カテゴリ: Quality / Value
	•	キー名: value_ema
	•	定義:
	•	各 decision に含まれる values.total の指数移動平均。
	•	算出方法（例）:

alpha = 0.1  # 応答 1件あたりの重み
ema = prev_ema
for dec in new_decisions:
    ema = alpha * dec["values"]["total"] + (1 - alpha) * ema

	•	目標:
	•	ベースラインから +0.05 以上向上し、0.5〜0.8 レンジで安定。
	•	用途:
	•	「自己改善サイクルが長期的にプラスか？」を見る。

⸻

4.5 risk_effective
	•	カテゴリ: Safety
	•	キー名: risk_effective
	•	定義:
	•	FUJI Gate による実効リスク（0〜1）。
	•	一般に fuji.risk または gate.risk を集計。
	•	算出方法（例）:

risk_effective = np.mean([dec["fuji"]["risk"] for dec in decisions])

	•	基準:
	•	0.0〜0.1: 低リスク
	•	0.1〜0.3: 注意
	•	0.3〜: 危険（設計の見直し）

⸻

4.6 fuji_reject_rate
	•	カテゴリ: Safety
	•	キー名: fuji_reject_rate
	•	定義:
	•	decision_status == "reject" となった決定の割合。

	•	算出方法:

total = len(decisions)
rej = sum(1 for d in decisions if d["fuji"]["status"] == "reject" or d["decision_status"] == "reject")
fuji_reject_rate = rej / total if total > 0 else 0.0

	•	解釈:
	•	高すぎる → 危険なリクエスト or 設計が多い
	•	低すぎる → FUJI が甘すぎる可能性もある（≠無条件に良い）

⸻

4.7 decision_count_total
	•	カテゴリ: Usage
	•	キー名: decision_count_total
	•	定義:
	•	/v1/decide の累積呼び出し回数。
	•	用途:
	•	AGI 研究OS として「どれくらい回されたか」を見るための単純なカウンタ。
	•	更新:
	•	world.update_from_decision() 内で +1。

⸻

5. metrics_snapshot.py の仕様メモ（実装ガイド）

※ このドキュメントから派生して実装するスクリプトの想定。

5.1 CLI インターフェイス案

python veritas_os/scripts/metrics_snapshot.py \
  --logs-dir veritas_os/scripts/logs \
  --out veritas_os/scripts/logs/metrics_20251119_0234.json \
  --window-days 1


	•	--logs-dir
	•	decision_log.jsonl, bench_*.json, world_state.json 等がある場所
	•	--out
	•	出力先 JSON パス
	•	--window-days
	•	過去何日分を対象とするか（デフォルト 1日）

5.2 入力と出力
	•	入力：
	•	decide_log.jsonl
	•	bench_*.json
	•	world_state.json
	•	出力：
	•	metrics_YYYYMMDD_HHMMSS.json（上記スキーマ）

5.3 world_state への反映
	•	metrics_snapshot.py 実行後、以下のような処理を行う想定：

world_state = world.get_state()
world_state["projects"]["veritas_agi"]["metrics"] = snapshot["metrics"]
world.save_state(world_state)

6. Self-Improve ループとの接続

Self-Improve サイクルにおけるメトリクスの位置付け：
	1.	観測（Observation）
	•	metrics_snapshot.py を実行し、最新メトリクスを取得
	•	doctor_report.json と合わせて「現状」を把握
	2.	解釈（Interpretation）
	•	/v1/decide で「どのメトリクスが悪いか」「どこを改善するか」を LLM に整理させる
	3.	設計（Design）
	•	「どのメトリクスを何％改善するか」を明示した plan を作る
	4.	検証（Evaluation）
	•	Before/After で metrics_*.json を比較し、改善を確認
	5.	ロールバック / 採用
	•	目標値を下回っているかどうかで、採用 / rollback を判断

⸻

7. 運用ルール（Draft）
	•	メトリクス定義を変更する場合：
	•	docs/metrics.md を更新し、バージョン番号を上げる
	•	metrics_snapshot.py, doctor_report 生成ロジックを合わせて更新
	•	新しいメトリクスを追加する場合：
	•	必ず 以下をセットで定義すること
	•	キー名
	•	意味・用途
	•	集計方法（どのログからどう計算するか）
	•	目標値 / アラート条件の例
	•	「意味があいまい / 使っていない」メトリクスは、定期的に整理して削除候補に入れる


