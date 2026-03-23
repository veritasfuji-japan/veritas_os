
# VERITAS OS v2.0 — Proto-AGI Decision OS（日本語版）

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.17688094.svg)](https://doi.org/10.5281/zenodo.17688094)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-All%20Rights%20Reserved-red.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-Beta%20Governance%20Platform-blue.svg)]()
[![CI](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/main.yml/badge.svg)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/main.yml)
[![Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen.svg)](../docs/COVERAGE_REPORT.md)


**Version**: 2.0.0
**Release Date**: 2025-12-01  
**Author**: Takeshi Fujishita

このリポジトリには **VERITAS OS** が含まれます。  
VERITAS OS は、LLM（例: **OpenAI GPT-4.1-mini**）をラップして

> **安全で、一貫性があり、監査可能な「意思決定OS」(Decision OS)**

として動かすための **Proto-AGI フレームワーク** です。

- メンタルモデル: **「LLM = CPU」**, **「VERITAS OS = その上で動く意思決定 / エージェントOS」**

**README 一覧**

- **英語版 README**: [`README.md`](README.md)
- **日本語版 README**（このファイル）

> ※法的には、ライセンス条件は常にトップレベルの [`LICENSE`](LICENSE) と英語版 README の記載が優先されます。

> **正本 / 最新の運用判断**: リポジトリ全体の現行ポジショニング、責務境界、運用上の注意はトップレベルの [`README_JP.md`](../README_JP.md) を正本として参照してください。`veritas_os/README_JP.md` は主にバックエンド配下の機能説明用であり、ベータ前提の運用判断や導入可否の最終根拠として単独利用しないでください。

> **セキュリティ注意**: この README だけを根拠に production readiness を判断すると、運用ハードニングや degraded 時の対応要件を見落とすおそれがあります。導入判断の前に、必ずトップレベル README と `docs/operations/ENTERPRISE_SLO_SLI_RUNBOOK_JP.md` を併読してください。

---

## 📑 目次

1. [何ができるか？](#-1-何ができるか)
2. [AGIタスク向けコンテキストスキーマ](#-2-agitask向けコンテキストスキーマ)
3. [ディレクトリ構成](#-3-ディレクトリ構成)
4. [`core/` モジュールの役割](#-4-core-モジュールの役割)
5. [LLM クライアント](#-5-llm-クライアント)
6. [TrustLog とデータセット](#-6-trustlog-とデータセット)
7. [Doctor Dashboard](#-7-doctor-dashboard)
8. [クイックスタート](#-8-クイックスタート)
9. [開発ガイド](#-9-開発ガイド)
10. [トラブルシューティング](#-10-トラブルシューティング)
11. [ライセンス](#-11-ライセンス)
12. [コントリビューション / 謝辞 / 連絡先](#-12-コントリビューション--謝辞--連絡先)

---

## 🎯 1. 何ができるか？

### 1.1 `/v1/decide` — フル意思決定ループ

`POST /v1/decide` は、毎回 **構造化された JSON** を返し、  
その中に「なぜこの行動を選んだか？」の文脈がすべて入ります。

主なフィールド（簡略版）:

| フィールド名          | 説明                                                                                           |
|-----------------------|------------------------------------------------------------------------------------------------|
| `chosen`              | 選択されたアクション（説明・理由・不確実性・効用・リスクなど）                               |
| `alternatives[]`      | 候補だった他のアクション / オプション                                                          |
| `evidence[]`          | 使用されたエビデンス（MemoryOS / WorldModel / Web など）                                      |
| `critique[]`          | 自己批判・自己チェックの結果                                                                  |
| `debate[]`            | 擬似マルチエージェントによる議論結果（賛成 / 反対 / 第三者視点など）                          |
| `telos_score`         | ValueCore の価値関数に対する整合度スコア                                                      |
| `fuji`                | FUJI Gate による安全性 / 倫理判定（allow / modify / rejected）                               |
| `gate.decision_status`| 最終的な意思決定ステータス（Enum `DecisionStatus`）                                          |
| `trust_log`           | `sha256_prev` を含むハッシュチェーン化された TrustLog エントリ（監査用）                      |

パイプラインのイメージ:

```text
Options → Evidence → Critique → Debate → Planner → ValueCore → FUJI → TrustLog
(Local FastAPI server with OpenAPI 3.1 / Swagger UI, 起動後は外部依存なし)
````

同梱されているサブシステム:

* **MemoryOS** – 長期メモリ（エピソード / セマンティック）
* **WorldModel** – 世界状態 & 進行中プロジェクト
* **ValueCore** – 価値関数 / Value EMA
* **FUJI Gate** – 安全性・コンプライアンスゲート
* **TrustLog** – 暗号学的に検証可能な意思決定ログ
* **Doctor Dashboard** – 自己診断・ヘルスモニタリング

**ゴール:**

* LLM を **安全で再現可能かつ暗号学的に監査可能な Proto-AGI の「骨格」** として使うための
  研究・実験プラットフォーム。

代表的なユースケース:

* AGI / エージェントの **研究**
* **AI Safety 実験**
* 企業 / 規制産業における **監査パイプライン**

### 1.2 その他の API

すべての保護されたエンドポイントは `X-API-Key` 認証が必要です。

| Method | Path                  | 説明                              |
| ------ | --------------------- | ------------------------------- |
| GET    | `/health`             | サーバーヘルスチェック                     |
| POST   | `/v1/decide`          | フル意思決定ループ                       |
| POST   | `/v1/fuji/validate`   | 単一アクションの安全性 / 倫理判定              |
| POST   | `/v1/memory/put`      | 情報を MemoryOS に保存                |
| GET    | `/v1/memory/get`      | MemoryOS からの取得                  |
| GET    | `/v1/logs/trust/{id}` | TrustLog エントリ（ハッシュチェーン）を ID で取得 |

---

## 🧠 2. AGIタスク向けコンテキストスキーマ

メタ意思決定（AGI 的な自己改善・長期計画など）に使う場合、
VERITAS は以下のような `Context` オブジェクトを想定しています:

```yaml
Context:
  type: object
  required: [user_id, query]
  properties:
    user_id:      { type: string }
    session_id:   { type: string }
    query:        { type: string, description: "User request / problem statement" }
    goals:        { type: array, items: { type: string } }
    constraints:  { type: array, items: { type: string } }
    time_horizon: { type: string, enum: ["short", "mid", "long"] }
    preferences:  { type: object }
    tools_allowed:
      type: array
      items: { type: string }
    telos_weights:
      type: object
      properties:
        W_Transcendence: { type: number }
        W_Struggle:      { type: number }
    affect_hint:
      type: string
      enum: ["calm", "focused", "empathetic", "concise"]
```

`/v1/decide` に渡せる典型的なクエリ:

* 「自分の AGI 研究プランの **次の最適ステップ** は何か？」
* 「**自己改善ループ** をどう設計すればよいか？」
* 「自分で設定した安全境界の中で、どこまで実験を攻めてよいか？」

OS は、

* **マルチステップの計画** と
* **今すぐ実行すべき次アクション**

の両方を決めます。

---

## 🏗 3. ディレクトリ構成

### 3.1 ルート構成

```text
veritas_os/
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
│   ├── memory/
│   ├── tools/
│   ├── templates/
│   ├── scripts/
│   ├── README.md
│   ├── README_ENGLISH.md       # (任意) 追加の英語ドキュメント
│   └── requirements.txt
├── reports/
├── backups/
├── datasets/
├── veritas.sh                  # ローカル利用用のヘルパースクリプト
├── .gitignore
└── LICENSE
```

`__pycache__` などの自動生成ディレクトリは省略。

### 3.2 `veritas_os/core/` 概要

```text
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
├── time_utils.py
├── value_core.py
├── world.py
├── world_model.py.old          # 旧 WorldModel プロトタイプ
└── models/
    ├── __init__.py
    ├── memory_model.py
    ├── memory_model.py.old     # 旧バージョン
    └── vector_index.json       # MemoryOS 用ベクトルインデックス（pickleはruntimeで無効）
```

---

## 🧩 4. `core/` モジュールの役割

### 4.1 コア OS レイヤー

#### `kernel.py`

VERITAS のグローバル・オーケストレーター。

* `/v1/decide` のエントリーポイント
* フルパイプラインを実行:

```text
Planner → Evidence → Critique → Debate → FUJI → World/Memory update
```

* 最終的な `DecideResult` JSON を組み立てる

#### `pipeline.py`

意思決定パイプラインのステージと制御フローを定義。

* どの OS モジュールをどの順番で呼ぶか
* どのステージでどのメトリクスを取るか

#### `planner.py`（PlannerOS）

`query / goals / constraints` を **マルチステップのプラン** に変換。

* すぐ実行する「次の一手」
* もう少し長期の `steps[]`（プラン配列）

を両方生成。

#### `reason.py`（ReasonOS）

内部推論 / Chain-of-Thought を扱う。

* Evidence / Critique を統合して一貫した推論を生成
* `DecideResponse` の「理由・根拠」のバックボーンになる

#### `strategy.py`

高レベルの戦略コントローラ（実験的）。

* 探索 vs 活用
* 今どの程度リスクを取るか
* 大域的な意思決定パターンの切り替え

#### `world.py` / `world_model.py.old`（WorldOS / WorldModel）

世界状態のスナップショットを管理:

* 進行中プロジェクト・タスク
* 累積リスク / 保留中タスク

これらは JSON (`world_state`) として保存され、
将来の `/v1/decide` 呼び出しに引き継がれます。

---

### 4.2 安全性 / 価値 / 自己改善レイヤー

#### `fuji.py`（FUJI Gate）

最終的な安全性 / 倫理 / コンプライアンスゲート。

出力:

* `risk_score`
* `violations[]`（どのポリシーに抵触したか）
* `status: allow | modify | rejected`

`POST /v1/fuji/validate` として単体でも利用可能。

#### `decision_status.py`

OS 全体で共通利用される標準化された意思決定ステータス Enum:

```python
class DecisionStatus(str, Enum):
    ALLOW    = "allow"
    MODIFY   = "modify"
    REJECTED = "rejected"
```

後方互換性のための文字列定数も提供。

#### `value_core.py`（ValueCore）

VERITAS の **Value EMA（指数移動平均）** を管理。

* 各意思決定に対し、単一の「良さ」スコアを記録
* `telos_score` の計算や、将来的なポリシー改善に利用

#### `reflection.py`（ReflectionOS）

過去の意思決定・Doctor Report をもとに自己反省を行う。

* どのような状況で失敗しがちか
* どの種類の質問・パターンが弱点か
* そのフィードバックを Planner / ValueCore に渡す

#### `adapt.py` / `rsi.py`

将来的な自己適応 / RSI（再帰的自己改善）ロジックの入口。

* 実験実装やノートを含む
* どの情報を次の学習サイクルに回すか決定

---

### 4.3 Evidence / Critique / Debate

#### `evidence.py`（EvidenceOS）

以下から候補エビデンスを収集:

* MemoryOS
* WorldModel
* （必要に応じて）外部ツール / Web

その後、関連性・信頼性でスコアリングし `evidence[]` を構成。

#### `critique.py`（CritiqueOS）

LLM 駆動の自己批判・自己検証。

* 隠れているリスクの顕在化
* 誤った前提の炙り出し
* FUJI / DebateOS へのフィードバックとして利用

#### `debate.py`（DebateOS）

擬似的なマルチエージェント議論を実施。

* 賛成 / 反対 / 第三者的な視点
* 議論結果を `debate[]` として構造化
* 最終的な `chosen` アクションに影響を与える

---

### 4.4 MemoryOS

#### `memory.py`（MemoryOS フロントエンド）

`scripts/logs/memory.json`（パスは設定可能）を中心に長期メモリを管理。

* エピソード / 意思決定 / メタデータの保存
* 過去の意思決定に対する類似検索
* 内部的には `core/models/memory_model.py` と `vector_index.json` を使用
* 旧 `.pkl` アーティファクトは RCE リスク対策で runtime でブロック

高レベルユーティリティ例:

* ベクトルインデックス + KVS フォールバックによる検索
* エピソード → セマンティックへの蒸留（長期「要約メモ」）
* 既存メモリからのベクトルインデックス再構築

#### `models/memory_model.py` / `models/vector_index.json`

MemoryOS 用の埋め込みモデルとベクトルインデックスを実装。

* ベクトル化と近傍検索を担当
* 基本的なセマンティックメモリ機能を提供

---

### 4.5 LLM クライアント & ロギング

#### `llm_client.py`

**すべての LLM 呼び出しの単一エントリーポイント**。

v2.0 現時点の前提:

* プロバイダ: **OpenAI**
* モデル: `gpt-4.1-mini`（互換モデルを想定）
* API: Chat Completions

環境変数による制御:

```bash
export OPENAI_API_KEY="sk-..."
export LLM_PROVIDER="openai"      # 現状は実質 'openai'
export LLM_MODEL="gpt-4.1-mini"
export LLM_TIMEOUT="60"
export LLM_MAX_RETRIES="3"
```

`llm_client.chat(...)` は

* Planner / Evidence / Critique / Debate / FUJI

といったモジュールからのみ呼ばれるため、
**このファイルだけ差し替えればモデル・プロバイダの切り替えが可能**です。

Claude / Gemini / ローカル LLM などのマルチプロバイダ対応は一部スタブがあり、
今後拡張予定です。

#### `logging.py`

OS 全体で共通利用されるロギングユーティリティ。

論文で説明している **TrustLog のハッシュチェーン** を実装:

```text
h_t = SHA256(h_{t-1} || r_t)
```

* `sha256_prev` と `sha256` は自動で埋め込まれる
* JSONL 形式でログを追記
* 意思決定履歴の暗号学的検証をサポート

---

### 4.6 ログ / データセット / パス

#### `veritas_os/logging/dataset_writer.py`

意思決定ログを、将来の学習用データセットに変換。

主要関数:

* `build_dataset_record(req, res, meta, eval_meta)`
  → 各意思決定から正規化されたレコードを生成
* `append_dataset_record(record, path=DATASET_JSONL)`
  → `datasets/dataset.jsonl` に追記
* `get_dataset_stats()`
  → ステータス分布、メモリ使用率、平均スコア、期間などを集計
* `search_dataset(query, status, memory_used, limit)`
  → `dataset.jsonl` に対する簡易検索 API

レコードには `DecisionStatus` に基づくラベルが含まれます:

* `labels.status = "allow" | "modify" | "rejected"`

さらに `memory_used`, `telos_score`, `utility`, `risk` 等を含むため、

* 「安全かつ高品質な意思決定データセット」

を簡単に抽出できます。

用途:

* ファインチューニング
* オフライン評価
* 安全性分析

#### `veritas_os/logging/paths.py`

以下のパスを一元管理:

* ログ
* レポート
* バックアップ
* データセット

`VERITAS_DATA_DIR` などの環境変数と連携。

---

### 4.7 Affect / Curriculum / Experiment / Tools

#### `affect.py`

**応答トーン / 雰囲気** を制御。

* モード例: `calm`, `focused`, `empathetic`, `concise`
* `Context.affect_hint` によって指定
* LLM に渡すプロンプトスタイルに影響

#### `curriculum.py` / `experiment.py`

自己学習・AGI 実験ユーティリティ。

* `docs/bench_summary.md` などからカリキュラムを生成
* 意思決定パイプラインに対する実験 / A/B テスト

#### `sanitize.py`

テキストのサニタイズ層。

* PII（個人情報）のマスク
* 制御文字 / 変な文字の除去
* 危険性のあるコンテンツの一部フィルタ

FUJI Gate とは別レイヤーで、
あくまで **テキストクリーニング** に特化。

#### `tools.py` / `identity.py`

* `tools.py`: ID 生成・日時フォーマットなどの一般ユーティリティ
* `identity.py`: システムの自己紹介・メタデータ

  * System ID
  * Version
  * Doctor Dashboard やログで表示される自己紹介文など

---

## 🧠 5. LLM クライアント

まとめ:

* **プロバイダ**: OpenAI
* **モデル**: `gpt-4.1-mini`（互換モデル）
* **API**: Chat Completions

例: 環境変数の設定

```bash
export OPENAI_API_KEY="sk-..."
export LLM_PROVIDER="openai"
export LLM_MODEL="gpt-4.1-mini"
export LLM_TIMEOUT="60"
export LLM_MAX_RETRIES="3"
```

内部モジュールはすべて `llm_client` 経由で LLM を呼び出すため、

* モデルの切り替え
* プロバイダの切り替え（将来的な対応）
* タイムアウト / リトライ / ログ設定

を **1つの場所で集中管理** できます。

---

## 🔐 6. TrustLog とデータセット

### 6.1 TrustLog（ハッシュチェーン監査ログ）

実装: `veritas_os/core/logging.py`
出力例: `scripts/logs/trust_log*.jsonl`
フォーマット: JSON Lines（1行 = 1エントリ）

各エントリには:

* `sha256_prev`: 直前エントリの `sha256`
* `sha256`: `SHA256(sha256_prev || entry_without_hashes)`

が含まれます。

ログをマージして再ハッシュしても、一貫性を保てます:

```bash
cd veritas_os
python -m veritas_os.api.merge_trust_logs \
  --out scripts/logs/trust_log_merged.jsonl
```

* デフォルト: 既存ログを自動検出し、`request_id` / timestamp で重複排除
* `--no-rehash` を付けると再ハッシュを無効化（基本的には ON 推奨）

### 6.2 データセット出力

意思決定結果を `dataset_writer.py` から学習用データセットに変換:

```python
from veritas_os.logging.dataset_writer import (
    build_dataset_record,
    append_dataset_record,
    get_dataset_stats,
    search_dataset,
)
```

出力ファイル: `datasets/dataset.jsonl`

含まれる情報:

* `labels.status = allow / modify / rejected`
* `memory_used`, `telos_score`, `utility`, `risk` など

これにより、

* 「安全で質の高い意思決定データ」

を抽出して:

* ファインチューニング
* オフライン評価
* 安全性分析

に利用できます。

---

## 📊 7. Doctor Dashboard

**Doctor Dashboard** は、VERITAS OS の「健康状態」を可視化するダッシュボードです。

### 7.1 レポート生成

```bash
cd veritas_os/scripts
source ../.venv/bin/activate
python generate_report.py
```

生成物:

* `scripts/logs/doctor_report.json`
* `scripts/logs/doctor_dashboard.html`

典型的な内容:

* `/v1/decide` 呼び出し回数の推移
* FUJI 判定分布（allow / modify / rejected）
* MemoryOS ヒット数
* Value EMA の推移
* unsafe / modify 判定の頻度
* レイテンシ分布

`doctor_dashboard.html` をブラウザで開くと可視化できます。

### 7.2 認証付きダッシュボードサーバ（任意）

`dashboard_server.py` を使うと、HTTP Basic 認証付きでダッシュボードを配信できます:

```bash
export DASHBOARD_USERNAME="veritas"
export DASHBOARD_PASSWORD="your_secure_password"
export VERITAS_LOG_DIR="/path/to/veritas_os/scripts/logs"  # 任意

python veritas_os/api/dashboard_server.py
# または
python veritas_os/scripts/dashboard_server.py
```

エンドポイント:

* UI: `http://localhost:8000/` または `/dashboard`
* ステータスAPI: `GET /api/status`
  → `drive_sync_status.json` を JSON で返す
* ヘルスチェック（認証不要）: `GET /health`

---

## 🚀 8. クイックスタート

### 8.1 インストール

```bash
# 1. Clone
git clone https://github.com/veritasfuji-japan/veritas_os.git
cd veritas_os

# 2. Virtualenv
python3.11 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. 依存パッケージのインストール
pip install -r veritas_os/requirements.txt

# 4. 必須環境変数
export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
export VERITAS_API_KEY="your-secret-api-key"  # X-API-Key 認証に使用
```

### 8.2 API サーバ起動

```bash
python3 -m uvicorn veritas_os.api.server:app --reload --port 8000
```

### 8.3 Swagger UI からの確認

1. `http://127.0.0.1:8000/docs` を開く
2. 右上の **“Authorize”** をクリック
3. `X-API-Key` に `VERITAS_API_KEY` の値を入力
4. `POST /v1/decide` を選択
5. 以下のようなサンプルペイロードで実行:

```json
{
  "query": "Should I check tomorrow's weather before going out?",
  "context": {
    "user_id": "test_user",
    "goals": ["health", "efficiency"],
    "constraints": ["time limit"]
  }
}
```

### 8.4 `curl` からの確認

```bash
curl -X POST "http://127.0.0.1:8000/v1/decide" \
  -H "X-API-Key: your-secret-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Should I check tomorrow'\''s weather before going out?",
    "context": {
      "user_id": "test_user",
      "goals": ["health", "efficiency"]
    }
  }'
```

---

## 🛠 9. 開発ガイド

### 9.1 開発環境

`requirements-dev.txt` がある場合:

```bash
# 開発用依存パッケージ
pip install -r requirements-dev.txt

# pre-commit フック（設定されていれば）
pre-commit install
```

### 9.2 テスト

```bash
# ユニットテスト
pytest tests/

# カバレッジ
pytest --cov=veritas_os tests/
```

（執筆時点では、コアロジックの大部分を内部テストスイートがカバーしています。）

### 9.3 コード品質

```bash
# Lint
flake8 veritas_os/
pylint veritas_os/

# フォーマット
black veritas_os/
isort veritas_os/

# 型チェック
mypy veritas_os/
```

---

## ❓ 10. トラブルシューティング

### `OPENAI_API_KEY` が見つからない

環境変数を設定:

```bash
echo $OPENAI_API_KEY
export OPENAI_API_KEY="sk-..."
```

### ポート 8000 が使用中

ポートを変更:

```bash
uvicorn veritas_os.api.server:app --reload --port 8001
```

### メモリが保存されない

`VERITAS_DATA_DIR` とファイル権限を確認:

```bash
export VERITAS_DATA_DIR="/path/to/veritas_data"
mkdir -p "$VERITAS_DATA_DIR"
```

### TrustLog 検証に失敗する

検証用スクリプトがある場合:

```bash
cd veritas_os/scripts
python verify_trust_log.py          # 実装されていれば
# または
python ../api/merge_trust_logs.py --out logs/trust_log_merged.jsonl
```

---

## 📜 11. ライセンス

このリポジトリは **ミックスライセンス** モデルを採用しています。

* **コアエンジン & 大部分のコード**
  （例: `veritas_os/`, `scripts/`, `tools/`, `config/`, `tests/` 等）
  → **All Rights Reserved（全権留保）**
  → 詳細はトップレベルの [`LICENSE`](LICENSE) を参照してください。

* 一部サブディレクトリ（例: `docs/`, `examples/` など）は、
  そのディレクトリ内に **独自の LICENSE ファイル** を持つ場合があります。
  その場合、そのディレクトリ以下については（例: Apache License 2.0 などの）
  **サブディレクトリ専用ライセンス** が適用されます。

**デフォルトルール:**

> あるファイル / ディレクトリに固有の LICENSE が存在しない場合、
> そのファイル / ディレクトリは **プロプライエタリな All Rights Reserved** とみなしてください。

```text
Copyright (c) 2025
Takeshi Fujishita
All Rights Reserved.
```

学術利用の際は、以下の DOI を引用してください:

```bibtex
@software{veritas_os_2025,
  author = {Fujishita, Takeshi},
  title  = {VERITAS OS: Proto-AGI Decision OS},
  year   = {2025},
  doi    = {10.5281/zenodo.17688094},
  url    = {https://github.com/veritasfuji-japan/veritas_os}
}
```

商用利用その他のライセンスに関するお問い合わせは、
下記「連絡先」までご連絡ください。

---

## 🤝 12. コントリビューション / 謝辞 / 連絡先

### コントリビューション

Pull Request は歓迎しますが、
コア部分が **All Rights Reserved** であるため、
必要に応じてコントリビューター同意が必要になる場合があります。

一般的なフロー:

```bash
# 1. リポジトリを Fork
# 2. フィーチャーブランチを作成
git checkout -b feature/AmazingFeature

# 3. 変更をコミット
git commit -m "Add some AmazingFeature"

# 4. ブランチを Push
git push origin feature/AmazingFeature

# 5. GitHub 上で Pull Request を作成
```

`CONTRIBUTING.md` が存在する場合は、そちらも参照してください。

### 謝辞

このプロジェクトは以下から影響を受けています:

* OpenAI GPT シリーズ
* Anthropic Claude
* AI Safety 研究コミュニティ
* AGI 研究コミュニティ

### 連絡先

* GitHub Issues: [https://github.com/veritasfuji-japan/veritas_os/issues](https://github.com/veritasfuji-japan/veritas_os/issues)
* Email: `veritas.fuji@gmail.com`

---

**VERITAS OS v2.0 — 安全で、監査可能な Proto-AGI Decision OS**

© 2025 Takeshi Fujishita. **All Rights Reserved.**
