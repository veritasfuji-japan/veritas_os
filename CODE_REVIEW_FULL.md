# VERITAS OS v2.0 — 全コードレビュー報告書

**日付**: 2026-02-08
**対象**: veritas_os/ 全ソースコード（160ファイル、~20,000行）
**レビュアー**: Claude Code Review

---

## 総合評価

| カテゴリ | 評価 | コメント |
|---------|------|---------|
| **アーキテクチャ** | B+ | レイヤ分離が明確。lazy import パターンで堅牢性を確保 |
| **セキュリティ** | B+ | HMAC認証、PII マスク、レート制限、非root Docker 実装済み |
| **信頼性** | B | atomic I/O・hash-chain TrustLog は優秀。一部 graceful degradation が過度 |
| **テスト** | B | 140+ テストファイル。カバレッジ目標 40% は低い |
| **保守性** | B- | pipeline.py が 122KB と巨大。一部モジュールの責務が不明確 |
| **パフォーマンス** | B- | メモリ内コサイン検索は小規模向き。大規模データでの課題あり |

---

## 1. アーキテクチャ

### 良い点

- **レイヤ分離**: API → Core Engine → Services（Memory, Logging, LLM）の3層構造が明確
- **Lazy Import パターン** (`server.py:226-388`): 依存モジュールが壊れても `/health` は必ず200を返す設計。プロダクション向きの堅牢性
- **Pipeline パターン**: Options → Evidence → Critique → Debate → Planner → ValueCore → FUJI → TrustLog の決定フロー
- **型定義** (`core/types.py`): TypedDict + Protocol による構造的部分型。IDE補完と型安全性を両立
- **設定の外部化** (`core/config.py`): 環境変数による全設定の上書きに対応。マジックナンバーを排除

### 問題点

#### [CRITICAL] pipeline.py が 122KB — 分割が必要

`veritas_os/core/pipeline.py` は単一ファイルで 122KB（推定3000行以上）。これは保守性とレビュー可能性を大きく損なう。

**推奨**: ステージごとにファイルを分割（`pipeline_options.py`, `pipeline_evidence.py`, `pipeline_fuji.py` 等）

#### [HIGH] kernel.py と pipeline.py の責務重複

`kernel.py` (41KB) と `pipeline.py` (122KB) の両方が decision pipeline を実装している。`kernel.py:408` の `decide()` と `pipeline.py` の `run_decide_pipeline()` が並行して存在し、呼び出し関係が複雑。

**推奨**: kernel.py を薄いファサードに絞り、ロジックは pipeline.py に統合するか、明確な委譲関係を文書化

#### [MEDIUM] core/memory.py (66KB) と memory/ パッケージの二重構造

`core/memory.py` がフロントエンドAPI、`memory/` パッケージがバックエンドだが、66KB の memory.py は大きすぎる。

---

## 2. セキュリティ

### 良い点

- **APIキー管理** (`server.py:469-500`): `secrets.compare_digest()` によるタイミング攻撃耐性。環境変数からの毎回取得でメモリダンプ対策
- **HMAC署名** (`server.py:601-633`): タイムスタンプ + nonce + ボディのHMAC署名でリプレイ攻撃を防止
- **レート制限** (`server.py:636-690`): スレッドセーフなIPベースレート制限
- **PII マスキング** (`core/sanitize.py`): メール、電話、住所、マイナンバー、クレジットカード（Luhn検証付き）等の包括的な検出・マスク
- **セキュリティヘッダー** (`server.py:442-450`): `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`, `Cache-Control`
- **Docker 非root実行** (`Dockerfile:15-17`): `appuser` による権限最小化
- **Prompt Injection 検出** (`fuji.py:138-175`): 正規表現ベースのインジェクションパターン検出
- **Pickle セキュリティ** (`index_cosine.py:23-47`): デフォルトで `allow_pickle=False`。レガシー互換は環境変数で明示的に有効化が必要
- **パストラバーサル防止** (`dashboard_server.py:93-135`): `VERITAS_LOG_DIR` の検証でベースディレクトリ外へのアクセスをブロック
- **ボディサイズ制限** (`server.py:410-437`): 10MB上限のDoS対策ミドルウェア

### 問題点

#### [HIGH] nonce ストアがインメモリ — マルチプロセス環境で無効

`server.py:508` の `_nonce_store` は dict で実装されている。uvicorn のワーカー数が2以上の場合、ワーカー間で nonce が共有されないためリプレイ攻撃が可能。

```python
_nonce_store: Dict[str, float] = {}  # server.py:508
```

**推奨**: Redis 等の外部ストアを使用するか、単一ワーカー運用を明示的に制約として文書化

#### [HIGH] レート制限がインメモリ — 同上

