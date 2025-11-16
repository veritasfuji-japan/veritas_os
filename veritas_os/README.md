# VERITAS OS — Technical Overview for Researchers

**Status**: Single-user AGI-OS prototype (local only)  
**Domain**: Long-horizon decision support, self-monitoring agent  
**Author**: FUJISHITA (ERASER)  

---

## 1. Abstract

VERITAS は「大規模言語モデルの上に乗る OS」として設計された、  
**1ユーザー専用の長期意思決定エージェント**です。

特徴は次の 4 点です：

1. **ValueCore**:  
   すべての decision に対して「倫理・合法性・リスク・ユーザー利益」を数値化し、  
   ローカルの `value_core.json` に蓄積された重みに基づいて評価する。

2. **MemoryOS**:  
   `memory/` フォルダの JSONL / ベクトルインデックスにエピソード記憶・セマンティック記憶・
   skill 記憶を保存し、decision ごとに関連 evidence を引き当てる。

3. **WorldModel + WorldState**:  
   `world_state.json` にタスクごとの進捗・リスク・ decision_count などを記録し、  
   「どのプロジェクトがどのフェーズにいるか」を OS として管理する。

4. **FUJI Gate + Doctor**:  
   decision 前後に安全フィルタ（FUJI）と自己監査（Doctor）を挟み、  
   リスクが高い提案を抑制しながら、ログからエージェントの健全性を診断する。

本リポジトリは、上記の OS を **FastAPI / CLI / ローカルファイル**のみで成立させる  
ミニマルな実装を目指している。

---

## 2. Repository Layout

実際のフォルダ構成（2025-11-14 時点）は概ね次の通り：

