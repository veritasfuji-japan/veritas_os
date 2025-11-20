# VERITAS WorldModel 技術仕様書（Step1 完全版）

- Version: 1.0
- Author: VERITAS OS (藤下 + LLM Co-evolution)
- Status: Internal AGI Architecture Document

---

## 1. Overview（概要）

VERITAS WorldModel は、

> **「状態 → 観測 → 推論 → 更新」**

の因果ループをもつ軽量世界モデルである。

目的は以下の 3 点：

1. VERITAS の「世界の状態」（プロジェクト進捗・リスク・メトリクス）を永続化する  
2. 過去の決定とその結果の**因果関係**を構造化する  
3. 次の意思決定（planner）に必要な**因果的コンテキスト**を提供する  

WorldModel は現在 JSON として保持される：

- パス: `veritas_os/scripts/logs/world_state.json`
- 更新タイミング: すべての `/v1/decide` 完了後に `world.update_from_decision()` を通じて更新

---

## 2. Data Structure（データ構造）

### 2.1 トップレベルスキーマ

```jsonc
{
  "meta": {
    "version": 1,
    "created_at": "...",
    "updated_at": "...",
    "last_users": {
      "user_id": "...",
      "session_id": "..."
    }
  },

  "projects": {
    "veritas_agi": {
      "name": "VERITASのAGI化",
      "status": "in_progress",       // "in_progress" | "completed" | "paused"
      "progress": 1.0,               // 0.0〜1.0

      "last_decision": "...",        // ISO8601
      "last_query": "...",
      "last_risk": 0.05,

      "decision_count": 235,
      "latency_ms_median": 3162,

      "description": "AGI化の目的や現状の要約",
      "extras": {}
    }
  },

  "metrics": {
    "value_ema": 0.0,                // ValueCore の指数移動平均
    "latency_ms_median": 0,
    "error_rate": 0.0                // 直近 N 件の decision 失敗率
  }
}

3. Causal Loop Architecture（因果ループ構造）

WorldModel が関与する因果チェーンは次の通り：
	1.	User Query
	2.	kernel.decide()
	•	DebateOS
	•	FUJI Gate
	•	PlannerOS
	•	MemoryOS
	3.	world.update_from_decision()
	4.	world.next_hint() による「次の一手」生成

3.1 State（状態）

WorldModel の状態は概念的に以下の変数群から構成される：
	•	projects
	•	各プロジェクトのステータス・進捗・リスク
	•	last_query / last_decision
	•	直近の思考イベント
	•	last_risk / value_ema
	•	FUJI Gate・ValueCore による評価
	•	decision_count
	•	累積決定回数
	•	latency_ms_median / error_rate
	•	パフォーマンス指標

3.2 Observation（観測）

観測は kernel.decide() のレスポンス JSON から得られる：
	•	query
	•	result.summary
	•	fuji.status, fuji.effective_risk
	•	planner.steps
	•	metrics.latency_ms
	•	telos_score
	•	debate.sides
	•	必要に応じて doctor_report, trust_log サマリ

WorldModel はこの観測と既存の状態をもとに、更新ルールを適用する。

3.3 Update Rule（更新則）

擬似コードイメージ：

progress_delta = f(planner_steps, telos_score, risk)

progress += progress_delta
last_query = query
last_decision = now()
last_risk = fuji.effective_risk
decision_count += 1
latency_ms_median = update_median(latency_ms)
value_ema = update_ema(value_ema, value_score)

ここで progress は AGI 研究に対する「内部学習ゲージ」であり、
	•	計画ステップ数（どれだけ深く考えたか）
	•	telos との整合度
	•	リスク（低いほど良い）

を総合して 0.0〜1.0 に正規化したものとする。

⸻

4. WorldModel と他モジュールの役割分担

4.1 MemoryOS との違い
機能	MemoryOS	WorldModel
生ログ（decision全文）の保存	◎	×
要約された状態の保持	△	◎
因果的な「状態遷移」の管理	△	◎
プロジェクト単位の進行管理	△	◎
AGI 化ロードマップの誘導	×	◎

	•	MemoryOS: 生ログ・エピソードの「アーカイブ」
	•	WorldModel: その上に立つ「状態・進行度」のシンプルなダッシュボード

⸻

5. Projects モジュール（AGI 進捗管理）

世界モデルの中核は projects であり、
ここに VERITAS が取り組んでいる長期プロジェクトを永続化する。

例（実際のログに近い形）：

"veritas_agi": {
  "name": "VERITASのAGI化",
  "status": "in_progress",
  "progress": 1.0,
  "last_query": "VERITASのAGI化方法を提案して",
  "decision_count": 235,
  "last_risk": 0.05,
  "description": "VERITASを自己ホスティング型AGI研究OSとして進化させる長期プロジェクト",
  "extras": {}
}

6. Next-Hint Engine（次の一手生成器）

WorldModel は内部で、

causal_state(project) → next_hint_for(project)

を計算する簡易エンジンを持つ。

6.1 ロジック例

if progress < 0.3:
    次の AGI 実装タスク（MVP機能）の提案
elif 0.3 ≤ progress < 0.7:
    安全性・評価系・ログ整備の強化タスク
elif 0.7 ≤ progress < 1.0:
    設計の統合 / 検証 / 失敗分析タスク
elif progress == 1.0:
    「AGI v2（恒常学習ループ）」への遷移提案

現在 veritas_agi.progress = 1.0 のため、
WorldModel 上は 「AGIフェーズ1完了 → 恒常学習ループへの移行済み」 という解釈になる。

⸻

7. FUJI Gate と安全境界

WorldModel 自体はコードの実行権限を持たない「状態ストア」だが、
FUJI Gate と連携した安全境界を明確に定義する。

7.1 想定する主な失敗モード（10件以上）
	1.	設計暴走：planner が複雑化し、progress が常に + され続ける
	2.	ログ破損：world_state.json がパース不能・欠損状態になる
	3.	状態不整合：progress が 1.0 を大きく超える／負の値になる
	4.	FUJI Gate 無効化：高リスク decision が連続しても last_risk が更新されない
	5.	リスク過小評価：恒常的に last_risk < 0.05 しか記録されない
	6.	decision_latency 異常増加：latency_ms_median がしきい値を大きく超える
	7.	メトリクスロギング停止：decision_count は増えるのに metrics が変化しない
	8.	progress 過大評価：実装なしで文書だけ書いても progress が上がり続ける
	9.	人間レビュー抜け：高リスク decision が長期間レビューされず積み上がる
	10.	API スキーマ変更：kernel.decide() のレスポンス構造変化に追随できず更新失敗
	11.	外部ストレージ同期失敗：バックアップが長期間取られず、復旧ポイントが消える

7.2 安全境界の定義
	•	WorldModel は 実世界への直接行動を指示しない
	•	外部 API コール・金銭トランザクションは常に FUJI Gate 経由で別レイヤに委譲
	•	fuji.effective_risk ≥ 0.3 の decision は
	•	progress_delta を 0 にし、
	•	場合によっては progress を減少させる（反省モード）
	•	world_state.json のバリデーションに失敗した場合：
	•	直近の安定スナップショットからロールバック
	•	失敗イベントを doctor_report に記録し、手動レビューを必須とする
	•	ValueCore（価値観）の重み更新は 人間レビュー必須。
WorldModel から ValueCore を直接書き換えることは禁止。

⸻

8. Persistent Storage（永続化プロトコル）
	•	保存先: veritas_os/scripts/logs/world_state.json
	•	更新タイミング: すべての /v1/decide 完了後
	•	バージョン管理: meta.version = 1（将来のスキーマ変更に備える）
	•	再起動時: ファイルが存在すれば必ずロードし、存在しなければ初期状態を生成

⸻

9. 現状の限界と拡張計画

9.1 現状の限界
	•	因果グラフが暗黙的（単なる集計値）であり、
「どの decision がどのメトリクスをどれだけ変えたか」が明示されていない
	•	「将来の影響」の予測が単純な progress 増分にとどまっている
	•	マルチエージェント（複数 LLM / 人間）の状態を区別して扱えていない

9.2 Step3〜Step5 で想定する拡張
	1.	Causal Graph の導入
	•	decision → metrics の影響をグラフ構造として保存
	2.	Bayesian World Update
	•	メトリクス変化をベイズ更新として解釈し、progress と不確実性を分離
	3.	Agent-Internal Loop
	•	VERITAS 自身の「自己予測モデル」を導入し、
提案の前に自己評価を挟むループを実装
	4.	外部 I/O World の統合
	•	GitHub・Drive 同期結果や、CLI 実行ログも WorldModel に反映

⸻

付録: WorldModel 実装の擬似コード

class WorldModel:
    def __init__(self, path: str):
        self.path = path
        self.state = load_json(path, default=_default_state())

    def update_from_decision(self, project_id: str, decision: dict) -> None:
        proj = self.state["projects"].setdefault(project_id, {
            "name": project_id,
            "status": "in_progress",
            "progress": 0.0,
            "decision_count": 0,
        })

        proj["last_query"] = decision.get("query")
        proj["last_decision"] = now_iso()
        proj["last_risk"] = decision.get("fuji", {}).get("effective_risk", 0.0)
        proj["decision_count"] = proj.get("decision_count", 0) + 1

        # progress update (リスク高いときは増やさない / 減らす)
        steps = len(decision.get("planner", {}).get("steps", []))
        telos_score = decision.get("telos_score", 0.0)
        risk = proj["last_risk"]

        base_delta = 0.02 * steps * telos_score
        if risk >= 0.3:
            delta = 0.0  # or negative
        else:
            delta = base_delta

        proj["progress"] = max(0.0, min(1.0, proj.get("progress", 0.0) + delta))

        # metrics 更新
        _update_global_metrics(self.state, decision)

        save_json(self.path, self.state)