`server.py:641` の `_rate_bucket` も同じ問題を抱えている。

#### [MEDIUM] CORS 設定で `*` を除外しているが、空リストはオープンと同じ

```python
# config.py:27
return [value for value in values if value != "*"]
```

`VERITAS_CORS_ALLOW_ORIGINS` が空の場合、`allow_origins=[]` となり CORS は事実上無効（全オリジン拒否）。これは意図的だが、設定ミスで API が使えなくなるリスクがある。

**推奨**: デフォルト値のドキュメント化を強化

#### [MEDIUM] ダッシュボードパスワードのログ出力

```python
# dashboard_server.py:47-49
logger.warning(
    "DASHBOARD_PASSWORD not set. Generated random password: %s  ",
    _env_password,
)
```

生成されたパスワードがログに記録される。プロダクション環境ではログ収集システムに平文パスワードが残る。

**推奨**: パスワードをstdoutに出力するか、起動メッセージのみに限定。logger.warning への出力は避ける

#### [LOW] Bandit で除外しているルールが多い

```yaml
# main.yml:47
bandit -r ... -s B101,B104,B311,B404,B603,B607
```

`B404`（subprocess）、`B603`（subprocess_without_shell_equals_true）、`B607`（start_process_with_partial_path）の除外は、`kernel.py` の `subprocess.Popen` 使用に起因する。doctor 自動起動でのシェルコマンド実行は攻撃面を広げる。

---

## 3. 信頼性・耐障害性

### 良い点

- **Atomic I/O** (`core/atomic_io.py`): write-to-temp → fsync → rename パターンの正しい実装。ディレクトリ fsync も含む
- **Hash-chained TrustLog** (`logging/trust_log.py`): `h_t = SHA256(h_{t-1} || r_t)` の論文準拠実装。改ざん検出が可能
- **スレッドセーフ**: TrustLog、MemoryStore、CosineIndex、nonce ストア、レート制限すべてにロックを使用
- **Graceful Degradation**: 全モジュールが import 失敗時にフォールバックを持つ

### 問題点

#### [HIGH] TrustLog の JSON ファイルが 2000 件制限

```python
MAX_JSON_ITEMS = 2000  # trust_log.py:35
```

JSONL は全件保持だが、JSON は最新 2000 件のみ。`_load_logs_json()` で読み込む JSON と `get_last_hash()` で読む JSONL の間に乖離が生じる可能性がある。コード内のコメント（L196-198）でこの問題に言及し修正済みだが、JSON ファイルの存在意義自体を再検討すべき。

**推奨**: JSON ファイルは廃止し JSONL のみにするか、明確に用途を分離

#### [MEDIUM] MemoryStore の全件スキャン

```python
# memory/store.py:200-205
with open(FILES[kind], encoding="utf-8") as f:
    for line in f:
        items.append(json.loads(line))
```

検索のたびに JSONL 全件を読み込んで `table` を構築している。データ量が増えると線形にパフォーマンスが劣化する。

**推奨**: CosineIndex の search 結果に metadata を含めるか、SQLite 等のインデックス付きストレージを使用

#### [MEDIUM] `_schedule_nonce_cleanup` の再帰 Timer

```python
# server.py:578-584
def _schedule_nonce_cleanup() -> None:
    global _nonce_cleanup_timer
    _cleanup_nonces()
    _nonce_cleanup_timer = threading.Timer(60.0, _schedule_nonce_cleanup)
    _nonce_cleanup_timer.daemon = True
    _nonce_cleanup_timer.start()
```

再帰的な Timer 呼び出し。Timer が例外で死んだ場合にクリーンアップが永久に停止する。

**推奨**: try/except でラップするか、`ScheduledExecutorService` 的なパターンを使用

#### [LOW] Graceful Degradation が過度

ほぼ全ての関数が try/except で例外を飲み込んでおり、デバッグが困難になるケースがある。例えば `_call_fuji()` (`server.py:1104-1123`) は3重の try/except で異なるシグネチャを試す。

**推奨**: 開発/テスト環境では例外をそのまま伝播させるモード（`VERITAS_STRICT_MODE`）を追加

---

## 4. コード品質

### 良い点

- **型アノテーション**: ほぼ全関数に型ヒントあり
- **TypedDict/Protocol**: `core/types.py` での型定義が充実
- **config からのマジックナンバー排除**: `ScoringConfig`, `FujiConfig`, `PipelineConfig` による設定外部化
- **ユーティリティの統合**: `core/utils.py` に共通関数を集約

### 問題点

#### [HIGH] `server.py` が 1460 行 — 責務過多

