VERITAS OS v2.0 — Proto-AGI Decision OS



[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.17688094.svg)](https://doi.org/10.5281/zenodo.17688094)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-All%20Rights%20Reserved-red.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-Production%20Ready%20(98%25)-green.svg)]()



Version: 2.0.0
Release Date: 2025-12-01
Author: Takeshi Fujishita

このリポジトリは、LLM（例: OpenAI GPT-4.1 mini）を
「安全・一貫・検証可能な意思決定 OS」 として扱うための
Proto-AGI フレームワーク VERITAS OS の実装です。

発想: 「LLM = CPU」 / 「VERITAS OS = その上に載る Decision OS / Agent OS」

日本語 README（このファイル）

英語 README: veritas_os/README_ENGLISH.md

🔥 TL;DR

VERITAS OS = LLM を Proto-AGI 的な Decision OS として包むための OS 層

/v1/decide 1回で以下を決定論的パイプラインで実行:

Options → Evidence → Critique → Debate → Planner → ValueCore → FUJI → TrustLog


OpenAPI 3.1 + Swagger UI からローカル FastAPI サーバーを直接叩ける

MemoryOS / WorldModel / ValueCore / FUJI Gate / TrustLog / Doctor Dashboard まで一式内蔵

目的: 「LLM を、安全・再現可能・監査可能な Proto-AGI 骨格として使う」ための研究・実験基盤

📑 目次

何ができるのか？

Context スキーマ（AGI用）

ディレクトリ構成

core/ 各モジュールの役割

LLM クライアント

TrustLog & Dataset

Doctor Dashboard

クイックスタート

開発ガイド

トラブルシューティング

ライセンス

コントリビューション / 謝辞 / お問い合わせ

🎯 1. 何ができるのか？
1.1 /v1/decide — フル意思決定ループ

POST /v1/decide は、毎回必ず以下を JSON で返します：

フィールド	説明
chosen	選ばれた一手（アクション・理由・不確実性など）
alternatives[]	他に取り得た選択肢
evidence[]	参照した証拠（MemoryOS / WorldModel / Web 等）
critique[]	自己批判・弱点の指摘
debate[]	擬似マルチエージェントによるディベート結果
telos_score	ValueCore が定義する価値関数との整合性スコア
fuji	FUJI Gate による安全・倫理判定（allow / modify / rejected）
gate.decision_status	DecisionStatus Enum 準拠の判定ステータス
trust_log	sha256_prev を持つハッシュチェーンログ（監査用 TrustLog エントリ）

「なぜこの一手になったか？」が構造化される ため、
AGI研究 / AI Safety / エンタープライズ監査用途で扱いやすい形になっています。

1.2 その他の API

すべて X-API-Key ヘッダでの認証が前提です。

Method	Path	説明
GET	/health	サーバのヘルスチェック
POST	/v1/decide	フル意思決定ループ
POST	/v1/fuji/validate	単一アクションの安全・倫理判定
POST	/v1/memory/put	永続メモリへの保存
GET	/v1/memory/get	永続メモリからの取得
GET	/v1/logs/trust/{id}	不変のトラストログ（hash chain）取得
🧠 2. Context スキーマ（AGI用）

AGI系のメタ意思決定タスクを投げるための Context スキーマ:

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


これにより、以下のような問いを /v1/decide に投げて、
OS 側に 段階的プランと一手の選択 を任せることができます:

「AGI研究プランの次の最適ステップは？」

「自己改善ループをどう設計すべきか？」

「安全境界を守りながら、どこまで実験してよいか？」

🏗 3. ディレクトリ構成
3.1 ルート構成
veritas_clean_test2/
├── chainlit_app.py
├── chainlit.md
├── data/
│   └── value_stats.json
├── docs/
│   ├── images/
│   │   ├── architecture.png
│   │   ├── pipeline.png
│   │   └── modules.png
│   ├── agi_self_hosting.md
│   ├── bench_summary.md
│   ├── fail_safe.md
│   ├── fuji_gate_safety.md
│   ├── metrics.md
│   ├── module_responsibilities.md
│   ├── self_improvement_commands.md
│   └── worldmodelstep1.md
├── veritas_os/
│   ├── api/
│   ├── core/
│   ├── logging/
│   ├── scripts/
│   ├── templates/
│   ├── tools/
│   ├── README.md           # モジュール単位の説明
│   ├── README_ENGLISH.md   # 英語版 README（詳細）
│   └── requirements.txt
├── reports/
├── backups/
├── datasets/
├── veritas.sh
├── .gitignore
└── LICENSE

3.2 veritas_os/core/ の構造（概要）
veritas_os/core/
├── __init__.py
├── adapt.py
├── affect.py
├── agi_goals.py
├── code_planner.py
├── config.py
├── critique.py
├── curriculum.py
├── debate.py
├── decision_status.py
├── doctor.py
├── evidence.py
├── experiment.py
├── fuji.py
├── identity.py
├── kernel.py
├── llm_client.py
├── logging.py
├── memory.py
├── pipeline.py
├── planner.py
├── reason.py
├── reflection.py
├── rsi.py
├── sanitize.py
├── strategy.py
├── tools.py
├── value_core.py
├── world.py
├── world_model.py.old
└── models/
    ├── __init__.py
    ├── memory_model.py
    ├── memory_model.py.old
    └── vector_index.pkl


※ __pycache__ や .DS_Store 等の自動生成ファイルは省略。

🧩 4. core/ 各モジュールの役割
4.1 コア OS レイヤ

kernel.py
VERITAS 全体のオーケストレーター。
/v1/decide から呼ばれ、Planner → Evidence → Critique → Debate → FUJI → World/Memory 更新を実行し、DecideResult を組み立てます。

pipeline.py
決定プロセスのステージ構成・実行フロー定義。
どの順番でどの OS を呼ぶか、途中でどのメトリクスを集計するか、を定義。

planner.py (PlannerOS)
query / goals / constraints からマルチステップのタスク計画を生成。
「今取る一手」だけでなく、中長期プラン (steps[]) も出力。

reason.py (ReasonOS)
Evidence / Critique を踏まえた思考展開・Chain-of-Thought を担当。
DecideResponse.trace / rationale の土台となるテキストを生成。

strategy.py
探索 vs 活用、どこまでリスクを取りに行くか、などの
高レベル戦略判断を行うモジュール（実験的要素を含む）。

world.py / world_model.py(old) (WorldOS / WorldModel)
直近の決定・メモリを元に世界状態のスナップショットを構築。
未処理タスク、累積リスクなどを JSON として保存し、次回 /v1/decide に渡します。

4.2 安全・価値・自己改善レイヤ

fuji.py (FUJI Gate)
安全・倫理・コンプライアンス観点の最終判定レイヤ。

risk_score

violations[]（どのポリシーに触れているか）

status: allow / modify / rejected

decision_status.py
FUJI Gate の判定を Enum 化した決定ステータス。

class DecisionStatus(str, Enum):
    ALLOW = "allow"
    MODIFY = "modify"
    REJECTED = "rejected"


既存コードとの互換性のために文字列定数も提供しています（DECISION_ALLOW など）。

value_core.py (ValueCore)
VERITAS 独自の 価値 EMA (Exponential Moving Average) を管理。
各決定結果の「良さ」をスカラーでロギングし、telos_score や
将来の方策更新の土台として利用。

reflection.py (ReflectionOS)
過去の決定ログや Doctor Report をもとに自己振り返りを行う。
「どの条件で失敗しやすいか」「どの質問が苦手か」を分析し、Planner / ValueCore へフィードバック。

adapt.py / rsi.py
将来の 自己適応・自己改善アルゴリズム（RSI） のエントリポイント／実験用コード。

4.3 証拠・批判・ディベート

evidence.py (EvidenceOS)
MemoryOS / WorldModel / Web 検索などから証拠候補を収集し、
relevance / reliability を元にスコアリングして evidence[] に反映。

critique.py (CritiqueOS)
LLM による自己批判・検証ロジック。
見落としているリスク、誤った前提を洗い出す役割。

debate.py (DebateOS)
賛成・反対・第三視点など複数の立場から擬似マルチエージェントディベートを行う。
ディベート結果は debate[] に構造化され、chosen へ影響します。

4.4 MemoryOS

memory.py (MemoryOS フロント)
scripts/logs/memory.json を中心とした長期メモリ管理。

エピソード／決定／メタ情報を JSON として保存

類似決定の検索

内部的には core/models/memory_model.py 等のインデックスを利用

models/memory_model.py / models/vector_index.pkl
メモリ用の埋め込みモデル・インデックス（ベクトル検索）を扱う層。

4.5 LLM クライアント & ロギング

llm_client.py
LLM 呼び出しの単一エントリポイント。

現バージョンは OpenAI GPT-4 系（gpt-4.1-mini 相当）を前提
（環境変数 OPENAI_API_KEY, LLM_MODEL で切替可能）

共通のリトライ・タイムアウト・ログ処理を実装

将来的に Claude / Gemini / ローカルモデル（Ollama 等）へ拡張予定

logging.py
OS 全体が共通で使うログユーティリティ。
特に、論文準拠:

hₜ = SHA256(hₜ₋₁ || rₜ)

を満たす TrustLog のハッシュチェーンを append_trust_log() で実装。
sha256_prev と sha256 を自動的に埋め、JSONL として追記します。

4.6 ログ / データセット / パス管理

veritas_os/logging/dataset_writer.py

決定ログを後で学習用データセットとして再利用するためのモジュール。

主な機能:

build_dataset_record(req, res, meta, eval_meta)
→ 1 決定分の正規化レコードを構築

append_dataset_record(record, path=DATASET_JSONL)
→ datasets/dataset.jsonl に追記

get_dataset_stats()
→ ステータス分布 / メモリ使用率 / 平均スコア / 日付範囲を集計

search_dataset(query, status, memory_used, limit)
→ dataset.jsonl を簡易検索

ここにも DecisionStatus ベースのラベル情報が含まれます。

veritas_os/logging/paths.py
ログ / レポート / バックアップ / Dataset のファイルパス定義。
環境変数 VERITAS_DATA_DIR などと連動。

4.7 口調・カリキュラム・実験 / ツール

affect.py
応答の**トーン・感情（calm / focused / empathetic / concise）**を制御。
Context.affect_hint と連動してプロンプト文体を切り替えます。

curriculum.py / experiment.py
自己学習用のカリキュラム生成と AGI 実験ユーティリティ。
ベンチマーク（docs/bench_summary.md など）と連携。

sanitize.py
テキストからの PII / 制御文字 / 危険情報のサニタイズ。
FUJI Gate とは別に、純粋なテキストクリーニングを担当。

tools.py / identity.py
各所で使うユーティリティ関数、そして VERITAS インスタンスの
ID / バージョン / 自己紹介文の定義。

🧠 5. LLM クライアント

現バージョンの前提:

使用プロバイダ: OpenAI

想定モデル: gpt-4.1-mini 系（環境変数で変更可）

将来拡張: Claude / Gemini / ローカルモデル（Ollama）など

設定例:

export OPENAI_API_KEY="sk-..."
export LLM_PROVIDER="openai"      # 現状は openai 固定運用を想定
export LLM_MODEL="gpt-4.1-mini"
export LLM_TIMEOUT="60"
export LLM_MAX_RETRIES="3"

🔐 6. TrustLog & Dataset
6.1 TrustLog (ハッシュチェーン監査ログ)

実装: veritas_os/core/logging.py

出力先: scripts/logs/trust_log*.jsonl など

形式: JSON Lines（1 行 1 エントリ）

各エントリ:

sha256_prev: 直前エントリの sha256

sha256: SHA256(sha256_prev || entry_without_hashes)
（初回は sha256_prev=None のみで計算）

マージ・再ハッシュ

複数のログファイルをマージしつつ、
request_id／timestamp ベースで重複を除去し、
チェーンを再計算するスクリプト:

cd veritas_os
python -m veritas_os.api.merge_trust_logs \
  --out scripts/logs/trust_log_merged.jsonl


デフォルトでは既定のログパスを自動探索

--no-rehash でハッシュ再計算を抑止可能（推奨は再計算 ON）

6.2 Dataset 出力

dataset_writer.py により、
決定結果を datasets/dataset.jsonl に蓄積し、
後で学習データセットとして再利用できます。

from veritas_os.logging.dataset_writer import (
    build_dataset_record,
    append_dataset_record,
    get_dataset_stats,
    search_dataset,
)


labels.status は DecisionStatus に対応 ("allow" / "modify" / "rejected")

memory_used / telos_score / utility なども含まれるため
「安全で良い決定」を学習ターゲットとして抽出可能。

📊 7. Doctor Dashboard

システムの健康状態を可視化する Doctor Dashboard を提供します。

7.1 レポート生成
cd veritas_os/scripts
source ../.venv/bin/activate
python generate_report.py


生成物:

scripts/logs/doctor_report.json

scripts/logs/doctor_dashboard.html

内容（例）:

Decide 実行数の推移

FUJI 判定の分布（allow / modify / rejected）

MemoryOS のヒット数

Value EMA の推移

unsafe / modified アクションの比率

レイテンシ分布

7.2 認証付き Dashboard Server（オプション）

dashboard_server.py（FastAPI ベース）を起動すると、
Basic 認証付き Web ダッシュボードとして閲覧できます。

export DASHBOARD_USERNAME="veritas"
export DASHBOARD_PASSWORD="your_secure_password"
export VERITAS_LOG_DIR="/path/to/veritas_os/scripts/logs"  # 省略可

python veritas_os/api/dashboard_server.py
# or: python veritas_os/scripts/dashboard_server.py


アクセス: http://localhost:8000/ または /dashboard

API: http://localhost:8000/api/status
→ drive_sync_status.json を JSON で返す

認証不要のヘルスチェック: GET /health

🚀 8. クイックスタート
8.1 インストール
# 1. クローン
git clone https://github.com/veritasfuji-japan/veritas_clean_test2.git
cd veritas_clean_test2

# 2. 仮想環境
python3.11 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. 依存インストール
pip install -r veritas_os/requirements.txt

# 4. 必須環境変数
export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
export VERITAS_API_KEY="your-secret-api-key"  # X-API-Key 用

8.2 API サーバー起動
python3 -m uvicorn veritas_os.api.server:app --reload --port 8000

8.3 動作確認（Swagger UI）

ブラウザで http://127.0.0.1:8000/docs
 を開く

Authorize ボタン → X-API-Key に VERITAS_API_KEY を入力

POST /v1/decide を選択し、以下のような JSON を送信:

{
  "query": "明日の天気を確認してから外出すべきか?",
  "context": {
    "user_id": "test_user",
    "goals": ["健康", "効率"],
    "constraints": ["時間制約"]
  }
}

8.4 curl 例
curl -X POST "http://127.0.0.1:8000/v1/decide" \
  -H "X-API-Key: your-secret-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "明日の天気を確認してから外出すべきか?",
    "context": {
      "user_id": "test_user",
      "goals": ["健康", "効率"]
    }
  }'

