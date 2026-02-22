# VERITAS OS v2.0 — LLMエージェント向け監査可能な意思決定OS（Proto-AGI Skeleton）

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.17838349.svg)](https://doi.org/10.5281/zenodo.17838349)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Multi--license%20(Core%20Proprietary%20%2B%20MIT)-purple.svg)](LICENSE)
[![CI](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/main.yml/badge.svg)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/main.yml)
[![Docker Publish](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/publish-ghcr.yml/badge.svg)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/publish-ghcr.yml)
[![Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen.svg)](docs/COVERAGE_REPORT.md) <!-- docs/COVERAGE_REPORT.md のスナップショット値。CIゲートは .github/workflows/main.yml で管理 -->
[![GHCR](https://img.shields.io/badge/GHCR-ghcr.io%2Fveritasfuji--japan%2Fveritas__os-2496ED?logo=docker&logoColor=white)](https://ghcr.io/veritasfuji-japan/veritas_os)
[![README EN](https://img.shields.io/badge/README-English-1d4ed8.svg)](README.md)

**Version**: 2.0.0-alpha  
**Release Status**: 開発中  
**Author**: Takeshi Fujishita

VERITAS OS は、LLM（例: OpenAI GPT-4.1-mini）を **決定論的・安全ゲート付き・ハッシュチェーン監査可能** な意思決定パイプラインで包みます。

> メンタルモデル: **LLM = CPU**、**VERITAS OS = その上に載る Decision / Agent OS**

---

## クイックリンク

- **GitHub**: https://github.com/veritasfuji-japan/veritas_os
- **Zenodo論文（英語）**: https://doi.org/10.5281/zenodo.17838349
- **Zenodo論文（日本語）**: https://doi.org/10.5281/zenodo.17838456
- **日本語README**: `README_JP.md`
- **レビュー文書マップ**: `docs/notes/CODE_REVIEW_DOCUMENT_MAP.md`

## 目次

- [なぜVERITASか](#なぜveritasか)
- [できること](#できること)
- [API概要](#api概要)
- [Quickstart](#quickstart)
- [セキュリティ注意（重要）](#セキュリティ注意重要)
- [Docker（GHCR）](#dockerghcr)
- [アーキテクチャ（高レベル）](#アーキテクチャ高レベル)
- [TrustLog（ハッシュチェーン監査ログ）](#trustlogハッシュチェーン監査ログ)
- [テスト](#テスト)
- [ロードマップ（短期）](#ロードマップ短期)
- [ライセンス](#ライセンス)

---

## なぜVERITASか

多くの「エージェントフレームワーク」は自律性やツール実行を最適化します。  
VERITAS は **ガバナンス** を最適化します。

- 最終ゲート（**FUJI Gate**）で安全性とコンプライアンスを強制
- 再現可能な意思決定パイプライン（固定ステージ、構造化出力）
- **ハッシュチェーンTrustLog** による監査可能性（改ざん検知）
- **MemoryOS + WorldModel** を一次入力として扱う
- **Doctorダッシュボード** による運用可視性（健全性・リスク分布）

**想定ユーザー**
- AI safety / エージェント研究者
- 規制領域・高リスク領域でLLMを運用するチーム
- ポリシー駆動LLM基盤を作るガバナンス/コンプライアンス担当

---

## できること

### `/v1/decide` — フル意思決定ループ（構造化JSON）

`POST /v1/decide` は構造化された意思決定レコードを返します。

主要フィールド（簡易）:

| フィールド | 意味 |
|---|---|
| `chosen` | 選択アクション + 根拠、不確実性、効用、リスク |
| `alternatives[]` | 他の候補アクション |
| `evidence[]` | 使用した根拠（MemoryOS / WorldModel / 任意ツール） |
| `critique[]` | 自己批判と弱点 |
| `debate[]` | 賛成/反対/第三者視点 |
| `telos_score` | ValueCoreに対する整合スコア |
| `fuji` | FUJI Gate判定（allow / modify / rejected） |
| `gate.decision_status` | 正規化済み最終ステータス（`DecisionStatus`） |
| `trust_log` | ハッシュチェーンTrustLogエントリ（`sha256_prev`） |

パイプラインのメンタルモデル:

```text
Options → Evidence → Critique → Debate → Planner → ValueCore → FUJI → TrustLog
```

同梱サブシステム:

- **MemoryOS** — エピソード/セマンティック記憶と検索
- **WorldModel** — 世界状態、プロジェクト、進捗スナップショット
- **ValueCore** — 価値関数と Value EMA
- **FUJI Gate** — 安全/倫理/コンプライアンスゲート
- **TrustLog** — ハッシュチェーン監査ログ（JSONL）
- **Doctor** — 診断とダッシュボード

---

## API概要

保護対象エンドポイントは `X-API-Key` が必要です。

| Method | Path                  | 説明 |
| ------ | --------------------- | ---- |
| GET    | `/health`             | ヘルスチェック |
| POST   | `/v1/decide`          | フル意思決定ループ |
| POST   | `/v1/fuji/validate`   | 単一アクションをFUJIで評価 |
| POST   | `/v1/memory/put`      | 記憶を保存 |
| GET    | `/v1/memory/get`      | 記憶を取得 |
| GET    | `/v1/logs/trust/{id}` | TrustLogエントリをIDで取得 |

---

## Quickstart

### 1) インストール

```bash
git clone https://github.com/veritasfuji-japan/veritas_os.git
cd veritas_os

python3.11 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

> [!WARNING]
> シークレットをシェル履歴へ直接残す運用は避けてください。`.env`（gitignore対象）または本番向けシークレットマネージャーを推奨します。

### 2) 環境変数設定

```bash
export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
export VERITAS_API_KEY="your-secret-api-key"
export VERITAS_API_SECRET="your-long-random-secret"
export LLM_PROVIDER="openai"
export LLM_MODEL="gpt-4.1-mini"
export VERITAS_MAX_REQUEST_BODY_SIZE="10485760"
```

### 3) サーバー起動

```bash
python -m uvicorn veritas_os.api.server:app --reload --port 8000
```

### 4) Swagger UIで試す

- 開く: `http://127.0.0.1:8000/docs`
- 認証ヘッダー: `X-API-Key: $VERITAS_API_KEY`
- 実行: `POST /v1/decide`

例:

```json
{
  "query": "明日の外出前に天気を確認すべきですか？",
  "context": {
    "user_id": "test_user",
    "goals": ["health", "efficiency"],
    "constraints": ["time limit"],
    "affect_hint": "focused"
  }
}
```

---

## Operational Security Deep Dive

- **プレースホルダ/短いシークレットは使用しない**: `VERITAS_API_SECRET` は長くランダムな値（推奨32文字以上）を設定してください。短い値や既知値はHMAC保護を実質的に弱体化します。
- **CORS安全性**: `allow_credentials` が有効な場合、ワイルドカードオリジン（`*`）は避け、信頼済みオリジンを明示してください。
- **Legacy pickle移行は高リスク**: MemoryOS で旧pickle移行を有効化する場合、短期移行用途に限定し、完了後は無効化してください。

---

## Docker（GHCR）

最新イメージ取得:

```bash
docker pull ghcr.io/veritasfuji-japan/veritas_os:latest
```

APIサーバー起動（上記uvicornコマンド相当）:

```bash
docker run --rm -p 8000:8000 \
  -e OPENAI_API_KEY="YOUR_OPENAI_API_KEY" \
  -e VERITAS_API_KEY="your-secret-api-key" \
  -e LLM_PROVIDER="openai" \
  -e LLM_MODEL="gpt-4.1-mini" \
  ghcr.io/veritasfuji-japan/veritas_os:latest
```

FastAPIエントリポイントが `veritas_os.api.server:app` と異なる場合は、イメージビルド前に Dockerfile の `CMD` を環境に合わせて更新してください。

---

## アーキテクチャ（高レベル）

### コア実行パス

- `veritas_os/core/kernel.py` — `/v1/decide` のオーケストレーション
- `veritas_os/core/pipeline.py` — ステージ順序 + メトリクス（`latency_ms` と `stage_latency`）
- `veritas_os/core/llm_client.py` — LLM呼び出しの**単一**ゲートウェイ（`chat_completion`）

### 安全性とガバナンス

- `veritas_os/core/fuji.py` — FUJI Gate（allow/modify/reject）
- `veritas_os/core/value_core.py` — 価値関数 + Value EMA
- `veritas_os/logging/trust_log.py`（または相当実装） — ハッシュチェーンTrustLog

### 記憶と世界状態

- `veritas_os/core/memory.py` — MemoryOSフロントエンド
- `veritas_os/core/world.py` — 世界状態スナップショット

---

## TrustLog（ハッシュチェーン監査ログ）

TrustLog は追記専用JSONLです。各エントリはハッシュポインタを持ちます。

```text
h_t = SHA256(h_{t-1} || r_t)
```

これにより整合性検証と改ざん検知可能な監査証跡を実現します。

---

## テスト

推奨（再現性重視）:

```bash
make test
make test-cov
```

これらのターゲットは `uv` + `PYTHON_VERSION=3.12.12` を利用し、未導入時はインタプリタを自動取得します。

スモークチェック:

```bash
make test TEST_ARGS="-q veritas_os/tests/test_api_constants.py"
```

オプション上書き:

```bash
make test TEST_ARGS="-q veritas_os/tests/test_time_utils.py"
make test PYTHON_VERSION=3.11
```

### CI / Quality Gate

- GitHub Actions は Python 3.11/3.12 マトリクスで **pytest + coverage** を実行
- Coverage成果物は **XML/HTML** で保存
- CIは最小カバレッジゲート（`--cov-fail-under`）を現在 **85%** に設定
- Coverageバッジは現時点で `docs/COVERAGE_REPORT.md` のドキュメントスナップショット値（将来的にCI成果物から自動更新予定）
- テスト失敗時はCIジョブが失敗し、品質ゲートとして機能

## セキュリティ注意（重要）

### 認証情報・鍵管理

- **APIキー**: シェル履歴に直接残る `export` は可能な限り避け、`.env`（gitignore対象）またはシークレットマネージャー利用を推奨。定期ローテーションと最小権限設定を実施してください。
- **プレースホルダ/短いシークレットを使わない**: `VERITAS_API_SECRET` は長くランダムな値（推奨32文字以上）を設定。短い値や既知値はHMAC保護を実質的に無効化・弱体化する恐れがあります。

### API・ブラウザ向け保護

- **CORS安全性**: `allow_credentials` を有効にしたままワイルドカード（`*`）を許可しないでください。信頼済みオリジンのみ明示設定してください。
- **CORS と APIキーは必須設定**: unsafe defaultを避けるため、`VERITAS_CORS_ALLOW_ORIGINS` と `VERITAS_API_KEY` を必ず設定してください。

### データ安全性・永続化

- **TrustLogデータ**: TrustLogは追記専用JSONLです。ペイロードにPII/機微情報が含まれる可能性がある場合、アクセス制御・保持期間・必要に応じた保存時暗号化を実施してください。
- **TrustLog/Memory保存前にPIIマスキングを強制**: 漏えいリスク低減のため保存前に `redact()` を適用してください。
- **保存時暗号化（任意）**: TrustLog/Memoryは平文保存です。要件に応じて暗号化またはKMS統合を検討してください。
- **運用ログはGit管理対象外**: 例として `veritas_os/memory/*.jsonl` のランタイムログは `.gitignore` で除外され、匿名化サンプルは `veritas_os/sample_data/memory/` 配下にあります。

### 移行時の安全性

- **Legacy pickle移行は高リスク**: MemoryOSの旧pickle移行を有効化する場合、短期移行パスとして扱い、移行完了後に必ず無効化してください。

---

## ロードマップ（短期）

- CI（GitHub Actions）: pytest + coverage + artifactレポート
- セキュリティ強化: 入力検証と秘密情報/ログ衛生
- Policy-as-Code: **Policy → ValueCore/FUJIルール → テスト自動生成**（コンパイラ層）

---

## ライセンス

このリポジトリは、ディレクトリ単位でスコープが明確な **マルチライセンス** 構成です。

### ライセンスマトリクス（ディレクトリ別）

| Scope | License | 商用利用 | 再配布 | 備考 |
|---|---|---|---|---|
| Default（明示上書きのない全体） | VERITAS Core Proprietary EULA（`/LICENSE`） | 契約必要 | 書面許可なし不可 | Core意思決定ロジックとパイプラインを含む |
| `spec/` | MIT（`/spec/LICENSE`） | 可 | 可 | オープンなインターフェース成果物 |
| `sdk/` | MIT（`/sdk/LICENSE`） | 可 | 可 | SDKインターフェース層 |
| `cli/` | MIT（`/cli/LICENSE`） | 可 | 可 | CLIインターフェース層 |
| `policies/examples/` | MIT（`/policies/examples/LICENSE`） | 可 | 可 | ポリシーテンプレート/例 |

### Core不正利用防止の主な制限（概要）

Core Proprietary EULA の下で、以下は禁止されます。

- Core（または実質的に同等機能）を競合マネージドサービスとして提供する行為
- ライセンスキー・メータリング・その他技術的保護の回避
- 著作権表示、帰属表示、プロプライエタリ表示、商標表示の削除
- 商用契約なしでのCore再配布または商用本番利用

詳細は [`LICENSE`](LICENSE)、[`TRADEMARKS`](TRADEMARKS)、[`NOTICE`](NOTICE) を参照してください。

### 既存ユーザー向け移行ノート

本変更は既存方針を、より明確な二層構造として明文化したものです。

- Coreは既定でプロプライエタリのまま
- インターフェース資産はディレクトリ単位で明示的にオープンライセンス化
- 本変更でCoreロジック（Planner/Kernel/FUJI/TrustLogパイプライン内部）はオープンソース化されません

### ライセンス分離ロードマップ（Plan B モノレポ → Plan A マルチレポ）

Phase 1（このPR）:
- モノレポ内でのディレクトリスコープライセンス（Core proprietary + interface MIT）

Phase 2（次PR群）:
- `veritas-spec`（OpenAPI/schema）
- `veritas-sdk-python`, `veritas-sdk-js`
- `veritas-cli`
- `veritas-policy-templates`
- `veritas_os` は proprietary Core に集中

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

- Issues: [https://github.com/veritasfuji-japan/veritas_os/issues](https://github.com/veritasfuji-japan/veritas_os/issues)
- Email: [veritas.fuji@gmail.com](mailto:veritas.fuji@gmail.com)