`server.py` は以下の責務を一つのファイルで担っている:
- FastAPI アプリ初期化
- CORS/セキュリティミドルウェア
- APIキー/HMAC/レート制限認証
- 全エンドポイント（health, decide, fuji, memory, metrics, trust feedback）
- TrustLog ヘルパー
- Lazy import インフラ

**推奨**: 認証 → `auth.py`、ミドルウェア → `middleware.py`、TrustLog → `trust_helpers.py` に分割

#### [HIGH] テスト対応のための過度な後方互換コード

`server.py` の多くのコードがテストの monkeypatch に対応するために存在する:

```python
# server.py:87-96 テストがこれらの属性を期待
# server.py:142-186 プレースホルダースタブ
# server.py:1104-1123 シグネチャ差を吸収する _call_fuji
```

テスト実装がプロダクションコードの設計を歪めている。

**推奨**: テストを依存注入ベースにリファクタし、プロダクションコードからテスト互換レイヤーを除去

#### [MEDIUM] 日本語と英語のコメント混在

コードベース全体で日本語コメントと英語コメントが混在している。docstring は英語が多いが、インラインコメントは日本語が多い。一貫性がない。

**推奨**: パブリックAPI の docstring は英語、インラインコメントは日本語、という規約を明確化

#### [MEDIUM] `# noqa`, `# type: ignore` の多用

型チェックの抑制が多い。特に `server.py` の lazy import 周りと、`fuji.py` の `yaml` import。

#### [LOW] `__init__.py` の `from __future__ import annotations` の不統一

一部ファイルで使用、一部で未使用。

---

## 5. パフォーマンス

### 問題点

#### [HIGH] CosineIndex の全ベクトルコピー

```python
# index_cosine.py:171
V = self.vecs.copy()  # スナップショット
```

検索のたびに全ベクトル配列をコピーしている。データ量が増えるとメモリ消費と処理時間が線形に増加する。

**推奨**: Read-Write Lock パターンに変更し、読み取り時はコピーなしで直接参照

#### [MEDIUM] HashEmbedder の品質

`memory/embedder.py` が `HashEmbedder` を使用している。これはハッシュベースの疑似埋め込みで、semantic similarity の品質は sentence-transformers に大きく劣る。requirements.txt に sentence-transformers がある以上、本番では使い分けが必要。

#### [MEDIUM] JSONL の全件スキャン（再掲）

`memory/store.py` の search が毎回 JSONL 全件を読む問題。

#### [LOW] `_effective_log_paths()` の毎回再計算

`server.py:108-124` の `_effective_log_paths()` は呼び出しのたびに global 変数の比較を行う。キャッシュしてもよい。

---

## 6. FUJI Gate（安全性ゲート）

### 良い点

- **多層防御**: Safety Head → Policy Engine → Keyword Fallback の3層構造
- **Prompt Injection 対策**: 5パターンの正規表現ベース検出 (`fuji.py:138-175`)
- **PII 検出**: 包括的な日本語PII対応（マイナンバー、住所、電話番号等）
- **PoC モード**: 高リスク時に deny、それ以外で needs_human_review に倒す安全側設計
- **不変条件の文書化**: docstring に deny ↔ rejection_reason の対応を明記

### 問題点

#### [MEDIUM] BANNED_KEYWORDS のバイパス可能性

```python
# fuji.py:93-108
BANNED_KEYWORDS_FALLBACK = {"harm", "kill", "exploit", ...}
```

単純な文字列マッチングのため、unicode 正規化やスペル変形（"k1ll", "h@rm"）でバイパス可能。

**推奨**: LLM Safety Head が利用可能な場合はそちらを優先（現在もそうなっているが、fallback の限界を文書化）

#### [MEDIUM] Prompt Injection パターンの限界

正規表現ベースの5パターンのみ。新しい手法に対する更新メカニズムがない。

**推奨**: パターンを外部 YAML/JSON 化して更新を容易にする

---

## 7. TrustLog（監査ログ）

### 良い点

- **Hash Chain**: `SHA256(prev_hash || normalize(entry))` の論文準拠実装
- **Atomic Write**: `atomic_append_line()` + `atomic_write_json()` で耐障害性確保
- **Thread Safety**: RLock による排他制御
- **Log Rotation**: `rotate.py` によるファイルローテーション
- **検証機能**: `verify_trust_log()` でチェーン整合性を検証可能

### 問題点

#### [MEDIUM] Hash Chain の JSON 正規化依存

```python
# trust_log.py:60-69
def _normalize_entry_for_hash(entry):
    payload = dict(entry)
    payload.pop("sha256", None)
    payload.pop("sha256_prev", None)
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)
```

`json.dumps` の実装に依存している。Python のバージョン差、float の表現差異でハッシュが変わる可能性がある。

**推奨**: RFC 8785 (JSON Canonicalization Scheme) の採用を検討

---

## 8. LLM クライアント

