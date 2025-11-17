# VERITAS OS — Proto-AGI Decision OS / Public API

> この README は、`veritas_clean_test2` リポジトリ内の `veritas_os/` ディレクトリ用です。
> まず `veritas_clean_test2` を clone し、その中の `veritas_os` をライブラリとして利用します。

## TL;DR

- VERITAS OS = LLM を **Proto-AGI 的な Decision OS** として包むフレームワーク
- `/v1/decide` で「選択肢生成 → Evidence → Critique → Debate → Safety(FUJI) → TrustLog」を一発実行
- OpenAPI 3.1 + Swagger Studio から、ローカルの uvicorn サーバに直接リクエスト可能
- MemoryOS / WorldModel / ValueCore / FUJI Gate / Doctor Dashboard まで一式内蔵
- 目的：**「LLM を 安全・再現可能・監査可能 な AGI 骨格として使う」ための実験基盤**

VERITAS OS は、LLM（例: OpenAI API）を「そのまま叩く」のではなく、

> **“LLM を安全に・一貫して・検証可能な意思決定エンジンとして動かすための OS”**

として包む **Proto-AGI フレームワーク / Decision OS** です。

Swagger Studio 用の **OpenAPI 3.1 スキーマ** を前提に、

- `/v1/decide` … フル意思決定ループ（ValueCore / FUJI / Memory / WorldModel / ReasonOS）
- `/v1/fuji/validate` … 単体アクションの安全・倫理チェック
- `/v1/memory/*` … 永続メモリの put/get
- `/v1/logs/trust/{request_id}` … 不変のトラストログ取得

を **X-API-Key 認証** 付きの Public API として公開する設計になっています。

---

## 🔧 VERITAS OS の特徴（他のエージェントフレームワークとの違い）

1. **Decision-first 設計**
   - LLM 呼び出しではなく、`/v1/decide` を中心に
   - chosen / alternatives / evidence / critique / debate / fuji / trust_log を毎回返す

2. **Safety & Trust を API レベルで分離**
   - `/v1/fuji/validate` で安全・倫理判定だけを個別に呼べる
   - `/v1/logs/trust/{request_id}` でチェーン化されたトラストログを再取得

3. **Memory / World / ValueCore まで一体になった「Proto-AGI 骨格」**
   - MemoryOS + WorldModel + ValueCore の値が DecideResponse や Doctor Dashboard で可視化される


## 💡 何が嬉しいのか？（Usefulness）

### 1. 「ただの回答」ではなく「決定プロセス」が取れる

`POST /v1/decide` は、Swagger の `DecideResponse` スキーマに従って、毎回必ず:

- `chosen`  
  - `action`: 「今やるべき一手」を短く記述  
  - `rationale`: なぜそれを選んだか  
  - `uncertainty`: 不確実性（0〜1）
- `alternatives[]`（`Option`）  
  他に取り得た選択肢の一覧
- `evidence[]`（`EvidenceItem`）  
  どの証拠を根拠にしたか
- `critique[]` / `debate[]`  
  内部での自己批判・擬似ディベートの結果
- `telos_score`  
  価値・目的への整合性スコア
- `fuji`（`FujiDecision`）  
  安全・倫理ゲートの最終判定（allow / modify / block / abstain）
- `trust_log`  
  チェーン可能なトラストログ（`sha256_prev` 付き）

を返します。

> 「なぜこの一手になったのか？」が構造化されるので、  
> AGI 研究・安全検証・監査用途で使いやすい構造になっています。

---

### 2. AGI 系タスクを「フレームワークごと」扱える

`Context` スキーマ（Swagger 定義）:

```yaml
Context:
  type: object
  required: [user_id, query]
  properties:
    user_id: {type: string}
    session_id: {type: string}
    query: {type: string, description: "ユーザ要求/問題文"}
    goals: {type: array, items: {type: string}}
    constraints: {type: array, items: {type: string}}
    time_horizon: {type: string, enum: ["short","mid","long"]}
    preferences: {type: object}
    tools_allowed: {type: array, items: {type: string}}
    telos_weights:
      type: object
      properties:
        W_Transcendence: {type: number}
        W_Struggle: {type: number}
    affect_hint: {type: string, enum: ["calm","focused","empathetic","concise"]}

AGI 系の問いを投げるときは、ここに
	•	長期/中期の time_horizon
	•	目的関数の重み telos_weights
	•	許可されたツール群 tools_allowed
	•	好みの応答トーン affect_hint

などを入れて、「AGI プロジェクトのメタ意思決定」 を直接叩けます。

例:
「VERITAS の AGI フレームワーク化 MVP を第三者に見せるまでの最短プラン」 を決めさせる:

{
  "context": {
    "user_id": "fujishita",
    "session_id": "sess-agi-mvp-001",
    "query": "VERITASのAGIフレームワーク化MVPを第三者に見せるまでの最短プラン",
    "goals": [
      "第三者が10分でVERITASの全体像を理解できるデモを作る",
      "AGIフレームワークとしての骨格が伝わること"
    ],
    "constraints": [
      "今週中に形にする",
      "ローカル環境 + GitHub + Swagger Studio だけで完結させる"
    ],
    "time_horizon": "short",
    "telos_weights": {
      "W_Transcendence": 0.6,
      "W_Struggle": 0.4
    },
    "affect_hint": "focused"
  },
  "options": [],
  "min_evidence": 2,
  "stream": false
}

これに対し /v1/decide は:
	•	alternatives[] にステップ候補
	•	chosen.action に「今週まずやるべき一手」
	•	telos_score / fuji.status で質と安全を定量化

…という形で返す、「AGI プロジェクトの指揮系統 API」 になります。

⸻

3. 安全ゲート・メモリ・トラストログも API 化されている

Swagger 定義に対応するエンドポイントは以下の通りです（全て X-API-Key 必須）。

GET /health
	•	サーバーのヘルスチェック。200 が返れば OK。

POST /v1/decide
	•	フル意思決定ループ。
	•	Request Body: 上記 context + 任意の options[] / min_evidence / stream
	•	Response: DecideResponse（chosen / alternatives / evidence / fuji / trust_log など）

POST /v1/fuji/validate
	•	単体の action と context に対し、安全・倫理チェックを行う。

{
  "action": "ユーザが指定したAGI実験を本番データで実行する",
  "context": {
    "user_id": "fujishita",
    "query": "この実験は安全か？",
    "time_horizon": "mid"
  }
}

•	Response: FujiDecision
	•	status: allow / modify / block / abstain
	•	reasons[], violations[]

POST /v1/memory/put
	•	永続メモリへの追記。

{
  "user_id": "fujishita",
  "key": "veritas_agi_todos",
  "value": "AGI MVPの優先TODOリスト v1"
}

GET /v1/memory/get
	•	user_id + key から値を取得。

GET /v1/logs/trust/{request_id}
	•	/v1/decide 実行時に積み上げた 不変のトラストログ を再取得。
	•	sha256_prev によりチェーン構造を持つため、「いつ・どんな元で・誰が承認したか」を追跡可能。

⸻

🌐 OpenAPI / Swagger Studio での利用方法

OpenAPI スキーマ:
	•	openapi: 3.1.0
	•	info.title: VERITAS Public API
	•	servers[0].url: http://127.0.0.1:8000
	•	securitySchemes.ApiKeyAuth:
	•	type: apiKey
	•	in: header
	•	name: X-API-Key

Swagger Studio / Editor での手順（想定）
	1.	[Swagger Editor / Swagger Studio] を開く
	2.	左ペインに OpenAPI YAML 全文を貼る
	3.	servers.url が http://127.0.0.1:8000 になっていることを確認
	4.	Authorize ボタンから ApiKeyAuth に X-API-Key を入力
	5.	POST /v1/decide を選んで、Try it out から上記の JSON を実行

これにより、
	•	Editor 上からローカルの uvicorn veritas_os.api.server:app へリクエスト
	•	DecideResponse スキーマで整形された JSON が右側に表示

という、「Swagger Studio から Proto-AGI OS を叩く開発スタイル」 が成立します。

⸻

🛠 セットアップ（veritas_clean_test2 を pull 前提）

veritas_clean_test2 リポジトリにこの veritas_os が含まれている想定です。

0. リポジトリを clone

cd ~
git clone https://github.com/veritasfuji-japan/veritas_clean_test2.git
cd veritas_clean_test2

構成イメージ:

veritas_os/
├─ api/                      # 外部公開API & ダッシュボード
│  ├─ __init__.py
│  ├─ constants.py           # 共通定数
│  ├─ dashboard_server.py    # Doctor Dashboard 用の簡易サーバ
│  ├─ evolver.py             # 将来の自己改善APIの土台
│  ├─ merge_trust_logs.py    # trust_log のマージツール
│  ├─ schemas.py             # FastAPI / Pydantic スキーマ
│  ├─ server.py              # メインAPI (/v1/decide /v1/fuji …)
│  └─ telos.py               # Telos(価値重み)関連のヘルパ
│
├─ core/                     # VERITAS の中枢ロジック（AGI骨格）
│  ├─ __init__.py
│  ├─ models/
│  │  ├─ __init__.py
│  │  └─ memory_model.pkl    # MemoryOS 用の埋め込みモデル
│  ├─ adapt.py               # 自己適応ロジック（将来拡張用）
│  ├─ affect.py              # 口調・感情モジュール
│  ├─ critique.py            # CritiqueOS：自己批判フェーズ
│  ├─ debate.py              # DebateOS：擬似多視点ディベート
│  ├─ evidence.py            # EvidenceOS：証拠収集＋スコアリング
│  ├─ fuji.py                # FUJI Gate：安全・倫理判定
│  ├─ identity.py            # システムID・メタ情報
│  ├─ kernel.py              # 全OSを束ねるコアカーネル
│  ├─ llm_client.py          # OpenAI API ラッパ
│  ├─ logging.py             # ログ共通ユーティリティ
│  ├─ memory.py              # MemoryOS：長期記憶管理
│  ├─ planner.py             # PlannerOS：ステップ分解プランナー
│  ├─ reason.py              # ReasonOS：思考チェーン生成
│  ├─ reflection.py          # ReflectionOS：自己振り返り
│  ├─ rsi.py                 # RSI/自己改善メモ（実験用）
│  ├─ sanitize.py            # 入出力サニタイズ
│  ├─ strategy.py            # 戦略レベルの判断ロジック
│  ├─ tools.py               # 補助ツール群
│  ├─ value_core.py          # ValueCore：価値EMA/next_value_boost
│  ├─ world.py               # WorldOS：状態更新ヘルパ
│  ├─ world_model.py         # WorldModel：世界状態スナップショット
│  │
│  ├─ logging/               # ログ永続化サブモジュール
│  │  ├─ __init__.py
│  │  ├─ dataset_writer.py   # 学習用データ書き出し
│  │  └─ paths.py            # ログパス管理
│  │
│  └─ memory/                # 記憶ベクトル・検索用モジュール
│     ├─ __init__.py
│     ├─ embedder.py         # 埋め込み生成
│     ├─ engine.py           # 検索エンジン本体
│     ├─ episodic.index.npz  # 近傍検索インデックス
│     ├─ index_cosine.py     # Cos類似度検索
│     └─ store.py            # ストレージ層
│
├─ scripts/                  # CLI ツール & 運用スクリプト
│  ├─ alert_doctor.py        # doctor_report からSlackアラート
│  ├─ analyze_logs.py        # decisionログの要約
│  ├─ auto_heal.sh           # 自動復旧（実験用）
│  ├─ backup_logs.sh         # ログZIPバックアップ
│  ├─ decide.py              # CLIから /v1/decide を叩くヘルパ
│  ├─ decide_plan.py         # プランニング専用 decide
│  ├─ doctor.py              # doctor_report.json 生成
│  ├─ doctor.sh              # doctor → report 一括実行
│  ├─ generate_report.py     # HTML ダッシュボード生成
│  ├─ heal.sh                # 簡易ヘルスチェック＆修復
│  ├─ health_check.py        # APIヘルスチェック
│  ├─ memory_sync.py         # memory.json の同期
│  ├─ memory_train.py        # MemoryOS 埋め込み再学習
│  ├─ notify_slack.py        # Slack 通知ユーティリティ
│  ├─ start_server.sh        # uvicorn サーバ起動
│  ├─ sync_to_drive.sh       # rclone で Google Drive バックアップ
│  ├─ veritas.sh             # まとめコマンド（full / decide / report …）
│  └─ veritas_monitor.sh     # 定期監視・自己診断ループ
│
├─ templates/
│  ├─ personas/              # エージェント人格テンプレ
│  ├─ styles/                # 出力スタイルテンプレ
│  └─ tones/                 # 口調プリセット
│
├─ README.md                 # 日本語ドキュメント（このファイル）
├─ README_ENGLISH.md         # 英語版
├─ requirements.txt          # 依存パッケージ
└─ .gitignore

1. Python 仮想環境を作成

cd ~/veritas_clean_test2

# 未インストールなら
brew install python@3.11

python3.11 -m venv .venv
source .venv/bin/activate

2. 依存パッケージをインストール

cd ~/veritas_clean_test2/veritas_os
source ../.venv/bin/activate

export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"

pip install --upgrade pip
pip install joblib
pip install requests
pip install matplotlib
pip install "openai>=1.0.0" scikit-learn

pip install -r requirements.txt

3. データディレクトリを分離（推奨）

cd ~/veritas_clean_test2
export VERITAS_DATA_DIR=~/veritas_clean_test2/data
mkdir -p "$VERITAS_DATA_DIR"

4. API サーバー起動

cd ~/veritas_clean_test2
source .venv/bin/activate

python3 -m uvicorn veritas_os.api.server:app --reload --port 8000

	•	http://127.0.0.1:8000 が OpenAPI servers.url と一致していること
	•	ログに Application startup complete. が出ていれば OK

⸻

🩺 Doctor Dashboard の生成

ログから自己診断レポート（HTML）を生成:

cd ~/veritas_clean_test2/veritas_os/scripts
source ../.venv/bin/activate

python generate_report.py

生成物:
	•	scripts/logs/doctor_report.json
	•	scripts/logs/doctor_dashboard.html

Dashboard では:
	•	決定数の推移（日次）
	•	FUJI ステータス分布
	•	Latency 推移
	•	Memory evidence 件数
	•	Value EMA の推移
	•	Redaction / Modifications 頻度
	•	Memory ヒット率

など、Swagger の DecideResponse では見えない内部メトリクスを俯瞰できます。

⸻

✅ 動作確認環境メモ

この構成は以下の条件で再現確認済み:
	•	macOS
	•	Python 3.11.14
	•	veritas_clean_test2 を GitHub から clone
	•	python3.11 -m venv .venv → pip install -r requirements.txt
	•	python3 -m uvicorn veritas_os.api.server:app --reload --port 8000
	•	OpenAPI 3.1 スキーマを Swagger Studio に貼り付け
	•	X-API-Key 設定後、POST /v1/decide に AGI 系クエリを送信し、正常レスポンスを確認（2025-11-15 時点）

⸻

一言まとめ
	•	VERITAS OS は 「LLM を AGI 的な意思決定エンジンとして包む Public API」 であり、
	•	Swagger Studio / OpenAPI 3.1 とセットで使うことで、
	•	再現性の高い実験
	•	監査可能なトラストログ
	•	安全ゲート付きの意思決定
をすべて HTTP API として扱えるようにすることを目指しています。

本リポジトリは、AGI / AI Safety / AI Alignment 研究者が、

- 「Decision OS」アーキテクチャの実験
- LLM ベースエージェントの安全評価
- 長期メモリ＋トラストログ付きエージェントの挙動解析

をローカルで再現できることを目的としています。