🛠 9. 開発ガイド
9.1 環境構築
# 開発用依存関係（存在する場合）
pip install -r requirements-dev.txt

# pre-commit（設定済みの場合）
pre-commit install

9.2 テスト
# ユニットテスト
pytest tests/

# カバレッジ
pytest --cov=veritas_os tests/

9.3 コード品質
# Lint
flake8 veritas_os/
pylint veritas_os/

# フォーマット
black veritas_os/
isort veritas_os/

# 型チェック
mypy veritas_os/

❓ 10. トラブルシューティング
Q: OPENAI_API_KEY が見つからない

A: 環境変数を設定してください。

echo $OPENAI_API_KEY
export OPENAI_API_KEY="sk-..."

Q: Port 8000 already in use

A: 別のポートを指定します。

uvicorn veritas_os.api.server:app --reload --port 8001

Q: メモリが永続化されない

A: VERITAS_DATA_DIR を設定し、書き込み権限を確認してください。

export VERITAS_DATA_DIR="/path/to/veritas_data"
mkdir -p "$VERITAS_DATA_DIR"

Q: TrustLog の検証に失敗する

A: マージ済みログを検証してください。

cd veritas_os/scripts
python verify_trust_log.py        # 実装されている場合
# または
python ../api/merge_trust_logs.py --out logs/trust_log_merged.jsonl

