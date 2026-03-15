# VERITAS OS v2.0 — LLMエージェント向け監査可能な意思決定OS（Proto-AGI Skeleton）

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.17838349.svg)](https://doi.org/10.5281/zenodo.17838349)
[![DOI（日本語論文）](https://zenodo.org/badge/DOI/10.5281/zenodo.17838456.svg)](https://doi.org/10.5281/zenodo.17838456)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Next.js](https://img.shields.io/badge/Next.js-15-black.svg)](https://nextjs.org/)
[![License](https://img.shields.io/badge/license-Multi--license%20(Core%20Proprietary%20%2B%20MIT)-purple.svg)](LICENSE)
[![CI](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/main.yml/badge.svg)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/main.yml)
[![CodeQL](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/codeql.yml)
[![Docker Publish](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/publish-ghcr.yml/badge.svg)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/publish-ghcr.yml)
[![Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen.svg)](docs/COVERAGE_REPORT.md) <!-- docs/COVERAGE_REPORT.md のスナップショット値。CIゲートは .github/workflows/main.yml で管理 -->
[![GHCR](https://img.shields.io/badge/GHCR-ghcr.io%2Fveritasfuji--japan%2Fveritas__os-2496ED?logo=docker&logoColor=white)](https://ghcr.io/veritasfuji-japan/veritas_os)
[![README EN](https://img.shields.io/badge/README-English-1d4ed8.svg)](README.md)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Takeshi%20Fujishita-0A66C2?logo=linkedin&logoColor=white)](https://www.linkedin.com/in/takeshi-fujishita-279709392?utm_source=share&utm_campaign=share_via&utm_content=profile&utm_medium=ios_app)

**Version**: 2.0.0  
**Release Status**: 開発中  
**Author**: Takeshi Fujishita

VERITAS OS は、LLM（例: OpenAI GPT-4.1-mini）を **高再現性・fail-closed安全ゲート付き・ハッシュチェーン監査可能** な意思決定パイプラインで包み、リアルタイム運用可視化のための **Mission Controlダッシュボード**（Next.js）を提供します。

> メンタルモデル: **LLM = CPU**、**VERITAS OS = その上に載る Decision / Agent OS**

### 独立技術DDスコア

| カテゴリ | スコア |
|---|---|
| Architecture | 82 |
| Code Quality | 83 |
| Security | 80 |
| Testing | 88 |
| Production Readiness | 80 |
| Governance | 82 |
| **Overall** | **82 / 100** |
| **判定** | **A-（本番接近レベルのガバナンスインフラ）** |

> 独立技術デューデリジェンスレビュー（2026-03-15）による評価。詳細: `docs/reviews/technical_dd_review_ja_20260315.md`

---

## クイックリンク

- **GitHub**: https://github.com/veritasfuji-japan/veritas_os
- **Zenodo論文（英語）**: https://doi.org/10.5281/zenodo.17838349
- **Zenodo論文（日本語）**: https://doi.org/10.5281/zenodo.17838456
- **英語README**: [`README.md`](README.md)
- **レビュー文書マップ**: `docs/notes/CODE_REVIEW_DOCUMENT_MAP.md`

## 目次

- [なぜVERITASか](#なぜveritasか)
- [できること](#できること)
- [プロジェクト構成](#プロジェクト構成)
- [フロントエンド — Mission Controlダッシュボード](#フロントエンド--mission-controlダッシュボード)
- [API概要](#api概要)
- [Quickstart](#quickstart)
- [Docker Compose（フルスタック）](#docker-composeフルスタック)
- [Docker（バックエンドのみ）](#dockerバックエンドのみ)
- [アーキテクチャ（高レベル）](#アーキテクチャ高レベル)
- [TrustLog（ハッシュチェーン監査ログ）](#trustlogハッシュチェーン監査ログ)
- [テスト](#テスト)
- [セキュリティ注意（重要）](#セキュリティ注意重要)
- [ロードマップ（短期）](#ロードマップ短期)
- [ライセンス](#ライセンス)
- [引用（BibTeX）](#引用bibtex)

---

## なぜVERITASか

多くの「エージェントフレームワーク」は自律性やツール実行を最適化します。  
VERITAS は **ガバナンス** を最適化します。

- **Fail-closed安全性・コンプライアンス**: 最終ゲート（**FUJI Gate**）でPII検出・有害コンテンツブロック・プロンプトインジェクション防御・Web検索結果の毒性フィルタリング・ポリシー駆動ルールを強制 — 全安全経路は例外時に `rejected` / `risk=1.0` を返却（fail-closed）
- **高再現性意思決定パイプライン**（20以上のステージ、構造化出力、差分検知付きリプレイ、取得スナップショットチェックサム、モデルバージョン検証）
- **ハッシュチェーンTrustLog** による監査可能性（改ざん検知、Ed25519署名、WORM hard-failミラー、**Transparency logアンカー**、**W3C PROV輸出**）
- **エンタープライズガバナンス** — ポリシー変更の**4-eyes承認**、**RBAC/ABAC**アクセス制御、**SSEリアルタイムガバナンスアラート**、外部シークレットマネージャー強制
- **MemoryOS**（ベクトル検索）+ **WorldModel**（因果遷移）を一次入力として扱う
- フルスタック **Mission Controlダッシュボード**（Next.js）によるリアルタイムイベントストリーミング、リスク分析、ガバナンスポリシー管理
- **EU AI Act準拠** — コンプライアンスレポート生成、監査エクスポート、デプロイメント準備チェック

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
| `evidence[]` | 使用した根拠（MemoryOS / WorldModel / Web検索） |
| `critique[]` | 自己批判と弱点 |
| `debate[]` | 賛成/反対/第三者視点 |
| `telos_score` | ValueCoreに対する整合スコア |
| `fuji` | FUJI Gate判定（allow / modify / rejected） |
| `gate.decision_status` | 正規化済み最終ステータス（`DecisionStatus`） |
| `trust_log` | ハッシュチェーンTrustLogエントリ（`sha256_prev`） |
| `extras.metrics` | ステージ毎のレイテンシ、メモリヒット数、Webヒット数 |

パイプラインステージ:

```text
入力正規化 → メモリ検索 → Web検索 → オプション正規化
  → コア実行 → 結果吸収 → フォールバック代替案 → モデルブースト
  → 討論 → 批評 → FUJIプレチェック → ValueCore → ゲート判定
  → 価値学習（EMA） → メトリクス計算 → エビデンス強化
  → レスポンス組立 → 永続化（監査＋メモリ＋世界状態） → エビデンス最終化
  → リプレイスナップショット構築
```

同梱サブシステム:

| サブシステム | 目的 |
|---|---|
| **MemoryOS** | エピソード/セマンティック/手続き/感情記憶とベクトル検索（sentence-transformers）、保持クラス、法的ホールド、PIIマスキング |
| **WorldModel** | 世界状態スナップショット、因果遷移、プロジェクトスコープ、仮想シミュレーション |
| **ValueCore** | 14次元加重（コア倫理9＋ポリシー5）の価値関数、EMAによるオンライン学習、TrustLogフィードバックからの自動リバランス |
| **FUJI Gate** | 多層安全ゲート — PII検出、有害コンテンツブロック、機微ドメインフィルタ、プロンプトインジェクション防御、紛らわしい文字検出、LLM安全ヘッド、ポリシー駆動YAMLルール |
| **TrustLog** | 追記専用ハッシュチェーン監査ログ（JSONL）、SHA-256完全性、Ed25519署名、WORM hard-failミラー、Transparency logアンカー、PII自動データ分類 |
| **Debate** | 多視点推論（賛成/反対/第三者）による透明な意思決定根拠 |
| **Critique** | 重大度ランク付きの自己批評生成と修正提案 |
| **Planner** | ステップバイステップ実行戦略を持つアクションプラン生成 |
| **Replay Engine** | 監査検証のための高再現性リプレイ（差分レポート、取得スナップショットチェックサム、モデルバージョン検証、依存バージョン追跡付き） |
| **Compliance** | EU AI Actコンプライアンスレポート、内部ガバナンスレポート、デプロイメント準備チェック |

---

## プロジェクト構成

```text
veritas_os/                  ← モノレポルート
├── veritas_os/              ← Pythonバックエンド（FastAPI）
│   ├── api/                 ← REST APIサーバー、スキーマ、ガバナンス
│   │   ├── server.py        ← 30以上のエンドポイントを持つFastAPIアプリ
│   │   ├── schemas.py       ← Pydantic v2リクエスト/レスポンスモデル
│   │   └── governance.py    ← 監査証跡付きポリシー管理
│   ├── core/                ← 意思決定エンジン
│   │   ├── kernel.py        ← 意思決定計算エンジン
│   │   ├── pipeline.py      ← 20以上のステージオーケストレータ
│   │   ├── fuji.py          ← FUJI安全ゲート
│   │   ├── value_core.py    ← 価値整合とオンライン学習
│   │   ├── memory.py        ← MemoryOS（ベクトル検索）
│   │   ├── world.py         ← WorldModel（状態管理）
│   │   ├── llm_client.py    ← マルチプロバイダLLMゲートウェイ
│   │   ├── debate.py        ← 討論メカニズム
│   │   ├── critique.py      ← 批評生成
│   │   ├── planner.py       ← アクションプランニング
│   │   └── sanitize.py      ← PIIマスキングとコンテンツ安全性
│   ├── logging/             ← TrustLog、データセットライター、ローテーション
│   ├── audit/               ← 署名付き監査ログ（Ed25519）
│   ├── compliance/          ← EU AI Actレポートエンジン
│   ├── security/            ← SHA-256ハッシュ、Ed25519署名
│   ├── tools/               ← Web検索、GitHub検索、LLM安全性
│   ├── replay/              ← 決定論的リプレイエンジン
│   └── tests/               ← 3200以上のPythonテスト
├── frontend/                ← Next.js 15 Mission Controlダッシュボード
│   ├── app/                 ← ページ（Home、Console、Audit、Governance、Risk）
│   ├── components/          ← 共有Reactコンポーネント
│   ├── features/console/    ← Decision Console機能モジュール
│   ├── lib/                 ← APIクライアント、バリデータ、ユーティリティ
│   ├── locales/             ← i18n（日本語 / 英語）
│   └── e2e/                 ← Playwright E2Eテスト
├── packages/
│   ├── types/               ← 共有TypeScript型定義とランタイムバリデータ
│   └── design-system/       ← Card、Button、AppShellコンポーネント
├── spec/                    ← OpenAPI仕様（MIT）
├── sdk/                     ← SDKインターフェース層（MIT）
├── cli/                     ← CLIインターフェース層（MIT）
├── policies/                ← ポリシーテンプレート（examplesはMIT）
├── openapi.yaml             ← OpenAPI 3.x仕様
├── docker-compose.yml       ← フルスタックオーケストレーション
├── Makefile                 ← 開発/テスト/デプロイコマンド
└── pyproject.toml           ← Pythonプロジェクト設定
```

---

## フロントエンド — Mission Controlダッシュボード

フロントエンドは **Next.js 15**（React 18、TypeScript）によるダッシュボードで、意思決定パイプラインの運用可視性を提供します。

### 技術スタック

| レイヤー | 技術 |
|---|---|
| フレームワーク | Next.js 15.5（App Router） |
| 言語 | TypeScript 5.7 |
| スタイリング | Tailwind CSS 3.4 + CVA（class-variance-authority） |
| アイコン | Lucide React |
| テスト | Vitest + Testing Library（ユニット）、Playwright + axe-core（E2E + アクセシビリティ） |
| i18n | カスタムReact Context（日本語デフォルト、英語対応） |
| セキュリティ | リクエスト毎ノンス付きCSP、httpOnly BFFクッキー、HSTS、X-Frame-Options |
| デザインシステム | `@veritas/design-system`（Card、Button、AppShell） |
| 共有型定義 | `@veritas/types`（ランタイム型ガード付き） |

### ページ

| ルート | ページ | 説明 |
|---|---|---|
| `/` | **コマンドダッシュボード** | ライブイベントストリーム（FUJIリジェクト、ポリシー更新、チェーン破損）、グローバルヘルスサマリー、クリティカルレール指標、運用優先事項 |
| `/console` | **Decision Console** | インタラクティブ意思決定パイプライン — クエリ入力後、8ステージパイプラインがリアルタイム実行され、FUJIゲート判定、選択/代替/棄却、コストベネフィット分析、リプレイ差分を表示 |
| `/audit` | **TrustLogエクスプローラ** | ハッシュチェーン監査証跡のブラウズ、チェーン完全性検証（verified/broken/missing/orphan）、ステージフィルタ、規制レポートエクスポート（JSON/CSV、PIIリダクション対応） |
| `/governance` | **ガバナンスコントロール** | FUJIルール（8つの安全ゲート）、リスク閾値、自動停止サーキットブレーカー、ログ保持の編集。標準モードとEU AI Actモード。ドラフト → 承認ワークフロー、差分ビューア、バージョン履歴 |
| `/risk` | **リスクダッシュボード** | 24時間ストリーミングリスク/不確実性チャート、重大度クラスタリング、フラグ付きリクエストのドリルダウン、異常パターン分析 |

### アーキテクチャ

- **BFF（Backend-for-Frontend）**パターン: すべてのAPIリクエストはNext.js（`/api/veritas/*`）経由でプロキシされ、ブラウザはAPI認証情報を見ない
- **httpOnlyセッションクッキー**（`__veritas_bff`）による認証、`/api/veritas/*`にスコープ
- **ランタイム型ガード**がすべてのAPIレスポンスを描画前に検証（`isDecideResponse`、`isTrustLogsResponse`、`validateGovernancePolicyResponse`等）
- **SSE + WebSocket**によるリアルタイムイベントストリーミング（ライブFUJIリジェクト、TrustLog更新、リスクバースト）
- すべてのAPIレスポンス描画に`sanitizeText()`による**XSS防御**

---

## API概要

保護対象エンドポイントは `X-API-Key` が必要です。全エンドポイント一覧:

### 意思決定

| Method | Path | 説明 |
|---|---|---|
| POST | `/v1/decide` | フル意思決定パイプライン |
| POST | `/v1/fuji/validate` | 単一アクションをFUJI Gateで評価 |
| POST | `/v1/replay/{decision_id}` | 差分レポート付き決定論的リプレイ |
| POST | `/v1/decision/replay/{decision_id}` | モックサポート付き代替リプレイ |

### メモリ

| Method | Path | 説明 |
|---|---|---|
| POST | `/v1/memory/put` | メモリ保存（エピソード/セマンティック/手続き/感情） |
| POST | `/v1/memory/get` | キーによるメモリ取得 |
| POST | `/v1/memory/search` | user_idフィルタ付きベクトル検索 |
| POST | `/v1/memory/erase` | ユーザーメモリ消去（法的ホールド保護） |

### Trust & 監査

| Method | Path | 説明 |
|---|---|---|
| GET | `/v1/trust/logs` | TrustLogエントリ一覧 |
| GET | `/v1/trust/{request_id}` | 単一TrustLogエントリ取得 |
| POST | `/v1/trust/feedback` | 意思決定に対するユーザー満足度フィードバック |
| GET | `/v1/trust/stats` | TrustLog統計 |
| GET | `/v1/trustlog/verify` | ハッシュチェーン完全性検証 |
| GET | `/v1/trustlog/export` | 署名付きTrustLogエクスポート |
| GET | `/v1/trust/{request_id}/prov` | 監査相互運用性のためのW3C PROV-JSON輸出 |

### ガバナンス

| Method | Path | 説明 |
|---|---|---|
| GET | `/v1/governance/policy` | 現行ガバナンスポリシー取得 |
| PUT | `/v1/governance/policy` | ガバナンスポリシー更新（ホットリロード、**4-eyes承認必須**） |
| GET | `/v1/governance/policy/history` | ポリシー変更監査証跡 |
| GET | `/v1/governance/value-drift` | 価値重みEMAドリフト監視 |

### コンプライアンス & レポート

| Method | Path | 説明 |
|---|---|---|
| GET | `/v1/report/eu_ai_act/{decision_id}` | EU AI Actコンプライアンスレポート |
| GET | `/v1/report/governance` | 内部ガバナンスレポート |
| GET | `/v1/compliance/deployment-readiness` | デプロイメント前コンプライアンスチェック |

### システム

| Method | Path | 説明 |
|---|---|---|
| GET | `/health`, `/v1/health` | ヘルスチェック |
| GET | `/status`, `/v1/status` | パイプライン/設定ヘルス付き拡張ステータス |
| GET | `/v1/metrics` | 運用メトリクス |
| GET | `/v1/events` | リアルタイムUI更新用SSEストリーム |
| WS | `/v1/ws/trustlog` | ライブTrustLogストリーミング用WebSocket |
| POST | `/v1/system/halt` | 緊急停止（停止状態を永続化） |
| POST | `/v1/system/resume` | 停止後の再開 |
| GET | `/v1/system/halt-status` | 現在の停止状態 |

### Replay

`POST /v1/replay/{decision_id}` は、保存済み意思決定を元の記録入力で再実行し、`REPLAY_REPORT_DIR`（既定: `audit/replay_reports`）に `replay_{decision_id}_{YYYYMMDD_HHMMSS}.json` として成果物を出力します。

Replayスナップショットには `retrieval_snapshot_checksum`（SHA-256決定論的ハッシュ）、`external_dependency_versions`、`model_version` が含まれ、再現性検証に使用されます。モデルバージョン不一致はデフォルトでチェックされ、`model_version` 未記録のスナップショットはデフォルトで拒否されます（`VERITAS_REPLAY_REQUIRE_MODEL_VERSION=1`）。

> **注意**: LLM応答は `temperature=0` でも本質的に非決定的です。VERITAS Replayは厳密な決定論的リプレイではなく、**差分検知付き高再現性再実行**として設計されています。

`VERITAS_REPLAY_STRICT=1` の場合、Replayは決定論設定（`temperature=0`、固定seed、外部取得の副作用モック）を強制します。

```bash
BODY='{"strict":true}'
TS=$(date +%s)
NONCE="replay-$(uuidgen | tr '[:upper:]' '[:lower:]')"
SIG=$(python - <<'PY'
import hashlib
import hmac
import os

secret=os.environ["VERITAS_API_SECRET"].encode("utf-8")
ts=os.environ["TS"]
nonce=os.environ["NONCE"]
body=os.environ["BODY"]
payload=f"{ts}\n{nonce}\n{body}"
print(hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest())
PY
)

curl -X POST "http://127.0.0.1:8000/v1/replay/DECISION_ID" \
  -H "X-API-Key: ${VERITAS_API_KEY}" \
  -H "X-VERITAS-TIMESTAMP: ${TS}" \
  -H "X-VERITAS-NONCE: ${NONCE}" \
  -H "X-VERITAS-SIGNATURE: ${SIG}" \
  -H "Content-Type: application/json" \
  -d "${BODY}"
```

EU AI Actレポート生成は `replay_{decision_id}_*.json` を既に参照しているため、Replay APIの実行により、コンプライアンスレポートが利用するReplay検証データも自動更新されます。

---

## Quickstart

### オプションA: Docker Compose（推奨）

バックエンドとフロントエンドを1コマンドで起動:

```bash
git clone https://github.com/veritasfuji-japan/veritas_os.git
cd veritas_os

# 環境変数をコピーして編集
cp .env.example .env
# .envを編集 — OPENAI_API_KEY、VERITAS_API_KEY、VERITAS_API_SECRETを設定

docker compose up --build
```

- バックエンド: `http://localhost:8000`（Swagger UIは`/docs`）
- フロントエンド: `http://localhost:3000`（Mission Controlダッシュボード）

### オプションB: ローカル開発

#### バックエンド

```bash
git clone https://github.com/veritasfuji-japan/veritas_os.git
cd veritas_os

python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
```

> [!WARNING]
> シークレットをシェル履歴へ直接残す運用は避けてください。`.env`（gitignore対象）または本番向けシークレットマネージャーを推奨します。

環境変数設定（または`.env`ファイル使用）:

```bash
export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
export VERITAS_API_KEY="your-secret-api-key"
export VERITAS_API_SECRET="your-long-random-secret"
export LLM_PROVIDER="openai"
export LLM_MODEL="gpt-4.1-mini"
```

バックエンド起動:

```bash
python -m uvicorn veritas_os.api.server:app --reload --port 8000
```

#### フロントエンド

```bash
# リポジトリルートから（Node.js 20+とpnpmが必要）
corepack enable
pnpm install --frozen-lockfile
pnpm ui:dev
```

フロントエンドは `http://localhost:3000` で起動します。

バックエンドが `http://localhost:8000` でない場合は `NEXT_PUBLIC_API_BASE_URL` を設定してください。

#### Makefileショートカット

```bash
make setup         # 環境初期化
make dev           # バックエンド起動（ポート8000）
make dev-frontend  # フロントエンド起動（ポート3000）
make dev-all       # 両方起動
```

### APIを試す

Swagger UI（`http://127.0.0.1:8000/docs`）を開き、`X-API-Key`で認証して `POST /v1/decide` を実行:

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

## Docker Compose（フルスタック）

`docker-compose.yml` が両サービスをオーケストレーション:

| サービス | ポート | 説明 |
|---|---|---|
| `backend` | 8000 | FastAPIサーバー（`Dockerfile`からビルド）、ヘルスチェック付き |
| `frontend` | 3000 | Next.js開発サーバー（Node.js 20）、バックエンドの正常起動を待機 |

```bash
docker compose up --build   # 起動
docker compose down         # 停止
docker compose logs -f      # ログ追跡
```

環境変数（`.env`またはシェルで設定）:

| 変数 | デフォルト | 説明 |
|---|---|---|
| `OPENAI_API_KEY` | — | OpenAI APIキー（必須） |
| `VERITAS_API_KEY` | — | バックエンドAPI認証キー |
| `VERITAS_API_SECRET` | `change-me` | HMAC署名シークレット（推奨32文字以上） |
| `VERITAS_CORS_ALLOW_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | CORSホワイトリスト |
| `NEXT_PUBLIC_API_BASE_URL` | `http://backend:8000` | フロントエンド → バックエンドURL |
| `LLM_PROVIDER` | `openai` | LLMプロバイダ |
| `LLM_MODEL` | `gpt-4.1-mini` | LLMモデル名 |

---

## Docker（バックエンドのみ）

最新イメージ取得:

```bash
docker pull ghcr.io/veritasfuji-japan/veritas_os:latest
```

APIサーバー起動:

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

```text
┌──────────────────────────────────────────────────────┐
│  フロントエンド (Next.js 15 / React 18 / TypeScript)  │
│  ┌────────┬──────────┬───────────┬──────────┬──────┐ │
│  │  Home  │ Console  │   Audit   │Governance│ Risk │ │
│  └────┬───┴────┬─────┴─────┬─────┴────┬─────┴──┬───┘ │
│       │ BFF Proxy (httpOnlyクッキー, CSPノンス) │      │
│       └─────────────────┬───────────────────────┘     │
└─────────────────────────┼─────────────────────────────┘
                          │ /api/veritas/*
┌─────────────────────────┼─────────────────────────────┐
│  バックエンド (FastAPI / Python 3.11+)                  │
│       ┌─────────────────┴─────────────────────┐       │
│       │          APIサーバー (server.py)        │       │
│       │  認証 · レート制限 · CORS · PIIマスク   │       │
│       └────┬──────┬──────┬──────┬──────┬──────┘       │
│            │      │      │      │      │              │
│  ┌─────────┴┐ ┌───┴───┐ ┌┴─────┐ ┌────┴──┐ ┌────────┴┐│
│  │Pipeline ││ガバナ ││メモリ ││Trust ││コンプラ ││
│  │オーケスト││ ンス  ││ API  ││ API  ││イアンス ││
│  └────┬─────┘└────────┘└──┬───┘└───┬───┘└─────────┘│
│       │                    │       │               │
│  ┌────┴────────────────────┴───────┴────────────┐  │
│  │          コア意思決定エンジン                   │  │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ │  │
│  │  │ Kernel │ │ Debate │ │Critique│ │Planner │ │  │
│  │  └────┬───┘ └────────┘ └────────┘ └────────┘ │  │
│  │       │                                       │  │
│  │  ┌────┴───┐ ┌────────┐ ┌────────┐ ┌────────┐ │  │
│  │  │  FUJI  │ │Value   │ │MemoryOS│ │ World  │ │  │
│  │  │  Gate  │ │ Core   │ │(Vector)│ │ Model  │ │  │
│  │  └────────┘ └────────┘ └────────┘ └────────┘ │  │
│  └──────────────────┬───────────────────────────┘  │
│                     │                              │
│  ┌──────────────────┴───────────────────────────┐  │
│  │  インフラストラクチャ                          │  │
│  │  LLMクライアント · TrustLog · Replay · 無害化 │  │
│  │  Atomic I/O · 署名 · ツール (Web/GitHub)      │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### コア実行パス

| モジュール | 責務 |
|---|---|
| `veritas_os/core/kernel.py` | 意思決定計算 — インテント検出、オプション生成、代替案スコアリング |
| `veritas_os/core/pipeline.py` | `/v1/decide` の20以上のステージオーケストレータ — 検証から監査永続化まで |
| `veritas_os/core/llm_client.py` | コネクションプーリング、サーキットブレーカー、リトライ付きマルチプロバイダLLMゲートウェイ |

### 安全性とガバナンス

| モジュール | 責務 |
|---|---|
| `veritas_os/core/fuji.py` | 多層**fail-closed**安全ゲート — PII、有害コンテンツ、機微ドメイン、プロンプトインジェクション、紛らわしい文字、LLM安全ヘッド、ポリシールール。全例外で `rejected` / `risk=1.0` を返却 |
| `veritas_os/core/value_core.py` | 14次元加重（コア倫理9＋ポリシー5）の価値関数、EMAによるオンライン学習、TrustLogからの自動リバランス |
| `veritas_os/api/governance.py` | ホットリロード、**4-eyes承認**（2名・重複不可）、変更コールバック、監査証跡、価値ドリフト監視、**RBAC/ABAC**アクセス制御付きポリシーCRUD |
| `veritas_os/logging/trust_log.py` | ハッシュチェーンTrustLog `h_t = SHA256(h_{t-1} ∥ r_t)` スレッドセーフ追記 |
| `veritas_os/audit/trustlog_signed.py` | Ed25519署名付きTrustLog、**WORM hard-fail**ミラー、**Transparency logアンカー**、PII自動**データ分類** |

### 記憶と世界状態

| モジュール | 責務 |
|---|---|
| `veritas_os/core/memory.py` | エピソード/セマンティック/手続き/感情の統合記憶、ベクトル検索（sentence-transformers、384次元）、保持クラス、法的ホールド、PIIマスキング |
| `veritas_os/core/world.py` | 世界状態スナップショット、因果遷移、プロジェクトスコープ、仮想シミュレーション |

### 推論

| モジュール | 責務 |
|---|---|
| `veritas_os/core/debate.py` | 多視点討論（賛成/反対/第三者） |
| `veritas_os/core/critique.py` | 重大度ランク付き自己批評と修正提案 |
| `veritas_os/core/planner.py` | アクションプラン生成 |

### LLMクライアント

`LLM_PROVIDER`環境変数で複数プロバイダをサポート:

| プロバイダ | モデル | ステータス |
|---|---|---|
| `openai` | GPT-4.1-mini（デフォルト） | 本番 |
| `anthropic` | Claude | 予定 |
| `google` | Gemini | 予定 |
| `ollama` | ローカルモデル | 予定 |
| `openrouter` | アグリゲータ | 予定 |

機能: 共有`httpx.Client`によるコネクションプーリング（`LLM_POOL_MAX_CONNECTIONS=20`）、設定可能なバックオフ付きリトライ（`LLM_MAX_RETRIES=3`）、レスポンスサイズガード（16MB）、テスト用モンキーパッチ対応。

---

## TrustLog（ハッシュチェーン監査ログ）

TrustLog は **secure-by-default** の暗号化・ハッシュチェーン監査ログです。

### セキュリティパイプライン（エントリごと）

```text
entry → redact(PII + secrets) → canonicalize(RFC 8785) → chain hash → encrypt → append
```

1. **Redact** — PII（メール、電話、住所）およびシークレット（APIキー、Bearerトークン）を永続化前に自動マスキング。
2. **Canonicalize** — RFC 8785 正規化JSONにより決定論的ハッシュを保証。
3. **Chain hash** — `h_t = SHA256(h_{t-1} || r_t)` による改ざん検知可能な連鎖。
4. **Encrypt** — 保存時暗号化は**必須**（AES-256-GCM または HMAC-SHA256 CTR-mode）。暗号鍵なしでは平文保存は**不可能**です。
5. **Append** — 暗号化済み行をJSONLにfsync付きで追記。

### セットアップ

```bash
# 暗号鍵を生成（必須）
python -c "from veritas_os.logging.encryption import generate_key; print(generate_key())"

# 鍵を設定（TrustLog動作に必須）
export VERITAS_ENCRYPTION_KEY="<generated-key>"
```

> **警告**: `VERITAS_ENCRYPTION_KEY` 未設定の場合、TrustLog書き込みは `EncryptionKeyMissing` で失敗します。これは設計上の仕様です — 平文監査ログは禁止されています。

### 検証

```bash
# ハッシュチェーンの整合性を検証（復号鍵が必要）
python -m veritas_os.scripts.verify_trust_log
```

主要機能:

- **暗号チェーン** — RFC 8785正規化JSON、決定論的SHA-256
- **スレッドセーフ** — RLockによる保護とアトミックファイル書込み
- **二重永続化** — インメモリキャッシュ（最大2000件）+ 永続JSONLレジャー
- **署名付きエクスポート** — 改ざん防止配布のためのEd25519デジタル署名
- **チェーン検証** — `GET /v1/trustlog/verify` でフルチェーン検証
- **Transparency logアンカー** — 独立監査検証のための外部ログ連携（`VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED=1` でfail-closed運用）
- **WORM hard-fail** — WORMミラー書き込み失敗時に `SignedTrustLogWriteError` を送出（`VERITAS_TRUSTLOG_WORM_HARD_FAIL=1`）
- **W3C PROV輸出** — `GET /v1/trust/{request_id}/prov` で監査ツール相互運用性のためのPROV-JSONを返却
- **PIIマスキング・分類** — PII/シークレットの自動リダクションとデータ分類タグ付与（18パターン: メール、クレジットカード、電話、住所、IP、パスポート等）
- **フロントエンド可視化** — `/audit`のTrustLogエクスプローラでチェーン完全性ステータス表示（verified/broken/missing/orphan）

---

## テスト

### バックエンド（Python）

推奨（`uv`による再現性重視）:

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

### フロントエンド（TypeScript）

```bash
# ユニットテスト (Vitest + Testing Library)
pnpm ui:test

# 型チェック
pnpm ui:typecheck

# E2Eテスト (Playwright + axe-coreアクセシビリティ)
pnpm --filter frontend e2e:install
pnpm --filter frontend e2e
```

### CI / Quality Gate

- GitHub Actions は Python 3.11/3.12 マトリクスで **pytest + coverage** を実行
- CIは最小カバレッジゲート（`--cov-fail-under`）を現在 **85%** に設定
- **CodeQL** によるセキュリティ脆弱性スキャン
- **SBOM** のナイトリー生成
- **セキュリティゲート** ワークフローによる追加セキュリティチェック
- Coverage成果物は **XML/HTML** で保存
- Coverageバッジは `docs/COVERAGE_REPORT.md` のドキュメントスナップショット値（CI成果物からの自動更新を予定）

---

## セキュリティ注意（重要）

### 認証情報・鍵管理

- **APIキー**: シェル履歴に直接残る `export` は可能な限り避け、`.env`（gitignore対象）またはシークレットマネージャー利用を推奨。定期ローテーションと最小権限設定を実施してください。
- **プレースホルダ/短いシークレットを使わない**: `VERITAS_API_SECRET` は長くランダムな値（推奨32文字以上）を設定。短い値や既知値はHMAC保護を実質的に無効化・弱体化する恐れがあります。

### API・ブラウザ向け保護

- **CORS安全性**: `allow_credentials` を有効にしたままワイルドカード（`*`）を許可しないでください。`VERITAS_CORS_ALLOW_ORIGINS`で信頼済みオリジンのみ明示設定してください。
- **Content Security Policy（CSP）**: フロントエンドミドルウェアがリクエスト毎のノンスベースCSPヘッダーを注入。`connect-src 'self'`でXHR/fetchを同一オリジンに制限。
- **BFFセッションクッキー**: `__veritas_bff`はhttpOnly、Secure、本番環境ではSameSite=strict。ブラウザはAPI認証情報を見ません。
- **セキュリティヘッダー**: HSTS（1年、preload）、X-Frame-Options DENY、X-Content-Type-Options nosniff、Permissions-Policy（カメラ/マイク/位置情報無効）。
- **レート制限と認証失敗追跡**: キー毎のレート制限と認証失敗時の指数バックオフ。
- **ノンスリプレイ防御**: 重要操作はHMAC署名ノンスとTTLクリーンアップで保護。
- **リクエストボディサイズ制限**: `VERITAS_MAX_REQUEST_BODY_SIZE`で設定可能（デフォルト10MB）。

### データ安全性・永続化

- **TrustLogデータ**: TrustLogは**デフォルトで暗号化**されています（secure-by-default）。全エントリはPII/シークレットの自動リダクション後に暗号化されてから永続化されます。`VERITAS_ENCRYPTION_KEY` の設定が必須であり、未設定の場合は書き込みが失敗します。
- **PII/シークレットの自動リダクション**: メール、電話、住所、APIキー、Bearerトークン、シークレット文字列は保存前に自動マスキングされます — 手動の `redact()` 呼び出しは不要です。
- **保存時暗号化（必須）**: `VERITAS_ENCRYPTION_KEY`（base64エンコードされた32バイト鍵）を設定してください。`generate_key()` で生成できます。鍵はvault/KMSに保存し、ソースコードにコミットしないでください。
- **運用ログはGit管理対象外**: 例として `veritas_os/memory/*.jsonl` のランタイムログは `.gitignore` で除外され、匿名化サンプルは `veritas_os/sample_data/memory/` 配下にあります。

### Fail-closed安全パイプライン

- **FUJI Gate fail-closed**: 全安全判定の例外は `status=rejected`, `risk=1.0` を返却。エラー時のサイレントパススルーなし。
- **ガバナンス境界ガード**: `/v1/fuji/validate` はデフォルト403拒否 — 明示的オプトインが必要（`VERITAS_ENABLE_DIRECT_FUJI_API=1`）。
- **4-eyes承認**: ガバナンスポリシー更新には2名の異なる承認者が必要（重複不可、デフォルト有効）。
- **RBAC/ABAC**: `require_governance_access` ガードによるロール＋テナント検証をガバナンス管理エンドポイントに適用。
- **外部シークレットマネージャー強制**: `VERITAS_ENFORCE_EXTERNAL_SECRET_MANAGER=1` でVault/KMS統合なしの起動をブロック。
- **Web検索毒性フィルタ**: retrieval poisoning / prompt injectionヒューリスティック（NFKC正規化、URLデコード、base64デコード、leet-speak検知）。デフォルト有効（fail-closed）、`VERITAS_WEBSEARCH_ENABLE_TOXICITY_FILTER=0` で無効化。

### 移行時の安全性

- **Legacy pickle移行は高リスク**: MemoryOSの旧pickle移行を有効化する場合、短期移行パスとして扱い、移行完了後に必ず無効化してください。レガシーpickle/joblibの読み込みはRCE防止のためランタイムでブロックされます。

---

## ロードマップ（短期）

- CI（GitHub Actions）: pytest + coverage + artifactレポート
- セキュリティ強化: 入力検証と秘密情報/ログ衛生
- Policy-as-Code: **Policy → ValueCore/FUJIルール → テスト自動生成**（コンパイラ層）
- マルチプロバイダLLMサポート（Anthropic、Google、Ollama、OpenRouter）
- CI成果物からのカバレッジバッジ自動更新

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
