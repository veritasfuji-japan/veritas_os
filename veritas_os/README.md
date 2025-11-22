VERITAS OS — Proto-AGI Decision OS / Public API

このリポジトリは、LLM（例: OpenAI API）を
「安全・一貫・検証可能な意思決定 OS」 として扱うための
Proto-AGI フレームワーク VERITAS OS の実装です。

⸻

🔥 TL;DR
	•	VERITAS OS = LLM を Proto-AGI 的 Decision OS として包むための OS 層
	•	/v1/decide 1 回で
Options → Evidence → Critique → Debate → Planner → ValueCore → FUJI → TrustLog
までを一括実行
	•	OpenAPI 3.1 + Swagger Studio からローカル FastAPI（uvicorn）を直接叩ける
	•	MemoryOS / WorldModel / ValueCore / FUJI Gate / Doctor Dashboard まで一式内蔵
	•	目的: 「LLM を、安全・再現可能・監査可能な AGI 骨格として使う」ための実験基盤

発想としては「LLM = CPU」、VERITAS = その上に載る
Decision OS / Agent OS という位置づけです。
![IMG_1157](https://github.com/user-attachments/assets/303f2355-4492-48c2-b286-29c35c3476dd)

⸻

🎯 1. 何ができるのか？

1-1. /v1/decide — フル意思決定ループ

POST /v1/decide は、毎回必ず以下を JSON で返します：
	•	chosen … 選ばれた一手（アクション・理由・不確実性）
	•	alternatives[] … 他に取り得た選択肢
	•	evidence[] … 参照した証拠
	•	critique[] … 自己批判
	•	debate[] … 多視点ディベート
	•	telos_score … 価値関数との整合性
	•	fuji … 安全・倫理判定（allow/modify/block/abstain）
	•	trust_log … sha256_prev を持つハッシュチェーンログ
![IMG_1159](https://github.com/user-attachments/assets/66f4e544-d6c8-4364-b8c2-f87504aea4fe)

「なぜこの一手になったか？」が構造化されるので、
AGI 研究 / AI Safety / 監査用途で使いやすい構造になっています。

⸻

1-2. 他 API

すべて X-API-Key ヘッダでの認証が前提です。
Method	Path	説明
GET	/health	サーバのヘルスチェック
POST	/v1/decide	フル意思決定ループ
POST	/v1/fuji/validate	単一アクションの安全・倫理判定
POST	/v1/memory/put	永続メモリへの保存
GET	/v1/memory/get	永続メモリからの取得
GET	/v1/logs/trust/{request_id}	不変のトラストログ（hash chain）取得

🧠 2. Context スキーマ（AGI 用）

AGI 系のメタ意思決定タスクを投げるための Context スキーマは以下です（OpenAPI 3.1 より抜粋）:

Context:
  type: object
  required: [user_id, query]
  properties:
    user_id: { type: string }
    session_id: { type: string }
    query: { type: string, description: "ユーザ要求/問題文" }
    goals: { type: array, items: { type: string } }
    constraints: { type: array, items: { type: string } }
    time_horizon: { type: string, enum: ["short", "mid", "long"] }
    preferences: { type: object }
    tools_allowed: { type: array, items: { type: string } }
    telos_weights:
      type: object
      properties:
        W_Transcendence: { type: number }
        W_Struggle: { type: number }
    affect_hint: { type: string, enum: ["calm", "focused", "empathetic", "concise"] }

これにより、
	•	「AGI 研究プランの最適ステップ」
	•	「自己改善ループの次の一手」
	•	「安全境界を守りながらの実験方針」

などを /v1/decide に直接投げて、OS 側に決めさせる ことができます。

⸻

🏗 3. ディレクトリ構成（veritas_clean_test2）

※ 実際のフォルダ構成を反映しています。

veritas_clean_test2/
├── chainlit_app.py
├── chainlit.md
├── data/
│   └── value_stats.json
├── docs/
│   ├── agi_self_hosting.md
│   ├── bench_summary.md
│   ├── fail_safe.md
│   ├── fuji_gate_safety.md
│   ├── metrics.md
│   ├── module_responsibilities.md
│   ├── self_improvement_commands.md
│   ├── worldmodelstep1.md
│   └── ...
├── veritas_os/
│   ├── api/
│   ├── core/
│   ├── scripts/
│   ├── templates/
│   ├── tools/
│   ├── README.md
│   ├── README_ENGLISH.md
│   └── requirements.txt
├── reports/
├── backups/
├── datasets/
└── .gitignore

🧩 4. veritas_os/core/ 各モジュールの役割

ここが VERITAS OS の心臓部 です。
研究者・企業がコードを読む際に迷わないよう、各 *.py の責務を整理します。
![IMG_1160](https://github.com/user-attachments/assets/0995362a-8026-4fbf-a714-732c1f41fe5b)

4-1. コア OS レイヤ
	•	kernel.py
	•	VERITAS 全体の「オーケストレーター」。
	•	/v1/decide から呼ばれ、
Planner → Evidence → Critique → Debate → FUJI → World/Memory 更新
の全ステップを順に実行して最終 DecideResult を組み立てる。
	•	pipeline.py
	•	決定プロセスの ステージ構成と実行フロー定義。
	•	「どの順番でどの OS を呼ぶか」「途中でどのメトリクスを集計するか」を記述。
	•	planner.py（PlannerOS）
	•	ユーザの query / goals / constraints から
マルチステップのタスク計画 を生成。
	•	「いま取る 1 手」だけでなく、steps 配列として中長期プランを出す。
	•	reason.py（ReasonOS）
	•	LLM による思考展開・鎖状推論（Chain-of-Thought）を扱う層。
	•	Evidence や Critique を踏まえた 内部推論テキストを生成し、
DecideResponse の trace / rationale の土台を作る。
	•	strategy.py
	•	高レベル戦略判断。
	•	「探索/活用のバランス」「どこまでリスクを取るか」など
Macro な意思決定パターンを切り替える。
	•	world.py / world_model.py（WorldOS / WorldModel）
	•	直近の決定やメモリから 世界状態のスナップショット を構築。
	•	「現在のプロジェクトの進行度」「累積リスク」「未処理タスク」などを
JSON 形式の world_state として保持し、次回 Decide に渡す。

⸻

4-2. 安全・価値・自己改善レイヤ
	•	fuji.py（FUJI Gate）
	•	安全・倫理・コンプライアンス観点での最終判定レイヤ。
	•	内部的には
	•	risk_score
	•	violations（どのポリシーに抵触したか）
	•	status: allow | modify | block | abstain
を返し、/v1/fuji/validate API でも単体呼び出し可能。
	•	value_core.py（ValueCore）
	•	VERITAS 独自の 価値 EMA（Exponential Moving Average） を管理。
	•	各 Decide の結果を評価し、「どのような行動が望ましいか」の
内部スカラー指標を更新する。
	•	telos_score や next_value_boost の計算にも利用。
	•	reflection.py（ReflectionOS）
	•	過去の決定ログや Doctor Report を元に 自己振り返り を行う。
	•	「どのパターンのときに失敗しやすいか」「どの質問に弱いか」などを検出し、
Planner / ValueCore にフィードバックする。
	•	adapt.py
	•	将来的な 自己適応・自己改善アルゴリズムの entry point。
	•	現時点では実験的なロジックを配置し、RSI や benchmarks と連携予定。
	•	rsi.py
	•	Self-Improvement / Recursive Self-Improvement に関するメモ・原型。
	•	「どの情報を次の学習サイクルに回すか」などのポリシーを記述（実験用）。

⸻

4-3. 証拠・批判・ディベートレイヤ
	•	evidence.py（EvidenceOS）
	•	Web 検索・MemoryOS・WorldModel などから 証拠候補を収集し、
relevance / reliability 等でスコアリング。
	•	DecideResponse.evidence[] に反映される構造を組み立てる。
	•	critique.py（CritiqueOS）
	•	LLM に自分自身の案を 批判・検証させるためのプロンプトとロジック。
	•	「見落としているリスク」「前提の間違い」を洗い出し、
FUJI / DebateOS に渡す。
	•	debate.py（DebateOS）
	•	賛成・反対・第三視点など 擬似マルチエージェントのディベートを実行。
	•	各立場の論点を構造化し、それを要約したうえで最終 chosen に影響させる。

⸻

4-4. MemoryOS レイヤ
	•	memory.py（MemoryOS フロント）
	•	scripts/logs/memory.json を中心とした 長期メモリ管理。
	•	エピソード・決定・メタ情報を JSON で保存し、
MemoryOS.search() で類似決定を検索する。
	•	内部で core/memory/* の埋め込み/インデックスを利用。
	•	core/memory/embedder.py
	•	メモリ用の 埋め込みベクトル生成。
	•	現状は軽量モデル＋キャッシュで動作。
	•	core/memory/engine.py
	•	コサイン類似度等を用いた 近傍検索エンジン本体。
	•	episodic.index.npz / semantic.index.npz を扱い、
高速検索を提供。
	•	core/memory/index_cosine.py
	•	CosineIndex 実装。
	•	add() / search() など低レベル API を提供し、
上位の MemoryOS から呼ばれる。
	•	core/memory/store.py
	•	JSONL などのストレージ形式をラップした シンプルなストア層。
	•	インデックスと生データの一貫性を保証。

⸻

4-5. LLM クライアント & ロギング
	•	llm_client.py
	•	OpenAI API 等へのアクセスを一元管理するラッパ。
	•	モデル切り替え・リトライ・タイムアウトなどを吸収して、
上位モジュールからは「関数呼び出し」感覚で使えるようにする。
	•	logging.py（共通ログユーティリティ）
	•	Decide や FUJI で使用するログ書き出しヘルパ。
	•	logs/ 以下のパスは core/logging/paths.py で一括管理。
	•	core/logging/dataset_writer.py
	•	決定ログを後で 学習用データセットとして再利用するための出力モジュール。
	•	datasets/dataset.jsonl などに書き出す。
	•	core/logging/paths.py
	•	ローカルのログ/レポート/バックアップのパス定義。
	•	VERITAS_DATA_DIR などの環境変数と連動。

⸻

4-6. 口調・スタイル / カリキュラム・実験
	•	affect.py
	•	応答の トーンや感情（calm/focused/empathetic など） を制御。
	•	Context.affect_hint と連動して、LLM プロンプトの文体を切り替える。
	•	curriculum.py
	•	自己学習・自己評価用の カリキュラム生成ロジック。
	•	benchmarks（docs/ / datasets/）と連携して
「どの課題で練習するか」を決める。
	•	experiment.py
	•	AGI 実験用のスクリプト／ユーティリティ。
	•	決定 OS の挙動をベンチマーク・AB テストするコードを配置。

⸻

4-7. サニタイズ・ツール群
	•	sanitize.py
	•	Prompt / Response からの 危険情報・PII・制御文字の除去。
	•	FUJI とは別に「純粋なテキストクリーニング」を担当。
	•	tools.py
	•	汎用ユーティリティ／小さなツール類。
	•	日付フォーマット・ID 生成等、複数モジュールで再利用される関数群。
	•	identity.py
	•	VERITAS インスタンスの ID / バージョン / メタ情報。
	•	Doctor Dashboard や logs に表示される「システム自己紹介」をここで定義。

⸻

🚀 5. API サーバ起動までの手順
	1.	クローン

git clone https://github.com/veritasfuji-japan/veritas_clean_test2.git
cd veritas_clean_test2

2.	仮想環境

python3.11 -m venv .venv
source .venv/bin/activate

3.	依存インストール

pip install -r requirements.txt
export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"

	4.	サーバ起動

python3 -m uvicorn veritas_os.api.server:app --reload --port 8000

	5.	Swagger / OpenAPI から叩く

	•	OpenAPI 3.1 スキーマを Swagger Editor / Studio にロード
	•	servers[0].url = http://127.0.0.1:8000 を確認
	•	Authorize から X-API-Key を設定
	•	POST /v1/decide にサンプル JSON を送信して動作確認

⸻

📊 6. Doctor Dashboard

cd veritas_os/scripts
source ../.venv/bin/activate
python generate_report.py

生成されるもの：
	•	scripts/logs/doctor_report.json
	•	scripts/logs/doctor_dashboard.html

ここで：
	•	Decide 実行数の推移
	•	FUJI 判定の分布
	•	メモリヒット数
	•	Value EMA の変化
	•	unsafe / modified アクションの頻度
	•	レイテンシ分布

などをブラウザで確認できます。

⸻

✅ 7. 動作確認済み環境
	•	macOS
	•	Python 3.11.x
	•	uvicorn + fastapi
	•	OpenAI API (gpt 系モデル)
	•	Swagger Editor / Swagger Studio

⸻

🧵 8. まとめ
	•	VERITAS OS は LLM を AGI 的な意思決定エンジンとして包むための OS 層
	•	Decision / Safety / Memory / Value / WorldModel / TrustLog が一体になっている
	•	研究者・企業が AGI / AI Safety / Alignment 実験をローカルで再現できることを狙ったプロジェクトです

Copyright (c) 2025 Takeshi Fujishita
All Rights Reserved.