📜 11. ライセンス
Copyright (c) 2025 Takeshi Fujishita
All Rights Reserved.


学術利用: 以下の DOI を引用してください。

@software{veritas_os_2025,
  author = {Fujishita, Takeshi},
  title = {VERITAS OS: Proto-AGI Decision OS},
  year = {2025},
  doi = {10.5281/zenodo.17688094},
  url = {https://github.com/veritasfuji-japan/veritas_clean_test2}
}

🤝 12. コントリビューション / 謝辞 / お問い合わせ
コントリビューション

プルリクエストを歓迎します。

Fork the repository

Create your feature branch (git checkout -b feature/AmazingFeature)

Commit your changes (git commit -m 'Add some AmazingFeature')

Push to the branch (git push origin feature/AmazingFeature)

Open a Pull Request

詳細は（用意されていれば）CONTRIBUTING.md を参照してください。

謝辞

このプロジェクトは以下の研究・技術の影響を受けています:

OpenAI GPT シリーズ

Anthropic Claude

AI Safety 研究コミュニティ

AGI 研究コミュニティ

お問い合わせ

GitHub Issues: https://github.com/veritasfuji-japan/veritas_clean_test2/issues

Email: veritas.fuji@gmail.com

VERITAS OS v2.0 — Safe, Auditable, Proto-AGI Decision OS
Copyright © 2025 Takeshi Fujishita. All Rights Reserved.