```text
veritas/
  README.md
  requirements.txt
  __init__.py
  .gitignore

  api/
    server.py          # FastAPI app ( /v1/decide, /api/status など )
    schemas.py         # Pydantic models
    telos.py           # Telos / value 設定関連の API
    constants.py       # API レベルの定数
    ...

  core/
    config.py          # 設定（API key, data_dir など, ダミー値＋env）
    kernel.py          # decide() のコアロジック
    value_core.py      # ValueCore スコア計算
    world.py           # World state 更新ロジック
    world_model.py     # world_state.json の Pydantic モデル
    planner.py         # マルチステップの計画生成
    memory.py          # MemoryOS エントリポイント
    debate.py          # 簡易 DebateOS
    critique.py        # 簡易 CritiqueOS
    fuji.py            # FUJI Gate (safety)
    rsi.py             # self-improvement hooks (RSI placeholder)
    strategy.py        # 高レベル戦略 decision
    logging.py         # 構造化ログ出力
    tools.py           # 補助ユーティリティ
    adapt.py           # persona / bias 学習
    affect.py          # トーン・感情モジュール
    identity.py        # エージェント自己記述
    llm_client.py      # LLM 呼び出し抽象化
    models/
      memory_model.pkl # MemoryOS 用の軽量エンコーダモデル
    ...

  memory/
    episodic.jsonl     # 対話エピソード (time, query, decision, meta)
    semantic.jsonl     # 知識ベース的メモ
    skills.jsonl       # 汎用スキルの記述
    episodic.index.npz # ベクトルインデックス (cosine)
    semantic.index.npz # ベクトルインデックス (cosine)
    skills.index.npz   # ベクトルインデックス (cosine)
    memory.json        # MemoryOS のメタ情報

  logs/
    doctor_auto.log    # 自動ヘルスチェックのログ
    doctor_auto.err
    cron.log
    DASH/decide_*.json # decision スナップショット (UI 用)

  reports/
    doctor_dashboard.html  # HTML ダッシュボード（自己監査）
    doctor_report.json     # 集計済みメトリクス
    ...

  scripts/
    decide.py          # CLI から /v1/decide を叩く
    decide_plan.py     # プランナー向けの質問テンプレ
    health_check.py    # ログを読み、Doctor レポート生成
    generate_report.py # HTML ダッシュボード生成
    memory_train.py    # MemoryOS の埋め込み再生成
    memory_sync.py     # memory/ と .veritas を同期
    auto_heal.sh       # ログを見て簡易自己修復を走らせる
    backup_logs.sh     # trust_log バックアップ
    sync_to_drive.sh   # rclone で外部ストレージへ同期（任意）
    start_server.sh    # uvicorn 起動ラッパ
    veritas.sh         # CLI entrypoint ラッパ
    ...

  templates/
    personas/
      default.txt      # デフォルト persona プロンプト
    styles/
      concise.txt
      deep.txt
    tones/
      friendly.txt
      serious.txt

  trust_log.json       # decision ログ（JSON）
  trust_log.jsonl      # decision ログ（1行1 decision）
  value_core.json      # ValueCore の現在の重み
  value_stats.json     # value スコアの統計
  world_state.json     # WorldModel スナップショット


3. Decision Pipeline

3.1 API Entry: /v1/decide
	•	実装ファイル: api/server.py
	•	ハンドラは概ね以下の情報を受け取る:

{
  "query": "自然言語の質問 / 指示",
  "alternatives": [ /* 任意の候補アクション */ ],
  "context": {
    "user_id": "veritas_dev",
    "stakes": 0.5,
    "telos_weights": { "W_Transcendence": 0.6, "W_Struggle": 0.4 },
    ...
  }
}

3.2 High-level Flow
	1.	FUJI Pre-check core.fuji.pre_check()
	•	内容・stakes をざっくり評価し、明らかなハイリスクを early block / warn。
	2.	Memory Retrieval core.memory.retrieve()
	•	memory/episodic.jsonl, semantic.jsonl, skills.jsonl から
query に近いトップ k をベクトル検索（index_cosine.py）し、
evidence として準備。
	3.	PlannerOS core.planner.plan()
	•	LLM を使って query に対する 3〜5 ステップ程度の
「マイクロプラン」を生成。
	•	各ステップには (id, title, detail, eta_hours, risk, dependencies) を付与。
	4.	Kernel Decide core.kernel.decide()
	•	intent 推定（_detect_intent）
	•	alternatives がなければ intent ベースのデフォルト options を生成。
	•	alternatives があればそれをベースに、Planner からのステップを merge。
	•	adapt.clean_bias_weights() を通して persona バイアスをロード。
	•	ValueCore & persona バイアスに基づいて各 option をスコアリング。
	•	chosen = argmax(score) を決定し、決定理由を evidence に追記。
	•	trust_log への書き込みに備えて metadata を整理。
	5.	ValueCore Scoring core.value_core.score()
	•	ethics, legality, harm_avoid, truthfulness, user_benefit,
reversibility, accountability, efficiency, autonomy などの
次元で [0,1] スコアを付与。
	•	telos_weights から Telos スカラー (telos_score) を計算。
	•	total スコアと top_factors を返す。
	6.	FUJI Post-check core.fuji.post_check()
	•	chosen option と ValueCore スコアを見て、
「allow / modify / block」 の最終判断。
	•	必要に応じて decison_status を block に変え、
safe な代替指示を生成する。
	7.	WorldModel Update core.world.update()
	•	タスク ID（例: veritas_agi）に紐づいて
decision_count, progress, last_risk, notes を更新し、
world_state.json に保存。
	8.	Logging / Learning
	•	trust_log.jsonl に decision を追記。
	•	adapt.update_persona_bias_from_history() により、
trust_log から好まれた選択肢を EMA で学習し、persona.json を更新。

⸻

4. MemoryOS Design

4.1 Data Layout
	•	memory/episodic.jsonl
	•	各行が 1 エピソード。
	•	例: { "ts": "...", "query": "...", "decision": {...}, "tags": ["AGI", "VERITAS"] }
	•	memory/semantic.jsonl
	•	長期的に有用な知識・構造化されたメモ。
	•	memory/skills.jsonl
	•	手順系の知識（例:「GitHub への push 手順」）を
「title, steps[]」の形式で保存。
	•	*.index.npz
	•	上記 JSONL に対する埋め込みベクトルと index。
	•	core/memory/embedder.py + 軽量モデル (memory_model.pkl) を利用。

4.2 Retrieval Algorithm (概要)
	1.	query を埋め込みに変換
	2.	各インデックスに対して cos 類似度検索
	3.	上位 k 件をフィルタ（スコア閾値＋新しさなど）
	4.	evidence[] に {source, uri, snippet, confidence} 形式で渡す

VERITAS の decision は常に「自分の過去ログ・メモリ」を参照するため、
同じユーザーに強く最適化されたエージェントになる。

⸻

5. ValueCore & Telos
	•	value_core.json に各 value の重み・統計を保存。
	•	Telos は "Transcendence" と "Struggle" の 2 軸で表現され、
コンフィグ (telos_default_WT, telos_default_WS) または
リクエスト context.telos_weights により調整可能。

Telos スコア例: W_T = cfg.telos_default_WT   # default 0.6
W_S = cfg.telos_default_WS   # default 0.4
telos_score = 0.5 * W_T + 0.5 * W_S    # 0.0〜1.0

ValueCore は、decision ごとの value スコアを trust_log.jsonl に残し、
scripts/analyze_logs.py や reports/doctor_dashboard.html から
「最近の decision がどの価値軸に偏っているか」を可視化できる。

⸻

6. Safety Layer: FUJI Gate

core/fuji.py では、decision の前後で簡易的な安全判定を行う。
	•	前処理 (pre)
	•	入力 query と stakes をみて、
「自傷」「違法」「プライバシー侵害」などのパターンを簡易判定。
	•	明らかな NG はブロック、グレーなものは risk を引き上げる。
	•	後処理 (post)
	•	ValueCore のスコアが閾値を下回る場合、
	•	decision を block
	•	より安全な代替案に差し替え
	•	あるいは「人間のレビューを要求」といった指示に変更

FUJI Gate はルールベース＋LLM ヘルパー（llm_client.py）で動く想定で、
実装はミニマルだが「OS 側に安全レイヤーを置く」設計を強調している。

⸻

7. Self-Monitoring (Doctor / Auto-heal)
	•	scripts/health_check.py
	•	trust_log.jsonl, logs/*.log を集計し、
	•	エラー率
	•	block された decision の割合
	•	高リスク decision の頻度
	•	ValueCore スコアのトレンド
などを算出。
	•	reports/doctor_dashboard.html
	•	上記メトリクスを HTML で可視化。
	•	「どのくらい安定しているか」「どこに偏りがあるか」が一目でわかる。
	•	scripts/auto_heal.sh
	•	Cron 等から定期的に呼び出し、
	•	エラーが増えている場合: サービス再起動 / ログローテーション
	•	インデックスが壊れている場合: 再構築
といった軽量な自己修復アクションを実行する設計。

⸻

8. LLM Integration

現状の実装では、LLM 呼び出しは core/llm_client.py に隠蔽されている。
	•	OpenAI など特定ベンダーに依存しないよう、
「chat(model, messages, **kwargs)」程度の薄い抽象のみ定義。
	•	研究用途では、ここを差し替えることで
さまざまなモデル（GPT-4.x, Claude, Grok, ローカルモデルなど）を
同じ OS 上で比較することができる。

⸻

9. Extensibility

研究者が触りたいポイント：
	1.	独自 Memory スキーマ
	•	memory/*.jsonl のフォーマットを変えることで、
ドメイン特化の knowledge graph 的な構造も検証可能。
	2.	ValueCore の拡張
	•	追加の value 軸（例: sustainability, fairness, privacy）を
value_core.py に実装し、value_core.json で重み管理。
	3.	FUJI プラグイン
	•	新しい安全チェック（法規制ベース、企業ポリシー等）を
module として追加可能。
	4.	Tool Integration
	•	LLM から外部ツールを叩く場合も、
OS 側で logging / value 評価 / FUJI Gate を通すことで、
「実世界のアクションに対する責任」をトレースできる。

⸻

10. Limitations / Non-Goals

現時点での VERITAS は、AGI そのものではなく、
	•	シングルユーザー
	•	ローカルファイルベース
	•	1台のマシン上で完結する

**「AGI 風 OS 層」**のプロトタイプに留まる。

特に次のような点は未実装 or 検証中：
	•	大規模マルチユーザー / 分散環境での動作
	•	学習ループの完全自動化（human-in-the-loop 前提）
	•	強い意味での「自己改善アルゴリズム」の安全性証明
	•	RLHF / bandit 的な formal な学習理論

⸻

11. Positioning

研究的には、VERITAS は以下の交差点に位置づけられる：
	•	Personal AI / LifeOS 系の「ユーザー中央のエージェント」
	•	Tools-using LLM より一段上にある オーケストレーション層
	•	Value-aware / Safety-aware decision making の実験プラットフォーム
	•	Long-term memory + world model を持つ「自己監査エージェント」

⸻

12. Contact / Usage

本リポジトリは現在 非公開・共同研究候補への限定共有 を想定している。
興味がある研究者の方は、作者（FUJISHITA）まで直接連絡をお願いしたい。

