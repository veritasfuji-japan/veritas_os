
# VERITAS OS v2.0 — LLMエージェントのための監査可能な意思決定OS（Proto-AGI Skeleton）

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.17838349.svg)](https://doi.org/10.5281/zenodo.17838349)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-All%20Rights%20Reserved-red.svg)](LICENSE)
[![CI](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/main.yml/badge.svg)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/main.yml)
[![Docker Publish](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/publish-ghcr.yml/badge.svg)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/publish-ghcr.yml)
[![Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen.svg)](docs/COVERAGE_REPORT.md)
[![GHCR](https://img.shields.io/badge/GHCR-ghcr.io%2Fveritasfuji--japan%2Fveritas__os-2496ED?logo=docker&logoColor=white)](https://ghcr.io/veritasfuji-japan/veritas_os)
[![README EN](https://img.shields.io/badge/README-English-1d4ed8.svg)](README.md)

**Version**: 2.0.0  
**Planned Release**: 2025-12-01  
**Author**: Takeshi Fujishita

VERITAS OS は、LLM（例：OpenAI GPT-4.1-mini）を  
**「安全ゲート付き・再現可能・監査可能」**な意思決定エンジンとして運用するための **Decision OS** です。

> メンタルモデル：**LLM = CPU** / **VERITAS OS = その上に載る意思決定OS**

---

## クイックリンク

- **GitHub**: https://github.com/veritasfuji-japan/veritas_os
- **Zenodo論文（英語）**: https://doi.org/10.5281/zenodo.17838349
- **Zenodo論文（日本語）**: https://doi.org/10.5281/zenodo.17838456
- **English README**: `README.md`
- **レビュー文書マップ**: `docs/notes/CODE_REVIEW_DOCUMENT_MAP.md`

## 目次

- [なぜVERITASか（何が違う？）](#なぜveritasか何が違う)
- [できること](#できること)
- [API一覧（概要）](#api一覧概要)
- [Quickstart（最短起動）](#quickstart最短起動)
- [セキュリティ注意（重要）](#セキュリティ注意重要)
- [Docker（GHCR）](#dockerghcr)
- [アーキテクチャ（高レベル）](#アーキテクチャ高レベル)
- [TrustLog（ハッシュチェーン監査ログ）](#trustlogハッシュチェーン監査ログ)
- [テスト](#テスト)
- [近いロードマップ（短期）](#近いロードマップ短期)
- [ライセンス](#ライセンス)

---

## なぜVERITASか（何が違う？）

多くの「エージェントFW」は自律性・ツール実行を中心に設計されています。  
VERITAS は **ガバナンス（統制）** を中心に置きます。

- **FUJI Gate** による安全・倫理・コンプライアンスの最終判定（allow/modify/rejected）
- ステージ固定の **決定パイプライン**（毎回同じ順序で実行 → 再現性が高い）
- **TrustLog（ハッシュチェーン）**による監査証跡（改ざん検知可能）
- **MemoryOS + WorldModel** を「入力の一級市民」として扱う（記憶と世界状態が意思決定に入る）
- **Doctor（診断/可視化）**で運用メトリクスを確認できる

**想定ユーザー**
- エージェント研究 / AI Safety 研究者
- LLMを規制・高リスク領域で運用したいチーム（金融・医療・法務・公共など）
- ガバナンス/コンプライアンス（ポリシー駆動のLLM運用基盤を作りたい）

---

## できること

### `/v1/decide` — フル意思決定ループ（構造化JSON）

`POST /v1/decide` は、意思決定の全過程を **構造化されたJSON** として返します。

主要フィールド（簡易）：

| フィールド | 意味 |
|---|---|
| `chosen` | 選択したアクション + 根拠、確信度、不確実性、効用、リスク |
| `alternatives[]` | 他の候補アクション |
| `evidence[]` | 参照した根拠（MemoryOS / WorldModel / 任意ツールなど） |
| `critique` | 自己批判・弱点・前提の穴（dict） |
| `debate[]` | 擬似マルチエージェント討論（賛成/反対/第三者） |
| `telos_score` | ValueCoreに対する整合スコア |
| `fuji` | FUJI Gate判定（allow / modify / rejected） |
| `gate.decision_status` | 正規化された最終ステータス（`DecisionStatus`） |
| `trust_log` | ハッシュチェーンされたTrustLog（`sha256_prev` など） |

意思決定パイプライン（メンタルモデル）：

```text
Options → Evidence → Critique → Debate → Planner → ValueCore → FUJI → TrustLog
````

> **注意（kernel 経由 vs pipeline 経由）**  
> `kernel.py` 経由の `/v1/decide` では `telos_score` は `telos_weights` から簡易算出され、  
> `pipeline.py` の **ValueCore 評価**（`value_core.evaluate`）や **TrustLog への監査書き込み** は
> **実行されません**。ValueCore/TrustLog を含む完全な評価・監査が必要な場合は
> **pipeline 経由**の実行を前提にしてください。

同梱サブシステム：

* **MemoryOS** — エピソード/セマンティック記憶、検索
* **WorldModel** — 世界状態、プロジェクト進行のスナップショット
* **ValueCore** — 価値関数 & Value EMA
* **FUJI Gate** — 安全/倫理/コンプライアンスのゲート
* **TrustLog** — 監査ログ（JSONL, ハッシュチェーン）
* **Doctor** — 診断レポート/可視化

---

## API一覧（概要）

保護されたエンドポイントは `X-API-Key` が必要です。

| Method | Path                  | 説明              |
| ------ | --------------------- | --------------- |
| GET    | `/health`             | ヘルスチェック         |
| POST   | `/v1/decide`          | フル意思決定          |
| POST   | `/v1/fuji/validate`   | 単一アクションをFUJIで評価 |
| POST   | `/v1/memory/put`      | 記憶の保存           |
| GET    | `/v1/memory/get`      | 記憶の取得           |
| GET    | `/v1/logs/trust/{id}` | TrustLogエントリ取得  |

---

## Quickstart（最短起動）

> Docker での起動手順は [Docker（GHCR）](#dockerghcr) を参照してください。

### 1) インストール

```bash
git clone https://github.com/veritasfuji-japan/veritas_os.git
cd veritas_os

python3.11 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

### 2) 環境変数

```bash
export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
export VERITAS_API_KEY="your-secret-api-key"
export VERITAS_API_SECRET="your-long-random-secret"
export LLM_PROVIDER="openai"
export LLM_MODEL="gpt-4.1-mini"
export VERITAS_ENCRYPTED_LOG_ROOT="/path/to/encrypted/logs"
export VERITAS_REQUIRE_ENCRYPTED_LOG_DIR="1"
export VERITAS_MAX_REQUEST_BODY_SIZE="10485760"
```

### 3) サーバ起動

```bash
python -m uvicorn veritas_os.api.server:app --reload --port 8000
```

### 4) Swagger UIで試す

* `http://127.0.0.1:8000/docs` を開く
* `Authorize` で `X-API-Key: $VERITAS_API_KEY` を入力
* `POST /v1/decide` を実行

サンプル：

```json
{
  "query": "明日の外出前に天気を確認すべき？",
  "context": {
    "user_id": "test_user",
    "goals": ["健康", "効率"],
    "constraints": ["時間制限"],
    "affect_hint": "focused"
  }
}
```

---

## セキュリティ注意（重要）

- **プレースホルダや短すぎるシークレットは禁止**:
  `VERITAS_API_SECRET` は長いランダム値（推奨32文字以上）を設定してください。
  プレースホルダや短い値はHMAC保護を無効化・弱体化する恐れがあります。
- **CORSの安全性**: `allow_credentials` を有効にした状態で
  ワイルドカード（`*`）を使わず、信頼できるオリジンのみを許可してください。
- **Legacy pickle移行は危険**:
  MemoryOSで旧pickle移行を有効にする場合は、移行完了後に必ず無効化してください。

---

## アーキテクチャ（高レベル）

### コアの実行経路

* `veritas_os/core/kernel.py` — `/v1/decide` の統括
* `veritas_os/core/pipeline.py` — ステージ順序とメトリクス
* `veritas_os/core/llm_client.py` — **LLM呼び出しの単一窓口**

### 安全/ガバナンス

* `veritas_os/core/fuji.py` — FUJI Gate（allow/modify/rejected）
* `veritas_os/core/value_core.py` — 価値関数 & Value EMA
* `veritas_os/logging/*` — TrustLog（ハッシュチェーン監査ログ）

### 記憶/世界状態

* `veritas_os/core/memory.py` — MemoryOS
* `veritas_os/core/world.py` — World state スナップショット

---

## TrustLog（ハッシュチェーン監査ログ）

TrustLog は JSONL（1行1レコード）の追記型ログです。
各レコードは前のレコードのハッシュを参照します。

```text
h_t = SHA256(h_{t-1} || r_t)
```

これにより、決定履歴は **改ざん検知可能**な監査証跡として扱えます。

### ログ保存パス（`scripts/logs` vs `~/.veritas`）

- **`scripts/logs`（既定）**: `veritas_os.logging.paths` 経由で保存される TrustLog/ダッシュボード用ログの既定パスです。  
  `VERITAS_DATA_DIR` または `VERITAS_LOG_ROOT` を設定している場合は、そのパスが優先されます。
- **`~/.veritas`（既定）**: ValueCore の補助ログ（`~/.veritas/trust_log.jsonl` など）や、
  Kernel 直呼び時の Doctor ログ（`~/.veritas/logs/doctor.log` など）が保存されます。

**使い分け/注意点**
- `/v1/decide` を **pipeline 経由**で実行している場合は主に `scripts/logs` に出力されます。
- **Kernel 直呼び**や ValueCore 単体のユーティリティは `~/.veritas` を参照するため、
  監査・解析の際は **両方のパスにログが分散し得る**ことに注意してください。
- ログ保存先を統一したい場合は `VERITAS_DATA_DIR`/`VERITAS_LOG_ROOT` の設定を優先してください。
  いずれのパスも **機微情報が含まれる可能性**があるため、アクセス権限と保管ポリシーを必ず確認してください。

### ログ保管ポリシー（暗号化 + 権限制御の推奨）

VERITAS のログは機微情報を含む可能性があるため、**暗号化ボリューム上に保管する運用**を推奨します。
以下の環境変数でログ出力先の強制と権限制御を行えます。

- `VERITAS_ENCRYPTED_LOG_ROOT`: 暗号化済みボリューム上のログ保存先
- `VERITAS_REQUIRE_ENCRYPTED_LOG_DIR=1`: ログ出力先を暗号化パスに強制

運用上の推奨:
- 暗号化ボリューム（LUKS, BitLocker, EBS暗号化等）へマウント
- ログディレクトリは **chmod 700**（所有者のみアクセス）
- バックアップ先も暗号化 & アクセス制御を必須にする

---

## テスト

再現性重視（推奨）:

```bash
make test
make test-cov
```

これらのターゲットは `uv` と `PYTHON_VERSION=3.12.12` を利用し、
未導入時は Python 本体を自動取得して実行します。

オプション:

```bash
make test TEST_ARGS="-q veritas_os/tests/test_time_utils.py"
make test PYTHON_VERSION=3.11
```

スモークチェック（最短）:

```bash
make test TEST_ARGS="-q veritas_os/tests/test_api_constants.py"
```

> 補足：CI は GitHub Actions で利用可能です。Coverage バッジは追加予定です。

---

## Docker（GHCR）

最新イメージを取得:

```bash
docker pull ghcr.io/veritasfuji-japan/veritas_os:latest
```

API サーバ起動:

```bash
docker run --rm -p 8000:8000 \
  -e OPENAI_API_KEY="YOUR_OPENAI_API_KEY" \
  -e VERITAS_API_KEY="your-secret-api-key" \
  -e LLM_PROVIDER="openai" \
  -e LLM_MODEL="gpt-4.1-mini" \
  ghcr.io/veritasfuji-japan/veritas_os:latest
```

FastAPI エントリポイントが `veritas_os.api.server:app` と異なる場合は、
Dockerfile の `CMD` を環境に合わせて更新してください。

---

## セキュリティ注意（重要）

- **APIキー**: 可能な限りシェル履歴に残る `export` を避け、`.env`（gitignore）
  や Secret Manager を使って実行時に注入してください。定期的なローテーションと
  最小権限の付与を推奨します。
- **TrustLogのデータ**: TrustLog は JSONL の追記ログです。ペイロードに個人情報
  や機密情報が含まれる可能性がある場合、アクセス制御、保持期間、必要に応じて
  保存時暗号化を実施してください。

---

## 運用・セキュリティ上の注意

- **TrustLog / Memory の保存前に PII マスクを強制することを推奨**します。保存前に `redact()`（PIIマスク）を通すことで、ログ/記憶に機微情報が残るリスクを低減できます。
- **暗号化 at rest（オプション）**: TrustLog / Memory は平文保存のため、要件に応じて暗号化やKMS連携を検討してください。
- **CORS と API Key の未設定は危険**です。`VERITAS_CORS_ALLOW_ORIGINS` と `VERITAS_API_KEY` を必ず設定してください。
- **運用ログは Git 管理から除外**します。`veritas_os/memory/*.jsonl` などのランタイムログは `.gitignore` 対象とし、匿名化済みサンプルは `veritas_os/sample_data/memory/` に配置します。

### 起動時ハードエラー条件（L1運用ポリシー）

本番環境（`ENV=prod` 相当）では、以下のセキュリティ要求を **警告止まりにせず起動時ハードエラー**として扱うことを推奨します。

| 項目 | 最低要件（起動を止める条件） | 理由 |
|---|---|---|
| `VERITAS_API_SECRET` 長 | 32文字未満、空、既定プレースホルダ値を検出したら起動失敗 | 短い/既知シークレットは署名なりすまし耐性を大幅に低下させるため |
| Legacy pickle移行 | `VERITAS_MEMORY_ALLOW_PICKLE_MIGRATION=1` での恒常運用を禁止（移行専用ジョブ以外は起動失敗） | pickle由来のデシリアライズ面は攻撃面積が大きく、平常運用へ持ち込むべきではないため |
| CORS | `allow_credentials=True` かつ `VERITAS_CORS_ALLOW_ORIGINS` 未設定/実質空/`*` 混入時は起動失敗 | 認証付きリクエストで広すぎるオリジン許可はデータ漏えいリスクを増大させるため |

#### 運用ルール（明文化）

1. **開発環境**: 警告ログで許容。ただしCIでは上記3項目を fail-fast で検証する。
2. **ステージング環境**: 本番同等（ハードエラー）を必須化する。
3. **本番環境**: 例外申請のない限り、上記3項目に違反した設定での起動を禁止する。

> ⚠️ セキュリティ警告: 起動時ハードエラー化を行わない場合、
> 設定ミスが「気づきにくい警告」のまま残留し、
> 認証・データ保護境界の弱体化が長期化するリスクがあります。

---

## 近いロードマップ（短期）

* CI（GitHub Actions）：pytest + coverage + レポート生成
* セキュリティ強化：入力検証、ログ/秘密情報の衛生
* Policy-as-Code：**規程 → ValueCore/FUJIルール → テスト自動生成**（コンパイラ層）

---

## ライセンス

**All Rights Reserved（プロプライエタリ）**。本リポジトリは
オープンソースではありません。使用・改変・配布は、サブディレクトリに
明示された LICENSE がある場合を除き制限されています。
詳細は [`LICENSE`](LICENSE) を参照してください。

学術用途では Zenodo DOI を引用してください。

---

## 引用（BibTeX）

```bibtex
@software{veritas_os_2025,
  author = {Fujishita, Takeshi},
  title  = {VERITAS OS: Auditable Decision OS for LLM Agents},
  year   = {2025},
  doi    = {10.5281/zenodo.17838349},
  url    = {https://github.com/veritasfuji-japan/veritas_os}
}
```

---

## 連絡先

* Issues: [https://github.com/veritasfuji-japan/veritas_os/issues](https://github.com/veritasfuji-japan/veritas_os/issues)
* Email: [veritas.fuji@gmail.com](mailto:veritas.fuji@gmail.com)