### 良い点

- **マルチプロバイダー対応**: OpenAI, Anthropic, Google, Ollama, OpenRouter
- **リトライ機構**: 指数バックオフ付きリトライ
- **Affect 注入**: スタイル・トーンの system prompt 注入

### 問題点

#### [MEDIUM] API キーの環境変数命名不統一

```python
# llm_client.py:107
return os.environ.get("OPENAI_API_KEY") or os.environ.get("OPEN_API_KEY")
```

`OPEN_API_KEY` というフォールバックが存在する。typo 互換だが、ドキュメントされていない。

#### [LOW] `requests` ライブラリの直接使用

`httpx` (async 対応) が requirements にあるにもかかわらず、`llm_client.py` は同期の `requests` を使用。FastAPI の async エンドポイントでブロッキング呼び出しになる。

**推奨**: `httpx.AsyncClient` に移行

---

## 9. Docker & CI/CD

### 良い点

- **非root実行**: `appuser` によるコンテナ内権限最小化
- **ヘルスチェック**: `/health` エンドポイントによるコンテナ監視
- **マルチバージョンテスト**: Python 3.11 + 3.12 のマトリックス
- **Lint + Security**: Ruff + Bandit によるコード品質・セキュリティスキャン
- **Concurrency Control**: 同一ブランチの CI 実行を自動キャンセル

### 問題点

#### [MEDIUM] `COPY . .` によるイメージ肥大化

```dockerfile
COPY . .
```

`.dockerignore` の内容次第だが、テストファイル、docs、.git 等がイメージに含まれる可能性がある。

**推奨**: マルチステージビルドを使用し、本番イメージにはランタイムに必要なファイルのみを含める

#### [MEDIUM] 依存関係のピン留め不足

`requirements.txt` でバージョンをピン留めしているが、CI の `pip install` ステップで追加パッケージを `pip install requests fastapi ...` のようにバージョン指定なしでインストールしている。

#### [LOW] テストカバレッジ目標が 40% — 低すぎる

```yaml
--cov-fail-under=40
```

安全性が重要なシステムでは 80% 以上を目標にすべき。特に FUJI Gate と TrustLog のカバレッジは 95%+ が望ましい。

---

## 10. 設計パターンの評価

| パターン | 使用箇所 | 評価 |
|---------|---------|------|
| Lazy Import + Fallback | server.py | 優秀。可用性を最優先 |
| Atomic Write (temp + fsync + rename) | atomic_io.py | 正しい実装。ディレクトリ fsync も含む |
| Hash Chain | trust_log.py | 論文準拠。改ざん検出に有効 |
| Strategy Pattern | debate.py の viewpoints | 適切。拡張性あり |
| Builder Pattern | schemas.py の validator chain | Pydantic v2 を活用。堅牢 |
| Facade Pattern | tools/__init__.py の call_tool | シンプルで良い |
| Observer Pattern | kernel.py の doctor 自動起動 | レート制限付きで適切 |

---

## 11. 改善優先度ロードマップ

### Phase 1（即時対応）
1. `pipeline.py` の分割（122KB → 複数ファイル）
2. テストカバレッジ目標を 60% → 80% に引き上げ
3. nonce/rate-limit のマルチワーカー対応（Redis 等）

### Phase 2（短期）
4. `server.py` の責務分割（auth, middleware, helpers）
5. MemoryStore の JSONL 全件スキャン解消
6. CosineIndex の Read-Write Lock 化
7. `llm_client.py` の httpx 移行

### Phase 3（中期）
8. テスト互換レイヤーの除去（依存注入化）
9. Docker マルチステージビルド
10. TrustLog の JSON 正規化を RFC 8785 準拠に
11. FUJI パターンの外部化（YAML/JSON）

---

## 12. まとめ

VERITAS OS v2.0 は、LLM エージェントの意思決定に**監査可能性と安全性**を組み込んだ意欲的なプロジェクトである。Hash-chained TrustLog、多層 FUJI Gate、Atomic I/O といった設計は、規制環境での LLM 運用に適している。

主な課題は:
1. **巨大ファイルの分割** — pipeline.py (122KB), server.py (1460行), core/memory.py (66KB) が保守性のボトルネック
2. **インメモリ状態管理** — nonce、レート制限、メモリインデックスがプロセスローカル。スケールアウト時に問題
3. **テスト駆動のコード歪み** — テストの monkeypatch に合わせたプロダクションコードが複雑性を増加
4. **パフォーマンス** — JSONL 全件スキャン、ベクトルコピー等のスケーラビリティ課題

全体として、安全性を最優先とした設計思想が一貫しており、PoC/MVP として高い完成度にある。上記の改善を段階的に実施することで、プロダクション品質に到達可能である。
