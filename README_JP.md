# VERITAS OS v2.0 — LLMエージェント向け意思決定ガバナンスOS

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.17838349.svg)](https://doi.org/10.5281/zenodo.17838349)
[![DOI（日本語論文）](https://zenodo.org/badge/DOI/10.5281/zenodo.17838456.svg)](https://doi.org/10.5281/zenodo.17838456)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org/)
[![License](https://img.shields.io/badge/license-Multi--license%20(Core%20Proprietary%20%2B%20MIT)-purple.svg)](LICENSE)
[![CI](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/main.yml/badge.svg)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/main.yml)
[![Release Gate](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/release-gate.yml/badge.svg)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/release-gate.yml)
[![CodeQL](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/codeql.yml)
[![Docker Publish](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/publish-ghcr.yml/badge.svg)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/publish-ghcr.yml)
[![Coverage](https://img.shields.io/badge/coverage-87%25-brightgreen.svg)](docs/ja/validation/coverage-report.md) <!-- docs/ja/validation/coverage-report.md のスナップショット値。CIゲートは .github/workflows/main.yml で管理 -->
[![GHCR](https://img.shields.io/badge/GHCR-ghcr.io%2Fveritasfuji--japan%2Fveritas__os-2496ED?logo=docker&logoColor=white)](https://ghcr.io/veritasfuji-japan/veritas_os)
[![README EN](https://img.shields.io/badge/README-English-1d4ed8.svg)](README.md)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Takeshi%20Fujishita-0A66C2?logo=linkedin&logoColor=white)](https://www.linkedin.com/in/takeshi-fujishita-279709392?utm_source=share&utm_campaign=share_via&utm_content=profile&utm_medium=ios_app)

**Version**: 2.0.0  
**Release Status**: ベータ版  
**Author**: Takeshi Fujishita

VERITAS OS は **Decision Governance and Bind-Boundary Control Plane for AI Agents**（AIエージェント向け意思決定ガバナンス / bind-boundary 制御プレーン）です。
エージェント実行の前段に **governance layer before execution** を置き、現実世界に影響する前に意思決定を制御します。

> メンタルモデル: **LLM = CPU**、**VERITAS OS = その上に載る Decision Governance OS**

## VERITAS OS は何か

- 実行前に意思決定を評価し、`proceed / hold / block / human_review_required` を判定するガバナンス層
- 意思決定を **reviewable / traceable / replayable / auditable / enforceable** にするための製品基盤
- Mission Control を通じて運用者がガバナンス状態を把握・運用できる実装

## 何を解決するか

企業環境・規制領域では「推論できるか」よりも「統制された実行ができるか」が課題になります。
VERITAS OS は次を実現します。

- **Reviewable**: 実行前レビュー可能な意思決定
- **Traceable**: 根拠とポリシーの追跡可能性
- **Replayable**: 差分検知つき再実行
- **Auditable**: 改ざん検知可能な監査証跡
- **Enforceable**: fail-closed 前提の制御強制

## runtime/orchestration ツールとの違い

- 主眼はタスク実行最適化ではなく、**意思決定ガバナンスと bind-boundary 統制**
- ポリシー・安全ゲートは **real-world effect の前** に適用
- TrustLog と governance identity により、監査可能な意思決定系譜を保持

## regulated / enterprise に適する理由

- 承認境界とポリシー適用ポイントが明示されている
- 事後検証向けのエビデンス保存とReplay経路がある
- secure/prod で fail-closed 起動検証を行うポスチャ設計

## VERITAS OS が「あるもの」と「ないもの」

- **あるもの**: AIエージェント向け Decision Governance and Bind-Boundary Control Plane（実行前ガバナンス＋bind-boundary統制層）
- **ないもの**: すべてのランタイムを置き換える実行基盤、または単なるオーケストレーション便利層

## 事実とロードマップの境界

- **現時点の事実（ベータ）**: `/v1/decide` 中心の意思決定パイプライン、FUJI fail-closed、TrustLog、Mission Control、ガバナンスAPIが実装済みで、公開上は **ベータ品質のガバナンス基盤** として位置づけます
- **現時点の事実（bind policy surface）**: bind-boundary adjudication は少なくとも次の2つの運用経路で実装されています。
  1) `PUT /v1/governance/policy`（governance policy update path）
  2) `POST /v1/governance/policy-bundles/promote`（policy bundle promotion path）
- **現時点の事実（bind outcome公開契約）**: ガバナンス系レスポンスでは `bind_outcome` / `bind_failure_reason` / `bind_reason_code` / `execution_intent_id` / `bind_receipt_id` を返し、`/v1/governance/bind-receipts*` でレシート本体を取得可能です
- **現時点の事実（replay/運用フロー）**: bind receipt はガバナンス成果物として保存され、運用・監査フローで再検証（revalidation/replay）に使える形へ進んでいます
- **現時点の境界**: 本番適用には環境ごとのハードニング・統合・運用審査が必要
- **将来方向（標準化）**: bind-boundary は複数の effect path を統治する標準枠組みへ拡張していく方針ですが、現時点で全経路完了を主張するものではありません
- **ロードマップ**: IdP/JWT スコープ連携の深耕、分散障害モード検証の拡張

### Technical Maturity Snapshot（内部）

> 本セクションは **self-assessment / internal re-evaluation**（内部再評価）であり、第三者認証ではありません。

- 最新の内部再評価日: **2026-04-15**
- 内部総合スナップショット: **85 / 100**（2026-03-15 の 82 から改善）
- 詳細テーブル・変更点・残存リスク: [`docs/ja/positioning/public-positioning.md`](docs/ja/positioning/public-positioning.md)

---

## クイックリンク

- **GitHub**: https://github.com/veritasfuji-japan/veritas_os
- **Zenodo論文（英語）**: https://doi.org/10.5281/zenodo.17838349
- **Zenodo論文（日本語）**: https://doi.org/10.5281/zenodo.17838456
- **英語README**: [`README.md`](README.md)
- **ユーザーマニュアル（日本語）**: [`docs/ja/guides/user-manual.md`](docs/ja/guides/user-manual.md)
- **コントリビューション**: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- **セキュリティポリシー**: [`SECURITY.md`](SECURITY.md)
- **ドキュメント総合インデックス**: [`docs/INDEX.md`](docs/INDEX.md)
- **PostgreSQL本番運用ガイド**: [`docs/en/operations/postgresql-production-guide.md`](docs/en/operations/postgresql-production-guide.md)
- **PostgreSQLドリルRunbook**: [`docs/en/operations/postgresql-drill-runbook.md`](docs/en/operations/postgresql-drill-runbook.md)
- **セキュリティ強化チェックリスト**: [`docs/en/operations/security-hardening.md`](docs/en/operations/security-hardening.md)
- **データベースマイグレーション**: [`docs/en/operations/database-migrations.md`](docs/en/operations/database-migrations.md)
- **バックエンドパリティカバレッジ**: [`docs/en/validation/backend-parity-coverage.md`](docs/en/validation/backend-parity-coverage.md)
- **ライブPostgreSQL検証エビデンス**: [`docs/live-postgresql-validation.md`](docs/live-postgresql-validation.md)
- **レガシーパスクリーンアップ**: [`docs/en/operations/legacy-path-cleanup.md`](docs/en/operations/legacy-path-cleanup.md)
- **レビュー文書マップ**: [`docs/ja/reviews/code-review-document-map.md`](docs/ja/reviews/code-review-document-map.md)
- **ドキュメント入口（英語）**: [`docs/en/README.md`](docs/en/README.md)
- **ドキュメント入口（日本語）**: [`docs/ja/README.md`](docs/ja/README.md)
- **公開ポジショニングガイド（英語）**: [`docs/en/positioning/public-positioning.md`](docs/en/positioning/public-positioning.md)
- **公開ポジショニングガイド（日本語）**: [`docs/ja/positioning/public-positioning.md`](docs/ja/positioning/public-positioning.md)
- **ドキュメント対応表**: [`docs/DOCUMENTATION_MAP.md`](docs/DOCUMENTATION_MAP.md)
- **運用Runbook**: [`docs/ja/operations/enterprise_slo_sli_runbook_ja.md`](docs/ja/operations/enterprise_slo_sli_runbook_ja.md)
- **ガバナンス署名運用Runbook**: [`docs/en/operations/governance-artifact-signing.md`](docs/en/operations/governance-artifact-signing.md)
- **ポリシーバンドル昇格ガイド（EN）**: [`docs/en/guides/governance-policy-bundle-promotion.md`](docs/en/guides/governance-policy-bundle-promotion.md)
- **ガバナンスアップグレード概要（Press）**: [`docs/press/governance_control_plane_upgrade_2026-04.md`](docs/press/governance_control_plane_upgrade_2026-04.md)

## 🚀 Quick Start（TL;DR）

```bash
# Clone & Docker Compose で起動（推奨）
git clone https://github.com/veritasfuji-japan/veritas_os.git
cd veritas_os
cp .env.example .env        # 編集: OPENAI_API_KEY、VERITAS_API_KEY、VERITAS_API_SECRET を設定
docker compose up --build

# バックエンド: http://localhost:8000 (Swagger UI: /docs)
# フロントエンド: http://localhost:3000 (Mission Control)
# PostgreSQL: localhost:5432 (デフォルトストレージバックエンドとして自動設定)
```

> **Docker ComposeはデフォルトでPostgreSQLを使用** します（Memory・TrustLog両方）。
> 確認: `curl -s http://localhost:8000/health | python3 -c "import json,sys; print(json.load(sys.stdin)['storage_backends'])"`
>
> 軽量なファイルベースバックエンドを使用する場合は、`.env`に以下を設定:
> ```
> VERITAS_MEMORY_BACKEND=json
> VERITAS_TRUSTLOG_BACKEND=jsonl
> ```

> **前提条件**: Docker 20+ と Docker Compose v2。ローカル開発の場合: Python 3.11+、Node.js 20+、pnpm。

## PostgreSQL本番パスと検証ステータス

このリポジトリでは、**MemoryOS と TrustLog の両方で PostgreSQL バックエンドが正式な本番パス**です。
JSON/JSONL バックエンドは、軽量なローカル開発や移行ワークフロー向けに引き続き利用できますが、
本番推奨ベースラインではありません。

- **Docker Compose のデフォルト:** `docker-compose.yml` で
  `VERITAS_MEMORY_BACKEND=postgresql` と
  `VERITAS_TRUSTLOG_BACKEND=postgresql` が設定されています。
- **実行時の確認ポイント:** 実行時に `/health` → `storage_backends` を確認し、
  有効なバックエンドを検証します。
- **ライブ PostgreSQL 検証は複数レイヤで実施:** CI スモーク（`pytest -m smoke`）、
  本番相当検証（`pytest -m "production or smoke"`）、ライブ検証エントリポイント
  （`make validate-postgresql-live`、`make validate-live`、workflow `production-validation.yml`）。

検証志向ドキュメント:

- [`docs/en/validation/backend-parity-coverage.md` — パリティ/実装検証の正本ソース](docs/en/validation/backend-parity-coverage.md)
- [`docs/en/validation/production-validation.md` — tier/promotion/release-gate の正本ソース](docs/en/validation/production-validation.md)
- [`docs/en/operations/postgresql-production-guide.md` — PostgreSQL運用/監視/復旧の正本ソース](docs/en/operations/postgresql-production-guide.md)
- [`docs/live-postgresql-validation.md` — ライブ PostgreSQL 検証の公開エビデンス入口](docs/live-postgresql-validation.md)

### 保証境界（現時点）

- **保証されること:** PostgreSQL が本番パスとして明文化されており、Docker Compose は
  PostgreSQL をデフォルトにし、バックエンドパリティ期待値が文書化され、
  本番バリデーション文書に継続的/ライブ検証経路が含まれています。
- **まだ保証しないこと:** この README セクション単体では、環境ごとの HA/DR 体制、
  クラウド管理サービス設定の正当性、ターゲット本番環境での運用 Runbook 実行品質までは
  保証しません。

## 目次

- [ベータ版の位置づけ](#-ベータ版の位置づけ)
- [PostgreSQL本番パスと検証ステータス](#postgresql本番パスと検証ステータス)
- [保証境界（現時点）](#保証境界現時点)
- [ランタイムポスチャ保証](#-ランタイムポスチャ保証)
- [なぜVERITASか](#-なぜveritasか)
- [できること](#-できること)
- [Quick Start](#-quick-start)
- [プロジェクト構成](#-プロジェクト構成)
- [フロントエンド — Mission Controlダッシュボード](#-フロントエンド--mission-controlダッシュボード)
- [API概要](#-api概要)
- [Docker Compose（フルスタック）](#-docker-composeフルスタック)
- [Docker（バックエンドのみ）](#-dockerバックエンドのみ)
- [アーキテクチャ（高レベル）](#-アーキテクチャ高レベル)
- [TrustLog（ハッシュチェーン監査ログ）](#-trustlogハッシュチェーン監査ログ)
- [Continuation Runtime](#-continuation-runtime)
- [テスト](#-テスト)
- [環境変数リファレンス](#-環境変数リファレンス)
- [セキュリティ注意（重要）](#-セキュリティ注意重要)
- [ロードマップ（短期）](#-ロードマップ短期)
- [ライセンス](#-ライセンス)
- [コントリビューション](#-コントリビューション)
- [引用（BibTeX）](#-引用bibtex)

---

## 📊 ベータ版の位置づけ

| 領域 | 現在のベータ版としての状態 |
|---|---|
| コア意思決定経路 | `/v1/decide` のオーケストレーション、ゲート、永続化、Replay フックまで一通り実装済みです。 |
| ガバナンス | ポリシー更新、承認フロー、監査証跡、コンプライアンス出力が中核機能として組み込まれています。 |
| フロントエンド | Mission Control は単なるデモではなく、運用者向けワークフローを意識した構成です。 |
| 安全性 | FUJI、Replay、TrustLog 周辺を含め、許容的フォールバックより fail-closed を優先する設計です。 |
| 導入想定 | 評価環境、ステージング、社内パイロット、制御されたベータ導入に適しています。本番利用には環境依存のハードニングと運用審査が必要です。 |

**ここでいう「ベータ版」とは**
- バックエンド、フロントエンド、Replay、ガバナンス、コンプライアンスまで統合された広いアーキテクチャをすでに持っている状態です。
- もはやアルファ試作ではなく、監査基盤を備えた実用寄りの段階です。
- 一方で、ポリシーパック、デプロイ既定値、環境固有の統合については継続的な改善が前提です。

## 🔒 ランタイムポスチャ保証

VERITAS OS は単一の**ランタイムポスチャ**（`VERITAS_POSTURE`）でガバナンスに重要な既定値を制御します。一度設定すれば、すべての安全フラグがそこから導出されます。

| ポスチャ | ガバナンス制御 | 起動時の動作 | エスケープハッチ |
|---|---|---|---|
| **dev**（デフォルト） | 明示的に有効化しない限りすべてOFF | 緩和 — 警告のみ | N/A |
| **staging** | 明示的に有効化しない限りすべてOFF | 緩和 — 警告のみ | N/A |
| **secure** | すべて**デフォルトON** | Fail-closed — 統合未設定時に起動拒否 | `VERITAS_POSTURE_OVERRIDE_*` 有効 |
| **prod** | すべて**ON**、例外なし | Fail-closed — 統合未設定時に起動拒否 | オーバーライドは**無視** |

### ポスチャで管理される制御

| 制御 | 環境変数（明示的オーバーライド） | 適用内容 |
|---|---|---|
| ポリシーランタイム適用 | `VERITAS_POLICY_RUNTIME_ENFORCE` | コンパイル済みポリシーのdeny/halt/escalate/require_human_review判定をパイプラインで適用 |
| 外部シークレットマネージャー | `VERITAS_ENFORCE_EXTERNAL_SECRET_MANAGER` | 起動時にVault/KMS/クラウドシークレットマネージャーを要求 |
| Transparency logアンカーリング | `VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED` | Transparencyアンカー未設定時にTrustLog書き込みを失敗させる |
| WORM hard-fail | `VERITAS_TRUSTLOG_WORM_HARD_FAIL` | WORMミラー書き込み失敗時にTrustLog書き込みを失敗させる |
| 厳密リプレイ | `VERITAS_REPLAY_STRICT` | 重大なリプレイ乖離を中止させる |
| ガバナンス成果物署名検証 | `VERITAS_POLICY_VERIFY_KEY`（+ポスチャ強制） | secure/prod で未署名または非Ed25519のガバナンスポリシーバンドルを拒否 |

### 意思決定出力に含まれるガバナンス成果物ID

コンパイル済みポリシーガバナンスが有効な場合、`/v1/decide` レスポンスには
`governance_identity` が含まれ、次の情報を返します。

- `policy_version`
- `digest`（コンパイル済みバンドルのセマンティックハッシュ）
- `signature_verified`
- `signer_id`（バンドルメタデータに `signing.key_id` がある場合）
- `verified_at`

このIDは意思決定・Replay・監査成果物に連結され、どのガバナンス制御プレーン成果物が
適用されていたかを後から証明できます。

### 起動拒否の条件（secure/prod）

以下の条件でアクション可能なエラーとともに起動を拒否します:
- `VERITAS_SECRET_PROVIDER` 未設定（外部シークレットマネージャー強制）
- `VERITAS_API_SECRET_REF` 未設定（外部シークレットマネージャー強制）
- `VERITAS_TRUSTLOG_SIGNER_BACKEND` が `aws_kms` でない、または `VERITAS_TRUSTLOG_KMS_KEY_ID` 未設定
- `VERITAS_TRUSTLOG_MIRROR_BACKEND` が `s3_object_lock` でない
- `VERITAS_TRUSTLOG_S3_BUCKET` / `VERITAS_TRUSTLOG_S3_PREFIX` 未設定（S3ミラーモード時）
- `VERITAS_TRUSTLOG_ANCHOR_BACKEND=noop` かつ `VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED=1`
- `VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH` 未設定（アンカーバックエンドが `local` かつTransparency必須時）

### エスケープハッチ（secureポスチャのみ）

`secure`ポスチャでは、本番前テスト用に個別制御を無効化できます:
```bash
VERITAS_POSTURE_OVERRIDE_POLICY_ENFORCE=0
VERITAS_POSTURE_OVERRIDE_EXTERNAL_SECRET_MGR=0
VERITAS_POSTURE_OVERRIDE_TRUSTLOG_TRANSPARENCY=0
VERITAS_POSTURE_OVERRIDE_TRUSTLOG_WORM=0
VERITAS_POSTURE_OVERRIDE_REPLAY_STRICT=0
```
これらのオーバーライドは `prod` ポスチャでは**無視されます**。

## 🎯 なぜVERITASか

### VERITAS OS が「あるもの」と「ないもの」

- **あるもの**: 実行前に配置され、ポリシー・安全・監査制御を強制するガバナンスレイヤ。
- **ないもの**: 単なるエージェント実行抽象化やオーケストレーションの便利ラッパー。

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

## 💡 できること

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

### 拡張時に重要な責務境界

以下の境界はコードとテストの両方で意識されており、拡張時に崩さないことが重要です。

| コンポーネント | 主責務 | 持ち込むべきでない責務 | 推奨拡張方向 |
|---|---|---|---|
| **Planner** | 計画構造、アクションプラン生成、Planner 向け要約 | Kernel オーケストレーション、FUJI ポリシー、Memory 永続化内部 | Planner helper / 正規化レイヤ |
| **Kernel** | 意思決定計算、スコアリング、討論の接続、根拠の組み立て | API オーケストレーション、永続化、ガバナンス保存処理 | Kernel stages / QA helper / contract |
| **FUJI** | 最終安全・ポリシー判定、拒否セマンティクス、監査向けゲート状態 | Memory 管理、Planner 分岐、汎用永続化ワークフロー | FUJI policy / safety-head / helper |
| **MemoryOS** | 保存、検索、要約、ライフサイクル、セキュリティ制御 | Planner の方針、Kernel の意思決定方針、FUJI のゲート判定 | Memory store / search / lifecycle / security helper |

この責務分離により、単一ファイルの「エージェントループ」よりも監査しやすく、進化させやすい構造になっています。

| サブシステム | 目的 |
|---|---|
| **MemoryOS** | エピソード/セマンティック/手続き/感情記憶とベクトル検索（sentence-transformers）、保持クラス、法的ホールド、PIIマスキング |
| **WorldModel** | 世界状態スナップショット、因果遷移、プロジェクトスコープ、仮想シミュレーション |
| **ValueCore** | 14次元加重（コア倫理9＋ポリシー5）の価値関数、EMAによるオンライン学習、TrustLogフィードバックからの自動リバランス。コンテキスト対応ドメインプロファイル（医療/金融/法務/安全）、ポリシー対応スコアフロア（strict/balanced/permissive）、ファクター毎の貢献度説明可能性、監査可能な重み調整証跡 |
| **FUJI Gate** | 多層安全ゲート — PII検出、有害コンテンツブロック、機微ドメインフィルタ、プロンプトインジェクション防御、紛らわしい文字検出、LLM安全ヘッド、ポリシー駆動YAMLルール |
| **TrustLog** | 追記専用ハッシュチェーン監査ログ（JSONL）、SHA-256完全性、Ed25519署名、WORM hard-failミラー、Transparency logアンカー、PII自動データ分類 |
| **Debate** | 多視点推論（賛成/反対/第三者）による透明な意思決定根拠 |
| **Critique** | 重大度ランク付きの自己批評生成と修正提案 |
| **Planner** | ステップバイステップ実行戦略を持つアクションプラン生成 |
| **Replay Engine** | 監査検証のための高再現性リプレイ（差分レポート、取得スナップショットチェックサム、モデルバージョン検証、依存バージョン追跡付き） |
| **Policy Compiler** | YAML/JSONポリシー → 中間表現 → コンパイル済みルール（Ed25519署名バンドル、ランタイム適用アダプター、テスト自動生成） |
| **Compliance** | EU AI Actコンプライアンスレポート、内部ガバナンスレポート、デプロイメント準備チェック |

---

## 📁 プロジェクト構成

```text
veritas_os/                  ← モノレポルート
├── veritas_os/              ← Pythonバックエンド（FastAPI）
│   ├── api/                 ← REST APIサーバー、スキーマ、ガバナンス
│   │   ├── server.py        ← 40以上のエンドポイントを持つFastAPIアプリ
│   │   ├── routes_decide.py ← 意思決定・リプレイ エンドポイント
│   │   ├── routes_trust.py  ← TrustLog・監査 エンドポイント
│   │   ├── routes_memory.py ← メモリCRUD エンドポイント
│   │   ├── routes_governance.py ← ガバナンス・ポリシー エンドポイント
│   │   ├── routes_system.py ← ヘルス、メトリクス、コンプライアンス、SSE、停止
│   │   ├── schemas.py       ← Pydantic v2リクエスト/レスポンスモデル
│   │   └── governance.py    ← 監査証跡付きポリシー管理
│   ├── core/                ← 意思決定エンジン
│   │   ├── kernel.py        ← 意思決定計算エンジン
│   │   ├── kernel_*.py      ← Kernel拡張（doctor、intent、QA、stages、episode、post_choice）
│   │   ├── pipeline/        ← 20以上のステージオーケストレータ（ステージモジュール群）
│   │   ├── fuji/            ← FUJI安全ゲート（パッケージ — policy、injection、safety head）
│   │   ├── memory/          ← MemoryOS（パッケージ — store、vector、search、security、compliance）
│   │   ├── continuation_runtime/ ← チェーンレベル継続観測（Phase-1）
│   │   ├── value_core.py    ← 価値整合とオンライン学習
│   │   ├── world.py         ← WorldModel（状態管理）
│   │   ├── llm_client.py    ← マルチプロバイダLLMゲートウェイ
│   │   ├── debate.py        ← 討論メカニズム
│   │   ├── critique.py      ← 批評生成
│   │   ├── planner.py       ← アクションプランニング（+ planner_helpers、planner_json、planner_normalization）
│   │   └── sanitize.py      ← PIIマスキングとコンテンツ安全性
│   ├── policy/              ← ポリシーコンパイラ、署名、ランタイムアダプター、バンドル
│   ├── logging/             ← TrustLog、データセットライター、暗号化、ローテーション
│   ├── audit/               ← 署名付き監査ログ（Ed25519）
│   ├── compliance/          ← EU AI Actレポートエンジン
│   ├── security/            ← SHA-256ハッシュ、Ed25519署名
│   ├── tools/               ← Web検索、GitHub検索、LLM安全性
│   ├── replay/              ← 決定論的リプレイエンジン
│   ├── observability/       ← OpenTelemetryメトリクス、ミドルウェア
│   ├── storage/             ← プラガブルストレージバックエンド（JSONL、PostgreSQL、Alembicマイグレーション）
│   ├── prompts/             ← LLM連携用プロンプトテンプレート
│   ├── reporting/           ← レポート生成ユーティリティ
│   ├── benchmarks/          ← パフォーマンスベンチマークデータ
│   └── tests/               ← 6600以上のPythonテスト（+ トップレベルtests/）
├── frontend/                ← Next.js 16 Mission Controlダッシュボード
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
├── config/                  ← テスト・ランタイム設定
├── scripts/                 ← アーキテクチャ・品質・セキュリティ検証スクリプト
├── docs/                    ← アーキテクチャ文書、レビュー、ユーザーマニュアル、カバレッジレポート
├── openapi.yaml             ← OpenAPI 3.x仕様
├── docker-compose.yml       ← フルスタックオーケストレーション
├── Makefile                 ← 開発/テスト/デプロイコマンド
└── pyproject.toml           ← Pythonプロジェクト設定
```

---

## 💾 ストレージバックエンド

VERITAS OS は MemoryOS と TrustLog の永続化に**プラガブルストレージバックエンド**パターンを採用しています。

| バックエンド | MemoryOS | TrustLog | デフォルト（ローカル/CLI） | デフォルト（Docker Compose） | 用途 |
|-------------|----------|----------|:-------------------:|:------------------------:|------|
| **JSON / JSONL**（ファイルベース） | `JsonMemoryStore` | `JsonlTrustLogStore` | ✅ はい | — | 単一プロセス開発、デモ、エアギャップ環境 |
| **PostgreSQL** | `PostgresMemoryStore` | `PostgresTrustLogStore` | — | ✅ はい | マルチワーカー本番、耐久監査 |

> **Docker ComposeはデフォルトでPostgreSQLを使用します。** ファイルベースバックエンドは、
> 環境変数を上書きせずに `python -m veritas_os` や `uvicorn` で実行する場合のデフォルトです。

### 環境マトリクス

| 環境 | 推奨バックエンド | 設定元 |
|------|-----------------|--------|
| ローカル開発（Docker なし） | JSON / JSONL | `.env` デフォルト |
| ローカル開発（Docker Compose） | PostgreSQL | `docker-compose.yml` デフォルト |
| ステージング | PostgreSQL | 明示的な環境変数 |
| Secure / Prod | PostgreSQL | 外部シークレットマネージャー |

### クイック切替

```bash
# PostgreSQL を両バックエンドに使用
VERITAS_MEMORY_BACKEND=postgresql
VERITAS_TRUSTLOG_BACKEND=postgresql
VERITAS_DATABASE_URL=postgresql://veritas:veritas@localhost:5432/veritas

# スキーマ適用
make db-upgrade
```

### PostgreSQL バックエンドの主な特徴

- **Alembic 管理スキーマ** — `upgrade` / `downgrade` パスを持つ再現可能なマイグレーション
- **アドバイザリロックによるチェーン直列化** — `pg_advisory_xact_lock` による並行書込み下での TrustLog ハッシュチェーン整合性保証
- **JSONB ストレージ** — GIN インデックスによるクエリ可能なペイロード
- **完全パリティテストスイート** — 195+ テストによるバックエンド間の同一セマンティクス検証
- **psycopg 3** — コネクションプーリング付きモダン非同期 PostgreSQL ドライバ（`psycopg-pool`）
- **JSONL → PostgreSQLインポート** — 冪等な `veritas-migrate` CLI（dry-run、レジューム、インポート後ハッシュチェーン検証）
- **競合テスト** — `test_pg_trustlog_contention.py` に25テスト、並行/バースト/障害シナリオでチェーン完全性を検証
- **可観測性** — `/v1/metrics` でプール使用率、ヘルス、`pg_stat_activity`（長時間クエリ、idle-in-tx、アドバイザリロック待機者）を公開。`test_pg_metrics.py` に28テスト
- **リカバリドリル** — `scripts/drill_postgres_recovery.sh` によるバックアップ → リストア → 検証の自動化。`test_drill_postgres_recovery.py` に31テスト

### 既存データの移行（JSONL → PostgreSQL）

```bash
# 1. Dry-runでソースファイルを検証
veritas-migrate trustlog --source runtime/trustlog/trust_log.jsonl --dry-run
veritas-migrate memory   --source runtime/memory/memory.json      --dry-run

# 2. インポート後ハッシュチェーン検証付きでインポート
veritas-migrate trustlog --source runtime/trustlog/trust_log.jsonl --verify
veritas-migrate memory   --source runtime/memory/memory.json

# 3. スモークテストで検証
VERITAS_MEMORY_BACKEND=postgresql VERITAS_TRUSTLOG_BACKEND=postgresql \
  pytest -m smoke veritas_os/tests/ -q
```

`veritas-migrate` CLIは**冪等**です — 部分的な障害後の再実行は、既にインポート済みのエントリをスキップして安全にレジュームします。
完全な手順（ロールバック含む）は[`docs/postgresql-production-guide.md` §11](docs/en/operations/postgresql-production-guide.md)を参照してください。

### 検証ツール

| ツール | 目的 | 実行方法 |
|--------|------|----------|
| `veritas-trustlog-verify` | スタンドアロンTrustLogチェーン完全性検証 | `veritas-trustlog-verify --log-dir <path>` |
| `veritas-migrate --verify` | インポート後ハッシュチェーンチェック（PostgreSQL） | `veritas-migrate trustlog --source … --verify` |
| `/v1/trustlog/verify` | REST APIチェーン検証 | `curl -H "X-API-Key: …" http://host:8000/v1/trustlog/verify` |
| `/v1/metrics` | プール使用率、ヘルス、pg_stat_activity | `curl -H "X-API-Key: …" http://host:8000/v1/metrics` |
| `drill_postgres_recovery.sh` | エンドツーエンド バックアップ → リストア → 検証 | `make drill-recovery` または `make drill-recovery-ci` |
| `pytest -m smoke` | ガバナンス不変条件スモークテスト | `pytest -m smoke veritas_os/tests/` |
| `pytest -m production` | 本番相当バリデーションスイート | `make test-production` |

### 本番デプロイ

[`docs/postgresql-production-guide.md`](docs/en/operations/postgresql-production-guide.md) を参照:
- プール設定、SSL/TLS、ステートメントタイムアウト
- バックアップ/リストア、レプリケーション/HAガイダンス
- JSONL → PostgreSQLインポート（`veritas-migrate` CLI: dry-run、レジューム、ロールバック、検証）
- スモークテストとリリースバリデーションの関係
- レガシーパスクリーンアップ状況
- secure/prodポスチャ推奨設定
- 競合テストカバレッジと既知の制限事項
- メトリクスリファレンス（JSONフィールド、Prometheusゲージ、解釈ガイド）
- 既知の制限事項と将来計画（pgvector、パーティショニング、CDC）

[`docs/postgresql-drill-runbook.md`](docs/en/operations/postgresql-drill-runbook.md) を参照:
- バックアップ / リストア / リカバリドリル手順とスクリプト
- TrustLog書き込みの安全 / 非安全HA境界
- インシデントレスポンスプレイブック（破損、改ざん）
- `make drill-backup`、`make drill-restore`、`make drill-recovery`、`make drill-recovery-ci`

関連: [`docs/database-migrations.md`](docs/en/operations/database-migrations.md) | [`docs/BACKEND_PARITY_COVERAGE.md`](docs/en/validation/backend-parity-coverage.md) | [`docs/legacy-path-cleanup.md`](docs/en/operations/legacy-path-cleanup.md)

---

## 🖥️ フロントエンド — Mission Controlダッシュボード

フロントエンドは **Next.js 16**（React 18、TypeScript）によるダッシュボードで、意思決定パイプラインの運用可視性を提供します。

### 技術スタック

| レイヤー | 技術 |
|---|---|
| フレームワーク | Next.js 16.2.3（App Router） |
| 言語 | TypeScript 5.7 |
| スタイリング | Tailwind CSS 3.4 + CVA（class-variance-authority） |
| アイコン | Lucide React |
| テスト | Vitest + Testing Library（ユニット）、Playwright + axe-core（E2E + アクセシビリティ） |
| i18n | カスタムReact Context（日本語デフォルト、英語対応） |
| セキュリティ | リクエスト毎ノンス付きCSP、httpOnly BFFクッキー、HSTS、X-Frame-Options |
| デザインシステム | `@veritas/design-system`（Card、Button、AppShell） |
| 共有型定義 | `@veritas/types`（ランタイム型ガード付き） |
| Lint設定 | eslint-config-next 15.5.10 |

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

## 📡 API概要

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
| GET | `/v1/governance/decisions/export` | ガバナンス監査用意思決定エクスポート |
| POST | `/v1/governance/policy-bundles/promote` | bind-boundaryガバナンスワークフローでポリシーバンドル昇格を実行（bind receipt系譜を返却。governance write権限が必要） |
| GET | `/v1/governance/bind-receipts` | bind receipt一覧（decision / execution intent 系譜 + target/outcome/reason/failed/recent/sort/limit でフィルタ可） |
| GET | `/v1/governance/bind-receipts/{bind_receipt_id}` | 単一bind receipt成果物を取得 |

> **署名付きガバナンス成果物** — secure/prodポスチャでは、ポリシーバンドルにEd25519署名が必須です。
> 意思決定成果物には、適用中のガバナンスポリシー（バージョン、ダイジェスト、署名検証結果、署名者ID）を
> 示す `governance_identity` フィールドが含まれます。
> ライフサイクル全体、鍵管理、移行ガイドは [`docs/governance_artifact_lifecycle.md`](docs/en/governance/governance-artifact-lifecycle.md) を参照してください。

### コンプライアンス & レポート

| Method | Path | 説明 |
|---|---|---|
| GET | `/v1/report/eu_ai_act/{decision_id}` | EU AI Actコンプライアンスレポート |
| GET | `/v1/report/governance` | 内部ガバナンスレポート |
| GET | `/v1/compliance/deployment-readiness` | デプロイメント前コンプライアンスチェック |
| GET | `/v1/compliance/config` | コンプライアンス設定の取得 |
| PUT | `/v1/compliance/config` | コンプライアンス設定の更新 |

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

## 🚀 Quick Start

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
pip install -e ".[full]"     # 全機能（推奨）
# pip install -e .           # コアのみ（APIサーバー + OpenAI）
# pip install -e ".[ml]"    # コア + ML ツール
```

> インストールプロファイルの詳細は [`docs/dependency-profiles.md`](docs/en/operations/dependency-profiles.md) を参照してください。

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

フロントエンドのBFFが `http://localhost:8000` 以外のバックエンドへ接続する場合は `VERITAS_API_BASE_URL` を設定してください。本番環境では `NEXT_PUBLIC_*` 系の API ベースURL変数を設定しないでください。内部ルーティング情報を露出させる恐れがあり、現在はBFFの fail-closed 動作を引き起こします。

#### Makefileショートカット

```bash
make setup         # 環境初期化
make dev           # バックエンド起動（ポート8000）
make dev-frontend  # フロントエンド起動（ポート3000）
make dev-all       # 両方起動
```

#### ローカルMac開発（Docker不要）

macOS上でDockerなしにVERITAS OSをネイティブ実行する検証済みフローです。

**1. `.env` を作成** — `.env.example` をコピーして必須値を設定:

```bash
cp .env.example .env
# .env を編集 — 最低限以下を設定:
#   OPENAI_API_KEY, VERITAS_API_KEY, VERITAS_API_SECRET, VERITAS_ENCRYPTION_KEY
```

暗号鍵の生成:

```bash
python -c "from veritas_os.logging.encryption import generate_key; print(generate_key())"
```

TrustLog WORMミラーとTransparencyログのパスをローカル開発用に追加:

```bash
# .env に追記
VERITAS_TRUSTLOG_MIRROR_BACKEND=local
VERITAS_TRUSTLOG_WORM_MIRROR_PATH=runtime/dev/logs/trustlog_worm.jsonl
VERITAS_TRUSTLOG_ANCHOR_BACKEND=local
VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH=runtime/dev/logs/trustlog_transparency.jsonl
```

**2. バックエンド起動** — `.env` をシェルに読み込んでから起動:

```bash
set -a && source .env && set +a
python -m uvicorn veritas_os.api.server:app --reload --port 8000
# または: make dev  （Makefileが自動で .env を読み込みます）
```

**3. フロントエンド起動** — 別ターミナルで:

```bash
# フロントエンドは frontend/.env.development をNext.js経由で自動読み込みします。
# frontend/.env.development の VERITAS_API_KEY がバックエンドと一致していることを確認してください。
set -a && source .env && set +a
pnpm ui:dev
```

**4. BFF認証** — フロントエンドBFFプロキシには有効な認証トークンが必要です。
`frontend/.env.development` にはdev用デフォルト値（`VERITAS_BFF_AUTH_TOKENS_JSON` と
`VERITAS_BFF_SESSION_TOKEN`）が設定済みです。ブラウザアクセスには
`http://localhost:3000/api/auth/dev-login` にアクセスして `__veritas_bff` httpOnlyクッキーを
発行し、以降の `/api/veritas/*` リクエストを認証します。

**5. 動作確認済み機能:**

| 機能 | エンドポイント / パス |
|---|---|
| 意思決定 | `POST /v1/decide` |
| SSEイベント | `GET /v1/events` |
| TrustLog保存 | decide時に自動実行 |
| WORMミラー | `VERITAS_TRUSTLOG_WORM_MIRROR_PATH` |
| Transparencyログ | `VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH` |

**6. 開発アーティファクトの場所** — デフォルト設定でのランタイムデータ出力先:

| パス | 内容 |
|---|---|
| `runtime/dev/logs/` | TrustLog JSONL、WORMミラー、Transparencyログ |
| `runtime/dev/logs/DASH/` | Shadow decide出力、データセット |
| `runtime/dev/logs/keys/` | Ed25519署名鍵（自動生成） |

> [!TIP]
> `runtime/` ディレクトリは `VERITAS_RUNTIME_NAMESPACE` または `VERITAS_ENV` マッピングにより
> 名前空間分離されます（`dev`, `test`, `demo`, `prod`）。デフォルトは `dev` です。

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

## 🐳 Docker Compose（フルスタック）

`docker-compose.yml` が3つのサービスをオーケストレーション:

| サービス | ポート | 説明 |
|---|---|---|
| `postgres` | 5432 | PostgreSQL 16（自動設定、ヘルスチェック、リソース制限付き） |
| `backend` | 8000 | FastAPIサーバー（`Dockerfile`からビルド）、ヘルスチェック付き、`postgres` に依存 |
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
| `VERITAS_API_BASE_URL` | `http://backend:8000` | フロントエンドBFF（サーバー専用）→ バックエンドURL |
| `VERITAS_MEMORY_BACKEND` | `postgresql` | メモリストレージバックエンド（`json` または `postgresql`） |
| `VERITAS_TRUSTLOG_BACKEND` | `postgresql` | TrustLogストレージバックエンド（`jsonl` または `postgresql`） |
| `VERITAS_DATABASE_URL` | `postgresql://veritas:veritas@postgres:5432/veritas` | PostgreSQL接続URL |
| `LLM_PROVIDER` | `openai` | LLMプロバイダ |
| `LLM_MODEL` | `gpt-4.1-mini` | LLMモデル名 |

---

## 🐳 Docker（バックエンドのみ）

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

## 🏗️ アーキテクチャ（高レベル）

```text
┌──────────────────────────────────────────────────────┐
│  フロントエンド (Next.js 16 / React 18 / TypeScript)  │
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
| `veritas_os/core/pipeline/` | `/v1/decide` の20以上のステージオーケストレータ — 検証から監査永続化まで（ステージモジュール群） |
| `veritas_os/core/llm_client.py` | コネクションプーリング、サーキットブレーカー、リトライ付きマルチプロバイダLLMゲートウェイ |

### 安全性とガバナンス

| モジュール | 責務 |
|---|---|
| `veritas_os/core/fuji/` | 多層**fail-closed**安全ゲート — PII、有害コンテンツ、機微ドメイン、プロンプトインジェクション、紛らわしい文字、LLM安全ヘッド、ポリシールール。全例外で `rejected` / `risk=1.0` を返却 |
| `veritas_os/core/value_core.py` | 14次元加重（コア倫理9＋ポリシー5）の価値関数、EMAによるオンライン学習、TrustLogからの自動リバランス |
| `veritas_os/api/governance.py` | ホットリロード、**4-eyes承認**（2名・重複不可）、変更コールバック、監査証跡、価値ドリフト監視、**RBAC/ABAC**アクセス制御付きポリシーCRUD |
| `veritas_os/logging/trust_log.py` | ハッシュチェーンTrustLog `h_t = SHA256(h_{t-1} ∥ r_t)` スレッドセーフ追記 |
| `veritas_os/audit/trustlog_signed.py` | Ed25519署名付きTrustLog、**WORM hard-fail**ミラー、**Transparency logアンカー**、PII自動**データ分類** |
| `veritas_os/policy/` | ポリシーコンパイラ — YAML/JSON → IR → コンパイル済みルール、Ed25519署名バンドル、ランタイム適用アダプター |

### 記憶と世界状態

| モジュール | 責務 |
|---|---|
| `veritas_os/core/memory/` | エピソード/セマンティック/手続き/感情の統合記憶、ベクトル検索（sentence-transformers、384次元）、保持クラス、法的ホールド、PIIマスキング |
| `veritas_os/core/world.py` | 世界状態スナップショット、因果遷移、プロジェクトスコープ、仮想シミュレーション |

### 推論

| モジュール | 責務 |
|---|---|
| `veritas_os/core/debate.py` | 多視点討論（賛成/反対/第三者） |
| `veritas_os/core/critique.py` | 重大度ランク付き自己批評と修正提案 |
| `veritas_os/core/planner.py` | アクションプラン生成 |

### LLMクライアント

`LLM_PROVIDER`環境変数で複数プロバイダをサポート。各プロバイダには本番準備状況を示す**サポートティア**が設定されています:

| ティア | 意味 |
|---|---|
| **production** | CIテスト済み・本番デプロイ対象・SLA範囲内 |
| **planned** | コードパスは実装済みだが本番未検証。上流API変更に追従していない場合あり |
| **experimental** | 最小限のスキャフォールド。破壊的変更の可能性あり。本番使用禁止 |

| プロバイダ | モデル | ティア |
|---|---|---|
| `openai` | GPT-4.1-mini（デフォルト） | **production** |
| `anthropic` | Claude | planned |
| `google` | Gemini | planned |
| `ollama` | ローカルモデル | experimental |
| `openrouter` | アグリゲータ | experimental |

> **ランタイム通知**: production 以外のプロバイダ使用時は `UserWarning` が発行されます。
>
> **production への昇格条件**: (1) 該当プロバイダのパスカバレッジ≥90%の結合テストスイート、(2) ステージング環境で2週間以上の成功運用、(3) 上流チェンジログとのAPI互換性レビュー、(4) プルリクエストでの明示的承認。

機能: 共有`httpx.Client`によるコネクションプーリング（`LLM_POOL_MAX_CONNECTIONS=20`）、設定可能なバックオフ付きリトライ（`LLM_MAX_RETRIES=3`）、レスポンスサイズガード（16MB）、プロバイダ単位のサーキットブレーカー、テスト用モンキーパッチ対応。

---

## 🔗 TrustLog（ハッシュチェーン監査ログ）

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

## 🔄 Continuation Runtime

VERITAS は既存のステップレベル意思決定インフラの **横に（内部ではなく）** 動作する **チェーンレベル継続観測・限定エンフォースメントレイヤー** を含みます。

### モード

| モード | 動作 | デフォルトポスチャ |
|---|---|---|
| **Observe**（Phase-1） | シャドウのみ — エンフォースメントなし、拒否ゲーティングなし | dev, staging |
| **Advisory**（Phase-2） | エンフォースメントイベントを助言として発行。ブロックなし | secure, prod |
| **Enforce**（Phase-2） | 限定エンフォースメント: 高確信条件でブロック/停止する場合あり | （環境変数でオプトイン） |

| 側面 | 状態 |
|---|---|
| FUJI | 変更なし — 各ステップの最終安全/ポリシーゲートのまま |
| `gate.decision_status` | 変更なし — 新しい値なし、再解釈なし |
| フィーチャーフラグOFF | レスポンス、ログ、UI、動作に変更なし |
| 目的 | 個々のステップが通過しても、チェーンの継続状態が弱化した場合の検知 |

### エンフォースメントアクション（Phase-2）

エンフォースメントエンジンは**高確信・説明可能な条件**でのみトリガーされます:

| 条件 | アクション | 発動条件 |
|---|---|---|
| 繰り返しの高リスク劣化 | `require_human_review` | degraded/escalated/haltedレシートが3回以上連続 |
| 承認なしの承認必須操作 | `halt_chain` | スコープがエスカレーションを要求するが承認がない |
| リプレイ乖離超過 | `escalate_alert` | センシティブパスで乖離率>0.3 |
| ポリシー境界違反 | `halt_chain` | 継続状態でポリシー違反を検知 |

### `require_human_review` と `halt_chain` の使い分け

- **`require_human_review`**: *蓄積された劣化*により発動 — 単一の重大障害ではなく、ドリフトを示唆する弱化パターン。オペレーターレビュー待ちでチェーンが一時停止。
- **`halt_chain`**: *決定論的なガバナンス障害*により発動 — 承認必須の遷移で承認が欠如、またはポリシー境界違反を検知。チェーンを即座に停止。
- **`escalate_alert`**: *リプレイ乖離*により発動 — 継続パスが予想されるリプレイ動作から乖離しており、環境または設定のドリフトを示唆。

### 設定

| 変数 | デフォルト | 説明 |
|---|---|---|
| `VERITAS_CAP_CONTINUATION_RUNTIME` | `0` | Continuation Runtimeの有効化 |
| `VERITAS_CONTINUATION_ENFORCEMENT_MODE` | `observe` | エンフォースメントモード（`observe`, `advisory`, `enforce`） |

ポスチャベースのデフォルト:
- **dev/staging**: `observe`（エンフォースメントなし）
- **secure/prod**: `advisory`（イベント発行のみ、ブロックなし）
- `VERITAS_CONTINUATION_ENFORCEMENT_MODE=enforce` で任意のポスチャで限定エンフォースメントを有効化。

### 主要概念

- **Snapshot**（状態）: 最小限のガバナンス可能な事実 — support basis、scope、burden、headroom、law version
- **Receipt**（監査証人）: 再検証の実施方法、乖離フラグ、理由コード、レシートチェーン連結
- **Enforcement Event**（監査成果物）: 全エンフォースメントアクションはログ記録され、帰属可能で、リプレイ可視かつオペレーター可視
- Snapshot は Receipt ではない。Receipt は状態ストアではない。Enforcement Eventは両方とは独立。
- 再検証はステップレベルのメリット評価の **前** に実行される（pre-merit placement）
- 継続レベルのエンフォースメントはFUJIステップレベル安全ゲーティングとは概念的に分離

### 全エンフォースメントイベントの特性:
- **ログ記録** — Python logging + trustlog-ready構造体経由
- **帰属可能** — `claim_lineage_id`, `receipt_id`, `chain_id` を保持
- **リプレイ可視** — `snapshot_id`, `receipt_id`, `law_version` を保持
- **オペレーター可視** — `action`, `reasoning`, `severity`, `conditions_met` を保持

### 設計ノート

参照: `docs/architecture/continuation_enforcement_design_note.md`

有効化: `VERITAS_CAP_CONTINUATION_RUNTIME=1`（デフォルト: OFF）

参照: `docs/architecture/continuation_runtime_adr.md`, `docs/architecture/continuation_runtime_architecture_note.md`

---

## 🧪 テスト

### バックエンド（Python）

推奨（`uv`による再現性重視）:

```bash
make test
make test-cov
```

これらのターゲットは `uv` + `PYTHON_VERSION=3.12.12` を利用し、未導入時はインタプリタを自動取得します。`make test-cov` は CI と同じカバレッジゲート（`--cov-fail-under=85`、`veritas_os/tests/.coveragerc`、XML/HTML レポート、`-m "not slow"`）で検証します。

```bash
# 任意: ローカル検証時のみ閾値/マーカーを上書き
make test-cov COVERAGE_FAIL_UNDER=0 PYTEST_MARKEXPR=""
```

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

VERITAS OS は明示的なブロッキングセマンティクスを持つ **3段階 CI/リリース検証モデル** を採用しています:

| 段階 | ワークフロー | トリガー | ブロッキング？ |
|------|----------|---------|-----------|
| **Tier 1** | `main.yml` | 全PR + `main` へのpush | ✅ マージをブロック |
| **Tier 2** | `release-gate.yml` | `v*` タグpush | ✅ リリースをブロック |
| **Tier 3** | `production-validation.yml` | 週次 + 手動 | ⚠️ アドバイザリー |

追加CIワークフロー:

| ワークフロー | トリガー | 目的 |
|------------|---------|------|
| `codeql.yml` | PR + `main` へのpush | CodeQLセキュリティ分析 |
| `publish-ghcr.yml` | リリース / タグpush | GHCRへのDockerイメージ公開 |
| `security-gates.yml` | PR + `main` へのpush | セキュリティゲートチェック（依存関係監査、シークレットスキャン） |
| `runtime-pickle-guard.yml` | PR + `main` へのpush | ランタイムpickle/joblib成果物のブロック |
| `sbom-nightly.yml` | ナイトリースケジュール | SBOM生成と脆弱性スキャン |

**Tier 1**（`main.yml`）— 以下がすべて通過するまでPRがブロックされます:
- Ruff lint + Bandit + アーキテクチャ/セキュリティスクリプトチェック
- 依存関係CVE監査（Python + Node）
- **`governance-smoke`**: 明示的高速スモークゲート（`pytest -m smoke`, 約2分）
- Python 3.11 + 3.12 マトリクスでのフルユニットテスト（85%カバレッジゲート）
- フロントエンド lint / Vitest / Playwright E2E

**Tier 2**（`release-gate.yml`）— 以下がすべて通過するまで `v*` タグがブロックされます:
- Tier 1チェックのリリース時再実行
- 本番相当テストスイート（`pytest -m "production or smoke"` + TLS + 負荷テスト）
- フルスタック Docker Compose ヘルスチェック
- ガバナンス準備レポート成果物の生成・アップロード

**Tier 3**（`production-validation.yml`）— 週次スケジュール + 手動ディスパッチ:
- 長時間実行の本番テスト、負荷テスト、外部ライブテスト
- アドバイザリー: 障害は可視だがリリースをブロックしない

完全な段階モデルは [`docs/PRODUCTION_VALIDATION.md`](docs/en/validation/production-validation.md)、
リリースプロセスは [`docs/RELEASE_PROCESS.md`](docs/en/operations/release-process.md) を参照してください。

### リリースのガバナンス準備状況の確認方法

1. [Actions タブ](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/release-gate.yml) で対象タグの `Release Gate` ワークフロー実行を確認
2. `✅ Release Readiness Gate` ジョブが **🟢 RELEASE IS GOVERNANCE-READY** を表示していること
3. `release-governance-readiness-report` 成果物をダウンロードし、`"governance_ready": true` を確認

### 本番相当バリデーション

ユニット/結合テストに加え、VERITAS は**本番相当のバリデーション**を備えており、
TrustLog、暗号化、ガバナンスAPI、Web検索セキュリティなどの実サブシステムを
本番等価のコードパスで検証します:

```bash
# 本番相当テストを実行（外部依存なし）
make test-production

# スモークテストのみ実行
make test-smoke

# Docker Composeを含む完全バリデーション（Docker必須）
make validate
```

本番バリデーションは **別CIワークフロー**（`production-validation.yml`）としても利用可能で、
手動トリガーまたは週次スケジュールで実行されます。
完全な戦略、検証マトリクス、残存する本番リスクについては
[`docs/PRODUCTION_VALIDATION.md`](docs/en/validation/production-validation.md) を参照してください。

---

## ⚙️ 環境変数リファレンス

すべての環境変数を一覧にまとめました。`.env`（gitignore対象）またはシークレットマネージャーで設定してください。

### 必須

| 変数 | 説明 | 例 |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI APIキー | `sk-...` |
| `VERITAS_API_KEY` | バックエンドAPI認証キー | ランダム文字列 |
| `VERITAS_API_SECRET` | HMAC署名シークレット（32文字以上） | ランダム64文字16進数 |
| `VERITAS_ENCRYPTION_KEY` | TrustLog暗号鍵（base64エンコード32バイト） | `generate_key()` で生成 |

### LLMプロバイダ

| 変数 | デフォルト | 説明 |
|---|---|---|
| `LLM_PROVIDER` | `openai` | LLMプロバイダ（`openai`, `anthropic`, `google`, `ollama`, `openrouter`） |
| `LLM_MODEL` | `gpt-4.1-mini` | モデル名 |
| `LLM_POOL_MAX_CONNECTIONS` | `20` | httpxコネクションプールサイズ |
| `LLM_MAX_RETRIES` | `3` | 指数バックオフ付きリトライ回数 |

### ストレージバックエンド

| 変数 | デフォルト | 説明 |
|---|---|---|
| `VERITAS_MEMORY_BACKEND` | `json`（ローカル）/ `postgresql`（Docker） | メモリストレージバックエンド（`json` または `postgresql`） |
| `VERITAS_TRUSTLOG_BACKEND` | `jsonl`（ローカル）/ `postgresql`（Docker） | TrustLogストレージバックエンド（`jsonl` または `postgresql`） |
| `VERITAS_DATABASE_URL` | — | PostgreSQL接続URL（`postgresql`バックエンド使用時に必須） |
| `VERITAS_DB_POOL_MIN_SIZE` | `2` | PostgreSQLコネクションプール最小サイズ |
| `VERITAS_DB_POOL_MAX_SIZE` | `10` | PostgreSQLコネクションプール最大サイズ |
| `VERITAS_DB_SSLMODE` | `prefer` | PostgreSQL SSLモード（`prefer`, `require`, `verify-full`） |
| `VERITAS_DB_AUTO_MIGRATE` | `false`（ローカル）/ `true`（Docker） | 起動時にAlembicマイグレーションを自動実行 |

### ネットワーク & CORS

| 変数 | デフォルト | 説明 |
|---|---|---|
| `VERITAS_CORS_ALLOW_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | CORSホワイトリスト |
| `VERITAS_API_BASE_URL` | `http://backend:8000` | フロントエンドBFF → バックエンドURL（サーバー専用） |
| `VERITAS_MAX_REQUEST_BODY_SIZE` | `10485760`（10 MB） | リクエストボディの最大サイズ |

### 安全性 & ガバナンス

| 変数 | デフォルト | 説明 |
|---|---|---|
| `VERITAS_ENABLE_DIRECT_FUJI_API` | `0` | `/v1/fuji/validate` エンドポイントの有効化 |
| `VERITAS_ENFORCE_EXTERNAL_SECRET_MANAGER` | `0`（ポスチャ: secure/prodで`1`） | Vault/KMSなしでの起動をブロック |
| `VERITAS_WEBSEARCH_ENABLE_TOXICITY_FILTER` | `1` | Web検索毒性フィルタ（fail-closed） |
| `VERITAS_CAP_CONTINUATION_RUNTIME` | `0` | Continuation Runtimeの有効化 |
| `VERITAS_CONTINUATION_ENFORCEMENT_MODE` | `observe` | Continuation Runtimeエンフォースメントモード（`observe`, `advisory`, `enforce`） |

### ポリシー署名 & 適用

| 変数 | デフォルト | 説明 |
|---|---|---|
| `VERITAS_POLICY_VERIFY_KEY` | — | ポリシーバンドル署名検証用Ed25519公開鍵PEMファイルのパス |
| `VERITAS_POLICY_RUNTIME_ENFORCE` | `0` | コンパイル済みポリシー判定（deny/halt/escalate/require_human_review）のランタイム適用を有効化 |
| `VERITAS_POLICY_REQUIRE_ED25519` | `0` | Ed25519署名検証を必須化。鍵未設定時にマニフェストを拒否 |

> **ポスチャ対応適用**: `secure`/`prod` ポスチャでは、SHA-256のみ（未署名）のポリシーバンドルは
> ランタイムアダプターにより拒否されます。Ed25519署名済みバンドルのみが検証を通過します。
> `dev`/`staging` では、SHA-256完全性チェックは警告付きで受け入れられます。
> ガバナンスロールバック操作は更新と同じ4-eyes承認・監査要件に従います。

### TrustLog & 監査

| 変数 | デフォルト | 説明 |
|---|---|---|
| `VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED` | `0`（ポスチャ: secure/prodで`1`） | Transparency logアンカーリングを必須化（fail-closed） |
| `VERITAS_TRUSTLOG_WORM_HARD_FAIL` | `0`（ポスチャ: secure/prodで`1`） | WORMミラー書込み失敗時にエラーを送出 |
| `VERITAS_TRUSTLOG_MIRROR_BACKEND` | `local` | TrustLogミラーバックエンド（`local` または `s3_object_lock`） |
| `VERITAS_TRUSTLOG_WORM_MIRROR_PATH` | — | ローカル追記ミラー先パス（バックエンドが `local` の場合） |
| `VERITAS_TRUSTLOG_S3_BUCKET` | — | TrustLogミラー書込み用S3バケット名（`s3_object_lock` バックエンド） |
| `VERITAS_TRUSTLOG_S3_PREFIX` | — | 追記専用TrustLogオブジェクトのS3キープレフィックス |
| `VERITAS_TRUSTLOG_S3_REGION` | — | S3クライアント用AWSリージョンオーバーライド |
| `VERITAS_TRUSTLOG_S3_OBJECT_LOCK_MODE` | — | Object Lockモード（`GOVERNANCE` または `COMPLIANCE`） |
| `VERITAS_TRUSTLOG_S3_RETENTION_DAYS` | — | S3 Object Lockの保持期間（日数） |
| `VERITAS_TRUSTLOG_VERIFY_MIRROR_REMOTE` | `0` | TrustLog検証時のリモートS3ミラー検証を有効化 |
| `VERITAS_TRUSTLOG_VERIFY_MIRROR_S3_STRICT` | `0` | 厳密ミラー検証: 欠損レシートと保持ギャップで失敗 |
| `VERITAS_TRUSTLOG_VERIFY_MIRROR_S3_REQUIRE_LEGAL_HOLD` | `0` | リモートミラー検証時にS3 Object Legal Hold（`ON`）を必須化 |
| `VERITAS_TRUSTLOG_ANCHOR_BACKEND` | `local` | TrustLogアンカーバックエンド（`local` または `noop`） |
| `VERITAS_TRUSTLOG_TRANSPARENCY_LOG_PATH` | — | ローカルTransparencyアンカーパス（アンカーバックエンドが `local` かつTransparency必須時に必須） |
| `VERITAS_TRUSTLOG_SIGNER_BACKEND` | `file` | TrustLog署名バックエンド（`file` または `aws_kms`） |
| `VERITAS_TRUSTLOG_KMS_KEY_ID` | — | AWS KMSキーID/ARN（`VERITAS_TRUSTLOG_SIGNER_BACKEND=aws_kms` 時に必須） |

#### TrustLogミラー移行ノート

- 既存デプロイは変更なしで動作します。`VERITAS_TRUSTLOG_MIRROR_BACKEND` はデフォルト `local` で、`VERITAS_TRUSTLOG_WORM_MIRROR_PATH` の動作を維持します。
- S3 Object Lockに移行するには、`VERITAS_TRUSTLOG_MIRROR_BACKEND=s3_object_lock` を設定し、最低限 `VERITAS_TRUSTLOG_S3_BUCKET`（任意でprefix/region/retention設定）を指定してください。
- `VERITAS_TRUSTLOG_WORM_HARD_FAIL` のセマンティクスは変更なく、両バックエンドに適用されます。
- `secure`/`prod` では、起動時バリデーションが `VERITAS_TRUSTLOG_MIRROR_BACKEND=s3_object_lock` と `VERITAS_TRUSTLOG_S3_BUCKET` / `VERITAS_TRUSTLOG_S3_PREFIX` の両方を要求します。

#### TrustLogミラー検証モード

- **オフラインモード（デフォルト）**: `VERITAS_TRUSTLOG_VERIFY_MIRROR_REMOTE=0` はレシートスキーマのみ検証し、レガシー互換性を維持。
- **リモートモード**: `VERITAS_TRUSTLOG_VERIFY_MIRROR_REMOTE=1` は `s3_object_lock` レシートに対してS3ベースのチェックを実行:
  - オブジェクト存在確認（`Bucket` + `Key`）
  - `version_id` 一致（レシートに `version_id` がある場合）
  - `etag` 一致（レシートに `etag` がある場合）
  - 保持状態（レシートが保持メタデータを記録している場合）
- **厳密モード**: `VERITAS_TRUSTLOG_VERIFY_MIRROR_S3_STRICT=1` は高保証/本番検証ジョブ向け:
  - ミラーレシート欠損エントリで失敗（`mirror_receipt_missing`）
  - 保持検証ギャップで失敗（`mirror_retention_missing`）
  - レシートサポート以前に作成された古いレジャーでは検証が中断する可能性あり。
- **Legal hold強制**: `VERITAS_TRUSTLOG_VERIFY_MIRROR_S3_REQUIRE_LEGAL_HOLD=1` は追加でオブジェクトlegal holdが `ON` であることを要求（`mirror_legal_hold_missing`）。

> セキュリティ注意: リモート検証はライブAWS APIアクセスとIAMパーミッション（`s3:HeadObject`, `s3:GetObjectRetention`, `s3:GetObjectLegalHold`）に依存します。最小権限を使用し、検証者の認証情報を分離してください。

### Replay

| 変数 | デフォルト | 説明 |
|---|---|---|
| `VERITAS_REPLAY_STRICT` | `0` | 決定論的リプレイ設定の強制 |
| `VERITAS_REPLAY_REQUIRE_MODEL_VERSION` | `1` | model_versionなしのスナップショットを拒否 |

### ランタイム

| 変数 | デフォルト | 説明 |
|---|---|---|
| `VERITAS_POSTURE` | `dev` | ランタイムポスチャ（`dev`/`staging`/`secure`/`prod`）。[ランタイムポスチャ保証](#-ランタイムポスチャ保証)を参照。 |
| `VERITAS_RUNTIME_ROOT` | `runtime/` | ランタイムデータのルートディレクトリ |
| `VERITAS_RUNTIME_NAMESPACE` | `dev` | ランタイム名前空間（`dev`/`test`/`demo`/`prod`） |

> 完全なテンプレートは [`.env.example`](.env.example) を参照してください。

---

## 🔐 セキュリティ注意（重要）

> [!WARNING]
> VERITAS は fail-closed を前提に設計されていますが、**安全な既定値があること** と **設定なしで安全に運用できること** は同義ではありません。ベータ導入前に、シークレット管理、暗号鍵、WORM / Transparency 設定、公開ネットワーク露出を必ず確認してください。

**ベータ運用で特に重要な警告**
- `VERITAS_API_SECRET=change-me` のような既定値のままバックエンドを公開しないでください。
- TrustLog 暗号化は secure-by-default を前提としており、`VERITAS_ENCRYPTION_KEY` 未設定時は意図的に書き込み失敗になります。
- MemoryOS の legacy pickle 移行は一時的な移行専用経路として扱ってください。デシリアライズ経路は高リスクです。
- BFF / サーバールーティングは慎重に運用してください。`NEXT_PUBLIC_*` で内部 API 構成を漏らすと、想定している境界が弱くなります。

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
- **運用ログはGit管理対象外**: ランタイムログ（例: `runtime/<namespace>/.../*.jsonl`）は `.gitignore` で除外されます。匿名化サンプルは `veritas_os/sample_data/memory/` 配下にあります。
- **ランタイム名前空間は用途別に分離**: デフォルトのローカルパスは `runtime/dev`、`runtime/test`、`runtime/demo`、`runtime/prod` です。`VERITAS_RUNTIME_ROOT` と `VERITAS_RUNTIME_NAMESPACE` で上書き可能です。
- **クリーンクローン用クリーンアップコマンド**: `python scripts/reset_repo_runtime.py --dry-run` と `python scripts/reset_repo_runtime.py --apply` で生成されたランタイムデータを削除できます。詳細は `docs/ja/operations/runtime-data-policy.md` を参照してください。

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

## 🗺️ ロードマップ（短期）

**実装済み**（以前ロードマップに記載されていた項目）:
- ✅ CI（GitHub Actions）: 3段階バリデーションモデル（pytest + coverage + artifactレポート）
- ✅ セキュリティ強化: 入力検証、秘密情報/ログ衛生、ランタイムポスチャシステム
- ✅ Policy-as-Code: YAML/JSON → IR → コンパイル済みルール（Ed25519署名バンドル、テスト自動生成）
- ✅ マルチプロバイダLLM: OpenAI（production）、Anthropic/Google（planned）、Ollama/OpenRouter（experimental）
- ✅ PostgreSQLストレージバックエンド: MemoryOS・TrustLog用プラガブルバックエンド（Alembicマイグレーション、アドバイザリロックチェーン直列化、195+パリティテスト）。JSONL → PostgreSQLインポート手順、スモーク/リリースバリデーション統合、レガシーパスクリーンアップ含む。[`docs/postgresql-production-guide.md`](docs/en/operations/postgresql-production-guide.md) 参照。
- ✅ PostgreSQL本番ハードニング: 競合テスト（25テスト）、プール/アクティビティメトリクス（28テスト）、バックアップ/リストア/リカバリドリルスクリプトとテスト（31テスト）。[`docs/postgresql-drill-runbook.md`](docs/en/operations/postgresql-drill-runbook.md) 参照。
- ✅ Continuation Runtime（Phase-1）: チェーンレベル継続観測レイヤー、スナップショット/レシート/エンフォースメントイベントアーキテクチャ。`docs/architecture/continuation_runtime_adr.md` 参照。
- ✅ ガバナンス成果物署名: Ed25519署名ポリシーバンドル、ランタイム署名検証、意思決定出力へのガバナンスID。[`docs/governance_artifact_lifecycle.md`](docs/en/governance/governance-artifact-lifecycle.md) 参照。
- ✅ S3 Object Lock TrustLogミラー: WORM準拠ミラーバックエンド（保持、legal hold、リモート検証）。[`docs/postgresql-drill-runbook.md`](docs/en/operations/postgresql-drill-runbook.md) 参照。

**今後のマイルストーン**:
- Anthropic / Google LLMプロバイダのproductionティア昇格
- CI成果物からのカバレッジバッジ自動更新
- pgvector統合によるMemoryOSベクトル類似度検索
- モノレポライセンス（Plan B）からマルチレポ分離（Plan A）への段階的移行
- Continuation Runtime Phase-2 エンフォースメントのsecure/prodポスチャでのデフォルト有効化

---

## 📄 ライセンス

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

現在の構造は、既存方針をより明確な二層モデルとして明文化したものです。

- Coreは既定でプロプライエタリのまま
- インターフェース資産はディレクトリ単位で明示的にオープンライセンス化
- Coreロジック（Planner/Kernel/FUJI/TrustLogパイプライン内部）はオープンソース化されていません

### ライセンス分離ロードマップ（Plan B モノレポ → Plan A マルチレポ）

Phase 1（現行）:
- モノレポ内でのディレクトリスコープライセンス（Core proprietary + interface MIT）

Phase 2（今後）:
- `veritas-spec`（OpenAPI/schema）
- `veritas-sdk-python`, `veritas-sdk-js`
- `veritas-cli`
- `veritas-policy-templates`
- `veritas_os` は proprietary Core に集中

学術用途では Zenodo DOI を引用してください。

---

## 🤝 コントリビューション

コントリビューションを歓迎します！ ガイドラインは [`CONTRIBUTING.md`](CONTRIBUTING.md) をご覧ください：

- リポジトリのライセンスモデル（Coreはプロプライエタリ、インターフェースはMIT）
- 開発環境セットアップとコーディング規約
- プルリクエストのワークフローとレビュープロセス
- セキュリティ脆弱性の報告は [`SECURITY.md`](SECURITY.md) を参照

---

## 📝 引用（BibTeX）

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

## 📞 連絡先

- Issues: [https://github.com/veritasfuji-japan/veritas_os/issues](https://github.com/veritasfuji-japan/veritas_os/issues)
- Email: [veritas.fuji@gmail.com](mailto:veritas.fuji@gmail.com)
