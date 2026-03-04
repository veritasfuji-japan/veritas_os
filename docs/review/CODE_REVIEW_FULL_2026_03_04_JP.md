# VERITAS OS 全コードレビュー報告書

**日付**: 2026-03-04
**対象**: 全コードベース (466ファイル / 136,103行)
**レビュー範囲**: バックエンド (Python) / フロントエンド (TypeScript/Next.js) / インフラ・設定 / テスト品質

---

## 目次

1. [総合評価](#1-総合評価)
2. [CRITICAL: セキュリティ問題](#2-critical-セキュリティ問題)
3. [HIGH: バグ・競合状態](#3-high-バグ競合状態)
4. [MEDIUM: コード品質・設計問題](#4-medium-コード品質設計問題)
5. [LOW: 改善提案](#5-low-改善提案)
6. [フロントエンド固有の問題](#6-フロントエンド固有の問題)
7. [インフラ・設定の問題](#7-インフラ設定の問題)
8. [テスト品質評価](#8-テスト品質評価)
9. [良い点（維持すべき設計）](#9-良い点維持すべき設計)
10. [対応優先度マトリクス](#10-対応優先度マトリクス)

---

## 1. 総合評価

| カテゴリ | 評価 | コメント |
|----------|------|----------|
| **セキュリティ** | ⭐⭐⭐⭐ | APIキー管理・CORS・CSP が堅牢。SSRF対策とnonce TTL が不足 |
| **バックエンド品質** | ⭐⭐⭐ | 広範な `except Exception:` と import 時副作用が課題 |
| **フロントエンド品質** | ⭐⭐⭐⭐ | 型安全性・a11y が良好。PDF生成のXSSリスクあり |
| **テストカバレッジ** | ⭐⭐⭐ | trust_log/atomic_io は優秀。kernel.decide は深刻に不足 |
| **インフラ・CI/CD** | ⭐⭐⭐⭐ | gitleaks・pip-audit・bandit が統合済。Docker 設計も良好 |
| **アーキテクチャ** | ⭐⭐⭐ | モジュール分離は適切。循環依存とモノリシックページが課題 |

---

## 2. CRITICAL: セキュリティ問題

### S-1: API Secret バリデーションがインポート時に実行される

**ファイル**: `veritas_os/core/config.py:443-445`

```python
cfg = VeritasConfig()
if cfg.should_enforce_api_secret_validation():
    cfg.validate_api_secret_non_empty()
```

**問題**: モジュールインポート時に副作用が発生。テスト環境でバイパス可能で、本番環境にリークするリスクあり。

**対策**: `server.py` の起動時に明示的に `validate_config()` を呼ぶ方式に変更する。

---

### S-2: Double-Checked Locking の安全性不足

**ファイル**: `veritas_os/api/server.py:332-362`

```python
def get_cfg() -> Any:
    global _cfg_state
    if _cfg_state.obj is not None:  # ロックなしの第1チェック
        return _cfg_state.obj
    with _cfg_state.lock:
        if _cfg_state.obj is not None:
            return _cfg_state.obj
        # ... 初期化 ...
```

**問題**: ロック外の第1チェックがスレッドセーフでない。複数スレッドが同時にロックブロックに入る可能性がある。

**対策**: 常にロックを取得してからチェックする、またはモジュールレベルで一度だけ初期化する。

---

### S-3: SSRF脆弱性 — URL検証の不備

**ファイル**: `veritas_os/tools/web_search.py:60-94`

**問題**: URLの `scheme` と `hostname` の存在のみチェック。プライベートIPアドレス (127.0.0.1, 192.168.*, 10.*, 172.16-31.*) やリザーブドポート (25, 22等) をブロックしていない。

**対策**:
```python
import ipaddress
def _is_private_ip(hostname: str) -> bool:
    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False
```

---

### S-4: フロントエンドAPIプロキシのパス検証

**ファイル**: `frontend/app/api/veritas/[...path]/route.ts:3-4, 59`

**問題**: パス検証が文字列前方一致のため、パストラバーサル (`/v1/decide/../../../admin`) に脆弱な可能性がある。APIキーが空文字列にデフォルトされるため、設定ミスで未認証リクエストが通過する。

**対策**: 完全一致のパスホワイトリストを使用。リクエストボディサイズ制限とレート制限を追加。

---

### S-5: PDF生成におけるXSSリスク

**ファイル**: `frontend/app/audit/page.tsx:351-451`

**問題**: `generatePdfReport()` が `window.open()` で新しいウィンドウを作成しHTMLを直接書き込む。レポートデータがユーザー制御下にあるため、悪意あるHTML/スクリプトが実行される可能性がある。

**対策**: `jsPDF` や `html2pdf` ライブラリに置き換える。

---

## 3. HIGH: バグ・競合状態

### R-1: Trust Log ローテーションのTOCTOU競合

**ファイル**: `veritas_os/logging/rotate.py:139-159`

**問題**: `is_symlink()` チェックと `unlink()` の間にシンボリックリンク差し替え攻撃が可能。コメントで認識されているが未修正。

**対策**: アトミックな操作に置き換える。

---

### R-2: 40件以上の過度に広い例外ハンドラ

**ファイル**: `veritas_os/core/pipeline.py` (104-112行 他多数)

```python
except Exception:  # SystemExit, KeyboardInterrupt も捕捉してしまう
    _atomic_write_json = None
```

**問題**: パイプライン全体で40箇所以上の `except Exception:` が存在。本来のエラーが黙殺され、デバッグが困難。

**対策**: 具体的な例外型 (`ImportError`, `ModuleNotFoundError` 等) に置き換え。全ハンドラにログを追加。

---

### R-3: Nonceの有効期限・リプレイ保護がない

**ファイル**: `veritas_os/api/server.py:990-1070`

**問題**: `secrets.token_hex(16)` でnonce生成は暗号学的に安全だが、TTL検証がない。nonceが無期限に有効でリプレイ攻撃が可能。

**対策**: nonce TTL (5分) とリプレイ保護を実装。

---

### R-4: Pydantic スキーマのリスト長制限が未適用

**ファイル**: `veritas_os/api/schemas.py:26`

```python
MAX_LIST_ITEMS = 100  # 定義済みだが、リクエスト検証で使われていない
```

**問題**: 攻撃者が100万件のalternatives/evidence/critiqueを送信可能。

**対策**: `Field(..., max_length=MAX_LIST_ITEMS)` をPydanticモデルに適用。

---

## 4. MEDIUM: コード品質・設計問題

### A-1: 循環依存とモジュール結合

**ファイル**: `veritas_os/api/server.py:34-57`

**問題**: 23以上のインポートがサーバ起動時に実行。どれか1つでも壊れるとサーバ全体が起動不能。

**対策**: オプショナル機能には遅延インポートを使用。クリティカルパスと分離する。

---

### A-2: 型アノテーションの不統一

**問題**: `Optional[X]` (Python 3.9) / `X | None` (Python 3.10+) / `Union[X, None]` が混在。

**対策**: `X | None` (Python 3.10+) に統一。`mypy --strict` をCIに追加。

---

### A-3: Lazy Import パターンの不統一

**ファイル**: `veritas_os/core/__init__.py:48-63`

**問題**: `__getattr__` と `try_import_experiments()` で異なるセマンティクス。キャッシュ・エラーハンドリングの挙動が不一致。

**対策**: 統一的な遅延インポートユーティリティを作成。

---

### A-4: PII サニタイゼーションのリソース制限

**ファイル**: `veritas_os/core/sanitize.py:437-440, 546-600`

**問題**: 入力1MBまで、PIIマッチ1万件まで許容。正規表現にタイムアウトがなく、ReDoS攻撃でハングする可能性。

**対策**: 正規表現処理にタイムアウトを設定。入力サイズ制限の見直し。

---

### A-5: Atomic Write でのブロッキングI/O

**ファイル**: `veritas_os/core/atomic_io.py:46-56`

**問題**: `os.write()` のブロッキング呼び出しがFastAPIイベントループを停止させる可能性。データスライスが毎回新しいオブジェクトを生成。

**対策**: `memoryview` を使用してコピーを回避。

---

## 5. LOW: 改善提案

### L-1: 廃止フィールドの計画的削除

**ファイル**: `veritas_os/api/schemas.py:344`

**問題**: `options` フィールドが非推奨だが削除予定なし。

**対策**: 廃止タイムライン (例: v2.0) を設定。

---

### L-2: エラーレスポンスでの内部情報漏洩

**ファイル**: `veritas_os/core/pipeline.py:1379-1391`

```python
return {"ok": False, "error": str(e)}  # 内部パスやDB接続文字列が含まれうる
```

**対策**: ジェネリックなエラーコードを返す (`"decision_processing_failed"`)。

---

### L-3: カーネル制約チェックの可読性

**ファイル**: `veritas_os/core/kernel.py:95-104`

**問題**: 早期リターンと条件分岐が混在し、制御フローが読みにくい。

**対策**: ヘルパ関数 `_has_seccomp()` / `_has_apparmor()` に分離。

---

## 6. フロントエンド固有の問題

### F-1: useDecide の競合状態

**ファイル**: `frontend/features/console/api/useDecide.ts:61-68`

**問題**: リクエストシーケンスの単調カウンターに依存するが、高速連続送信時に古いリクエストの状態更新が新しいものを上書きする可能性。

**対策**: AbortController の signal を使用。マウントフラグを追加。

---

### F-2: DANGER_PRESETS がプロダクションバンドルに含まれる

**ファイル**: `frontend/features/console/constants.ts:11-24`

**問題**: 開発フラグで制御されるが、バンドルには含まれたまま。

**対策**: webpackプラグインでプロダクションビルド時に除去。

---

### F-3: Error Boundary の欠如

**ファイル**: `frontend/app/console/page.tsx`

**問題**: `<ChatPanel>`, `<PipelineVisualizer>`, `<ResultSection>` 等にError Boundaryがない。子コンポーネントのクラッシュでページ全体が落ちる。

**対策**: 各フィーチャーパネルをErrorBoundaryでラップ。

---

### F-4: Governance ページのモノリシック設計

**ファイル**: `frontend/app/governance/page.tsx` (745行)

**問題**: 状態管理 (7つのuseState)、データフェッチ、バリデーション、フォームUI、差分プレビューが1ファイルに集中。

**対策**: `PolicyFetcher`, `PolicyEditor`, `DiffViewer`, `ValidationErrors` 等に分割。

---

### F-5: localStorage の同意なし利用

**ファイル**: `frontend/components/i18n-provider.tsx:29-36`

**問題**: 言語設定をlocalStorageに保存しているがユーザー同意を取得していない。EU規制に抵触する可能性。

---

## 7. インフラ・設定の問題

### I-1: start_server.sh にハードコードされたテストパス

**ファイル**: `veritas_os/scripts/start_server.sh:17`

```bash
cd "$HOME/veritas_clean_test2"  # ← 本番では動作しない
```

**対策**: 環境変数 `$REPO_ROOT` から読み取る方式に変更。

---

### I-2: Slack Webhook URLのログ出力

**ファイル**: `veritas_os/scripts/doctor.sh:110-111`, `veritas_os/scripts/sync_to_drive.sh:73-78`

**問題**: `SLACK_WEBHOOK_URL` が平文でログに出力される。

**対策**: 機密環境変数をマスク表示 (`*****`) に。

---

### I-3: OpenAPI仕様にレート制限のドキュメントがない

**ファイル**: `openapi.yaml:10-14`

**問題**: `ApiKeyAuth` のみ定義。スコープ、レート制限、タイムアウト等が未記載。

---

### I-4: Docker Compose のシークレット管理

**ファイル**: `docker-compose.yml:10`

**問題**: 環境変数の補間に依存。`.env` ファイルが欠如するとデフォルト値で動作。

**対策**: Docker secrets または外部シークレット管理を検討。

---

## 8. テスト品質評価

### 8.1 カテゴリ別評価

| テスト対象 | 評価 | テスト数 | リスク |
|-----------|------|---------|--------|
| **Trust Log (データ永続化)** | ⭐⭐⭐⭐⭐ | 20+ | LOW |
| **Atomic I/O** | ⭐⭐⭐⭐⭐ | 23 | LOW |
| **Thread Safety** | ⭐⭐⭐⭐⭐ | 10+ | LOW |
| **LLM Client** | ⭐⭐⭐⭐ | 47 | LOW |
| **Decision Status** | ⭐⭐⭐⭐ | 10+ | LOW |
| **Governance API** | ⭐⭐⭐ | 12 | MEDIUM |
| **Memory Core** | ⭐⭐⭐ | < 10 | MEDIUM |
| **Kernel (decide)** | ⭐⭐ | **3** | **HIGH** |
| **API Decide** | ⭐ | **1** | **CRITICAL** |

### 8.2 重大なテスト不足

#### kernel.decide() — 3テストのみ、全依存をモック

**ファイル**: `veritas_os/tests/test_kernel.py:22-62`

```python
# すべての依存関係をモックしており、実際の振る舞いをテストしていない
monkeypatch.setattr(kernel.world_model, "inject_state_into_context", lambda ...: dict(context))
monkeypatch.setattr(kernel.mem_core, "summarize_for_planner", lambda ...: "summary")
monkeypatch.setattr(kernel.planner_core, "plan_for_veritas_agi", lambda ...: {"steps": [...]})
```

**推奨**: 半実データを使った統合テスト25件以上を追加。

#### API /v1/decide — 1テストのみ、HTTP 200のみ確認

**ファイル**: `veritas_os/tests/test_api_decide.py:7-34`

```python
assert res.status_code == 200  # 唯一のアサーション
assert "chosen" in data  # フィールド存在確認のみ、値の正確性は未検証
```

**推奨**: 異常系・バリデーション・レート制限を含む30件以上のテストを追加。

### 8.3 "Coverage Boost" パターンへの懸念

**ファイル**: `veritas_os/tests/test_coverage_boost.py` (133テスト)

**問題**: カバレッジ指標向上が目的で、アサーションが曖昧 (`> 0` 等)。偽の安心感を生む。

**推奨**: 具体的な期待値でアサーション。メトリクスではなく振る舞いに焦点。

---

## 9. 良い点（維持すべき設計）

### セキュリティ
- `secrets.compare_digest()` によるタイミングセーフな比較 (server.py:857)
- IP ベースのレート制限 (10回/60秒) (server.py:712-836)
- 包括的なHTTPセキュリティヘッダ (HSTS, CSP, X-Frame-Options等) (server.py:670-699)
- 安全なCORS設定 (`*` + credentials の禁止) (server.py:521-568)
- リクエストボディサイズ制限 (dev: 10MB, prod: 5MB) (server.py:583-667)
- gitleaks プリコミットフック (.pre-commit-config.yaml)
- pip-audit / pnpm audit のCI統合 (security-gates.yml)
- bandit セキュリティスキャナ (main.yml:46-51)
- NEXT_PUBLIC_* シークレット露出チェック (scripts/security/)

### フロントエンド
- Nonce ベースのCSP (middleware.ts)
- 包括的なランタイムバリデータ (api-validators.ts)
- スキップリンク、ARIA属性、aria-live の適切な使用
- TypeScript strict mode

### インフラ
- マルチステージDockerビルド、非rootユーザ実行
- 環境変数でのシークレット生成 (`secrets.token_urlsafe(48)`)
- ピン留めされた依存バージョン (requirements.txt)
- カバレッジ要件 85% (main.yml:73)

### テスト
- Trust Log のチェーン整合性テスト
- Atomic I/O の原子性保証テスト (障害時の元データ保全)
- スレッドセーフティの並行テスト
- LLMクライアントのリトライロジックテスト

---

## 10. 対応優先度マトリクス

### 今週中（CRITICAL/HIGH）

| # | 問題 | ファイル | 行 |
|---|------|---------|-----|
| 1 | `except Exception:` を具体的な例外型に置換 | pipeline.py | 104+ (40箇所) |
| 2 | Double-checked locking の修正 | server.py | 332-362 |
| 3 | Config validation をインポート時から起動時に移動 | config.py | 443-445 |
| 4 | Pydantic スキーマにリスト長制限を適用 | schemas.py | 26, 87-99 |
| 5 | APIプロキシのパス検証を完全一致に変更 | route.ts | 全体 |
| 6 | kernel.decide() のテスト追加 (25件+) | test_kernel.py | 全体 |
| 7 | API /v1/decide のテスト追加 (30件+) | test_api_decide.py | 全体 |

### 今月中（MEDIUM）

| # | 問題 | ファイル |
|---|------|---------|
| 8 | SSRF対策 (プライベートIP検証) | web_search.py:60-94 |
| 9 | Nonce TTL とリプレイ保護 | server.py:990-1070 |
| 10 | フロントエンドの Error Boundary 追加 | console/page.tsx |
| 11 | Governance ページのコンポーネント分割 | governance/page.tsx |
| 12 | PDF生成のXSS対策 | audit/page.tsx:351-451 |
| 13 | start_server.sh のハードコードパス除去 | start_server.sh:17 |
| 14 | Slack Webhook URLのマスク処理 | doctor.sh, sync_to_drive.sh |

### 来四半期（LOW）

| # | 問題 |
|---|------|
| 15 | 型アノテーションの統一 |
| 16 | 統一的遅延インポートユーティリティの作成 |
| 17 | PII正規表現のタイムアウト追加 |
| 18 | DANGER_PRESETS のバンドル除外 |
| 19 | OpenAPI仕様のレート制限ドキュメント追加 |
| 20 | "Coverage Boost" テストの品質改善 |

---

*レビュー実施: Claude Code (Opus 4.6)*
*レビュー対象: 466ファイル / 136,103行 (Python 80+ファイル, TypeScript 65+ファイル, テスト 144ファイル)*
