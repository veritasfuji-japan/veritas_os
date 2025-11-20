# VERITAS Self-Improvement Loop 技術仕様書（self_improvement_loop.md）

Version: 1.0  
Author: VERITAS OS (藤下 + LLM Co-evolution)  
Status: Step3 – 自己改善ループ設計ドキュメント  
Scope: /v1/decide, world_state, doctor_report, bench, Git ブランチ運用

---

## 1. 概要（Overview）

VERITAS の自己改善ループは、以下の 6 フェーズからなるサイクルとして定義する：

1. **観測 (Observation)**  
2. **解釈 (Interpretation)**  
3. **設計 (Design)**  
4. **実装 (Implementation)**  
5. **検証 (Evaluation)**  
6. **ロールバック / 採用 (Rollback / Adopt)**  

このループは、

- ログ (`decision_log.jsonl`, `trust_log.jsonl`)
- 世界状態 (`world_state.json`)
- ベンチ結果 (`bench_*.json`)
- doctor_report (`doctor_report.json`)

を使って、**VERITAS 自身のコード / 設計 / 安全性を継続的に改善する**ことを目的とする。

---

## 2. 全体ループ図

```mermaid
flowchart LR
    OBS[観測<br>(Observation)] --> INT[解釈<br>(Interpretation)]
    INT --> DES[設計<br>(Design)]
    DES --> IMP[実装<br>(Implementation)]
    IMP --> EVAL[検証<br>(Evaluation)]
    EVAL -->|OK| ADOPT[採用<br>(Adopt)]
    EVAL -->|NG / リスク高| ROLL[ロールバック<br>(Rollback)]

    ADOPT --> OBS
    ROLL --> OBS

3. フェーズ別 詳細設計

3.1 観測 (Observation)

目的
	•	「最近の VERITAS がどう動いていたか」を定量的に把握し、doctor_report と簡易メトリクスを生成する。

主なトリガー
	•	定期バッチ（例：1日1回 or 週1回の cron 相当）
	•	藤下が手動で doctor / bench 系スクリプトを実行したとき

主な入力
	•	scripts/logs/decision_log.jsonl
	•	scripts/logs/trust_log.jsonl
	•	scripts/logs/world_state.json
	•	scripts/logs/bench_*.json

主な役割
	•	直近の decision / FUJI 結果 / bench 結果を集計し、
	•	エラー率
	•	レイテンシ中央値
	•	value_ema のトレンド
	•	リスク (fuji.risk) のトレンド
などをまとめる。
	•	doctor_report.json と簡易メトリクス (simple_metrics.json など) を生成する。

担当
	•	自動: Python スクリプト（例：generate_doctor_report.py 相当）
	•	人間: レポートをざっと眺めて「明らかにおかしい値がないか」確認

データフロー

flowchart LR
    DECLOG[decision_log.jsonl]
    TRUST[trust_log.jsonl]
    WORLD[world_state.json]
    BENCH[bench_*.json]

    SUBGRAPH1[Observation Script<br>(generate_doctor_report.py)]

    DECLOG --> SUBGRAPH1
    TRUST --> SUBGRAPH1
    WORLD --> SUBGRAPH1
    BENCH --> SUBGRAPH1

    SUBGRAPH1 --> REPORT[doctor_report.json<br>＋ simple_metrics.json]

出力アーティファクト
	•	scripts/logs/doctor_report.json
	•	scripts/logs/simple_metrics.json（任意）

⸻

3.2 解釈 (Interpretation)

目的
	•	doctor_report と world_state をもとに、
	•	「どこが弱点なのか」
	•	「次にどのテーマを優先すべきか」
を LLM / VERITAS で整理する。

トリガー
	•	doctor_report.json 更新時

主な入力
	•	scripts/logs/doctor_report.json（メトリクス・警告）
	•	scripts/logs/world_state.json（プロジェクト進捗・リスク）

主な役割
	•	/v1/decide を使って：
	•	「弱点リスト」
	•	「優先度付きの Next Actions」
を生成する。

担当
	•	VERITAS / LLM: /v1/decide を呼んで「弱点サマリ + 次の一手案」を生成
	•	人間: 出力された弱点リスト / TODO が大きくズレていないか目視確認

シーケンス

sequenceDiagram
    participant O as Observation Script
    participant S as /v1/decide API
    participant K as kernel + planner
    participant W as world.py
    participant H as Human (藤下)

    O->>S: POST /v1/decide<br>query="最新 doctor_report を読んで弱点を整理して"
    S->>K: context + query
    K-->>S: decision_json (弱点リスト / 次の一手案)
    S->>W: update_from_decision(...)
    S-->>O: response_json
    O-->>H: 「弱点サマリ＋推奨ステップ」を表示/保存

出力アーティファクト
	•	scripts/logs/agi_weakpoints.md
	•	scripts/logs/agi_next_actions.json

⸻

3.3 設計 (Design)

目的
	•	解釈フェーズで決まった「次にやるべきテーマ」を、
実行可能な 5〜10 ステップのプラン (planner.steps) に落とし込む。

トリガー
	•	解釈フェーズで「次にやるべきテーマ」が 1 つ以上特定されたとき

主な入力
	•	scripts/logs/agi_weakpoints.md
	•	scripts/logs/agi_next_actions.json
	•	既存ドキュメント（docs/*.md, world_state.json の snapshot など）

主な役割
	•	/v1/decide を mode="design_loop" などで呼び、
	•	指定テーマに対する 5〜10 ステップの plan (extras.planner.steps[]) を生成
	•	生成されたプランを markdown / JSON として保存する

担当
	•	VERITAS / PlannerOS:
	•	/v1/decide を plan 用に呼び出し、extras.planner.steps を設計
	•	人間:
	•	プランを読んで「やり過ぎ / 足りない」箇所を微調整

データフロー

flowchart TD
    Weak[agi_weakpoints.md]
    Next[agi_next_actions.json]

    subgraph DesignCall["/v1/decide (design)"]
        Ctx[context: mode="design_loop"]
        PlanReq[query: "この弱点を6ステップで改善計画にして"]
    end

    Weak --> PlanReq
    Next --> PlanReq

    PlanReq --> Planner[planner.plan()]
    Planner --> Kernel[kernel.decide()]
    Kernel --> Resp[decision_json<br>+ extras.planner.steps[]]

    Resp --> PlanFile[docs/plan_YYYYMMDD_*.md<br>scripts/logs/plan_*.json]

出力アーティファクト
	•	docs/plan_2025-11-19_worldmodel_step3.md（例）
	•	scripts/logs/plan_*.json（extras.planner.steps を保存）

⸻

3.4 実装 (Implementation)

目的
	•	設計フェーズで決まったプランに基づき、
実際にコード・スクリプト・ドキュメントを変更する。

トリガー
	•	plan に「コード変更 / スクリプト追加 / Doc 更新」が含まれるとき

主な入力
	•	docs/plan_*.md
	•	scripts/logs/plan_*.json

主な役割
	•	Git ブランチを切り、実験的な変更を行う：
	•	git checkout -b feature/worldmodel-step3
	•	core/kernel.py, core/world.py, scripts/*.py, docs/*.md を編集
	•	小さなコミット単位で変更を積み上げる

担当
	•	人間中心（藤下）
	•	LLM / VERITAS は必要に応じてコード提案やレビュー案内を行う

データフロー

flowchart LR
    Plan[plan_*.md] --> H[Human Dev]
    H --> Code[core/*.py, scripts/*.py, docs/*.md]
    Code --> Git[Git Branch<br>feature/*]
    Git --> PR[実験ブランチとして管理]

出力アーティファクト
	•	Git ブランチ・コミット（例：feature/worldmodel-step3）
	•	更新されたコード / Doc

⸻

3.5 検証 (Evaluation)

目的
	•	実験ブランチの変更が、
	•	メトリクス（latency, value_ema, error_rate など）
	•	AGI 研究 OS としての挙動
を改善しているかどうかを確認する。

トリガー
	•	実験ブランチでの実装がひととおり完了したとき

主な入力
	•	新しいコード（実験ブランチ）
	•	scripts/run_benchmarks.py 実行結果
	•	手動の /v1/decide テスト結果

主な役割
	•	ベンチマーク・自己診断（doctor）を再度回し、
	•	Before / After のメトリクス比較
	•	目標値（例：latency 30%削減）が達成できたか
をチェックする。

担当
	•	自動:
	•	python3 scripts/run_benchmarks.py
	•	python3 scripts/bench_summary.py
	•	python3 scripts/generate_doctor_report.py
	•	人間:
	•	ベンチ結果 / doctor_report / world_state を見て、
「良くなった / 悪くなった / 差がない」を判断

シーケンス

sequenceDiagram
    participant H as Human
    participant B as run_benchmarks.py
    participant S as /v1/decide
    participant W as world.py
    participant M as MemoryOS

    H->>B: python3 scripts/run_benchmarks.py
    B->>S: /v1/decide を複数回叩く
    S->>W: update_from_decision(...)
    S->>M: decision_log, bench_*.json
    B-->>H: ベンチ結果まとめ

    H->>B: python3 scripts/bench_summary.py
    B-->>H: 「Before/After」の主要メトリクス比較

出力アーティファクト
	•	scripts/logs/bench_*.json
	•	scripts/logs/bench_summary_*.md
	•	更新された world_state.json（progress, last_risk, metrics.*）

⸻

3.6 ロールバック / 採用 (Rollback / Adopt)

目的
	•	検証結果に基づき、
	•	変更を採用して main にマージするか
	•	ロールバックするか
を決定し、その結果を world_state に反映する。

判定ロジック（一例）
	•	decision_latency_ms.median が Before 比で +20% 以上悪化 → ロールバック検討
	•	value_ema が一定期間連続で低下 → ロールバック検討
	•	バグ / クラッシュ / FUJI Risk 急上昇 → 即ロールバック

担当
	•	人間: Git での merge / revert を最終決定
	•	VERITAS: /v1/decide で「ロールバック or 採用」の提案は可能

フロー

flowchart TD
    Bench[bench_summary_*.md<br>doctor_report.json] --> Judge[人間の評価]
    Judge -->|改善している| Adopt[main にマージ<br>world.progress 上げる]
    Judge -->|悪化 or 不明| RB[Git revert / ブランチ破棄]

    Adopt --> WorldUpdate[world.update_from_decision<br>progress += Δなど]
    RB --> WorldUpdate2[world.update_from_decision<br>notes に「rollback」記録]

出力アーティファクト
	•	採用時:
	•	main ブランチの更新
	•	world_state.json の progress 上昇・成功メモ
	•	ロールバック時:
	•	revert コミット
	•	world_state.json に「rollback」メモ

⸻

4. 自己改善ループの擬似コード

def veritas_self_improve_cycle():
    # 1) 観測
    doctor_report = generate_doctor_report()  # decision_log / bench_*.json から集計

    # 2) 解釈
    weakpoints, next_actions = call_decide_for_weakpoints(doctor_report)

    # 3) 設計
    plan = call_decide_for_plan(weakpoints, next_actions)
    save_plan(plan)

    # 4) 実装（人間中心）
    implement_plan_in_git_branch(plan)

    # 5) 検証
    before_metrics = load_metrics_snapshot()
    run_benchmarks()
    after_metrics = load_metrics_snapshot()
    summary = compare_metrics(before_metrics, after_metrics)

    # 6) ロールバック / 採用
    decision = human_judgement(summary, plan)
    if decision == "adopt":
        merge_branch_to_main()
        world.note_success(plan, summary)
    else:
        revert_branch()
        world.note_rollback(plan, summary)

5. 責務分担まとめ（Human / VERITAS）
	•	VERITAS / LLM / Core モジュール
	•	doctor_report 生成（集計ロジック）
	•	弱点抽出（Interpretation）
	•	改善プラン設計（Design）
	•	ベンチ実行・結果集計（Evaluation 補助）
	•	人間（藤下）
	•	ループのトリガー実行（スクリプト・Git 操作）
	•	プランのレビュー（やり過ぎ / 足りないの修正）
	•	実際のコード編集・コミット作成（Implementation）
	•	Before/After の最終評価（Evaluation）
	•	採用 or ロールバックの最終判断（Rollback / Adopt）

この仕様に従うことで、VERITAS は
「自分で自分の弱点を見つけ、改善案を出し、人間と協調して進化する AGI 研究 OS」
として運用できる。


