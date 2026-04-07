# VERITAS OS 全コードレビュー報告書

**レビュー日**: 2026-02-08
**レビュー対象**: veritas_os/ 全モジュール
**レビュアー**: Claude (Opus 4.6)

---

## 1. プロジェクト概要

VERITAS OS は **AGI意思決定支援OS** で、以下のコアモジュールから構成される:

- **Kernel** (`core/kernel.py`): 意思決定の中枢。query → alternatives → scoring → debate → FUJI gate → response
- **Pipeline** (`core/pipeline.py`): FastAPI サーバーからのエントリポイント。kernel.decide を orchestrate
- **FUJI Gate** (`core/fuji.py`): Safety / Policy / TrustLog による安全ゲート
- **DebateOS** (`core/debate.py`): Multi-Agent Debate による候補評価
- **WorldOS** (`core/world.py`): 世界状態の管理・シミュレーション
- **MemoryOS** (`memory/`): エピソード記憶・セマンティック検索
- **ValueCore** (`core/value_core.py`): 価値観の学習・評価
- **TrustLog** (`logging/trust_log.py`): SHA-256 ハッシュチェーンによる監査ログ
- **API Layer** (`api/`): FastAPI ベースの REST API
- **Chainlit UI** (`chainlit_app.py`): デモ用 Web UI

---

## 2. 全体的な評価

### 良い点

| カテゴリ | 詳細 |
|---------|------|
| **アーキテクチャ** | モジュール分離が良好。kernel / pipeline / fuji / debate / memory の責務が明確 |
| **耐障害設計** | try/except による graceful degradation が徹底されている。必須/推奨/任意のモジュール分類 |
| **型定義** | `core/types.py` に TypedDict / Protocol が集約され、型安全性を高めている |
| **設定外部化** | `core/config.py` に ScoringConfig / FujiConfig / PipelineConfig が dataclass で整理 |
| **PII保護** | `core/sanitize.py` が包括的。Luhn検証、マイナンバーチェックデジット等を網羅 |
| **原子的I/O** | `core/atomic_io.py` が write→fsync→rename パターンを正しく実装。ディレクトリ fsync も対応 |
| **TrustLog** | 論文の式 `hₜ = SHA256(hₜ₋₁ || rₜ)` に準拠。スレッドセーフ化済み |
| **セキュリティ** | HMAC署名検証、APIキー毎回取得、Content-Length制限、パス検証、プロンプトインジェクション検知 |
| **テスト** | 130+ のテストファイル。カバレッジ 40% 以上をCIで要求 |
| **CI/CD** | lint(ruff) + bandit + pytest + coverage をマトリクスで実行 |

---

## 3. 重要度別の問題点

### CRITICAL (即時対応推奨)

#### C-1: `kernel.py` での subprocess.Popen によるバックグラウンドプロセス起動

**ファイル**: `core/kernel.py:1069`

```python
subprocess.Popen(
    [python_executable, "-m", "veritas_os.scripts.doctor"],
    stdout=log_file,
    stderr=subprocess.STDOUT,
    shell=False,
)
```

**問題**:
- `decide()` が呼ばれるたびに doctor スクリプトをバックグラウンドで起動する。高頻度リクエストでプロセスが溜まる可能性。
- `auto_doctor` はデフォルト `True` で、明示的に無効化しない限り毎回起動する。

**推奨**:
- レート制限（最低 N 秒間隔）を導入
- `subprocess.Popen` の戻り値を管理し、前回のプロセスが完了してから次を起動


#### C-2: `config.py` に API secret のプレースホルダーがハードコード

**ファイル**: `core/config.py:201`

```python
api_secret: str = field(
    default_factory=lambda: os.getenv(
        "VERITAS_API_SECRET",
        "YOUR_VERITAS_API_SECRET_HERE",
    )
)
```

**問題**: 環境変数未設定時にプレースホルダー文字列がそのまま使われる。server.py 側で検出・拒否されるが、config 層で防御すべき。

**推奨**: デフォルト値を空文字列にし、使用時に未設定エラーを出す


#### C-3: `kernel.py` で `logging` と `logger` が二重に定義

**ファイル**: `core/kernel.py:13,21,36,38-39`

```python
import logging          # L13
logger = logging.getLogger(__name__)  # L21
import logging          # L36 (重複 import)
log = logging.getLogger(__name__)     # L39
```

**問題**: `logger` と `log` の2つのロガー変数が同一モジュールに存在。コード内で混在使用されている（L518 で `logger`、L438 で `log`）。

**推奨**: どちらか一方に統一する

---

### HIGH (近日中の対応推奨)

#### H-1: `pipeline.py` が巨大すぎる (推定 800+ 行)

**問題**: 単一ファイルに多くの責務が集中しており、テスト・保守が困難。

**推奨**:
- メモリ検索、Web検索、スコアリング、レスポンス構築を個別モジュールに分離
- pipeline.py はオーケストレーション層のみに


#### H-2: `world.py` の `DynamicPath` の `__getattr__` フォールバック

**ファイル**: `core/world.py:93-95`

```python
def __getattr__(self, name: str) -> Any:
    # fallback delegation (e.g. .parent, .suffix, .name ...)
    return getattr(self._p(), name)
```

**問題**:
- 存在しない属性へのアクセスで `AttributeError` ではなく `Path` の `AttributeError` が出るため、デバッグが困難
- `_p()` 内の resolver が例外を投げると、属性アクセスのエラーとして表面化し混乱する

**推奨**: 許可する属性をホワイトリストで管理するか、`__getattr__` のエラーハンドリングを改善


#### H-3: `llm_client.py` が同期 `requests.post` を使用

**ファイル**: `core/llm_client.py:377`

**問題**: FastAPI は async フレームワークだが、LLM 呼び出しが同期の `requests.post` で行われている。API レスポンス待ち中にイベントループがブロックされる。

**推奨**: `httpx.AsyncClient` に移行するか、`asyncio.to_thread` でラップ


#### H-4: `web_search.py` が同期 `requests.post` を使用

**ファイル**: `tools/web_search.py:142-147`

**問題**: H-3 と同様。Web検索も同期HTTPクライアントを使用しており、イベントループをブロックする。

**推奨**: 非同期化するか、別スレッドで実行


#### H-5: `llm_safety.py` の OpenAI クライアント Responses API 使用

**ファイル**: `tools/llm_safety.py:202`

```python
resp = client.responses.create(...)
```

**問題**: `resp.output[0].parsed` へのアクセスが安全でない。`output` が空リストの場合 `IndexError` が発生する。

**推奨**: `output` の存在チェックを追加


#### H-6: `trust_log.py` の `get_last_hash()` でのファイル末尾読み取り

**ファイル**: `logging/trust_log.py:97-107`

```python
chunk_size = min(4096, file_size)
f.seek(file_size - chunk_size)
chunk = f.read().decode("utf-8")
lines = chunk.strip().split("\n")
```

**問題**:
- 最終行が 4KB を超える場合、不完全な JSON を読み取る可能性
- マルチバイト UTF-8 の境界で split される可能性（seek 位置がバイト単位のため）

**推奨**: 十分なバッファサイズを確保するか、末尾からの逆読みロジックを改善

---

### MEDIUM (計画的な改善を推奨)

#### M-1: `kernel.py` の例外ハンドリングが広すぎる

**ファイル**: `core/kernel.py` 全般

```python
except Exception:
    pass
```

**問題**: 多くの箇所で `except Exception: pass` パターンが使われ、潜在的なバグが隠蔽される。特に `_score_alternatives()` L370-371 でのサイレント例外。

**推奨**: 最低限 `logging.debug` でエラーを記録する


#### M-2: `debate.py` の危険キーワード一覧が `fuji.py` と重複

**ファイル**: `core/debate.py:33-60`, `core/fuji.py:91-120`, `tools/llm_safety.py:38-63`

**問題**: 同一の禁止キーワードリストが3箇所で別々に定義されている。メンテナンス時に不整合が生じるリスク。

**推奨**: 共通定数モジュール（例: `core/safety_constants.py`）に一元化


#### M-3: `memory/engine.py` が事実上スタブ

**ファイル**: `memory/engine.py`

**問題**: `Embedder`, `VectorIndex`, `MemoryStore` のクラスが定義されているが、全メソッドが `raise NotImplementedError` か `...`（Ellipsis）。実際のメモリストアは `memory/store.py` にある。

**推奨**: engine.py の意図を明確にする（インターフェース定義ならABCを使用）


#### M-4: `Dockerfile` にヘルスチェックがない

**ファイル**: `Dockerfile`

**問題**: `/health` エンドポイントが server.py に存在するが、Dockerfile に `HEALTHCHECK` ディレクティブがない。

**推奨**: `HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1` を追加


#### M-5: `Dockerfile` が root ユーザーで実行

**ファイル**: `Dockerfile`

**問題**: 非特権ユーザーの作成がない。コンテナ内で root として実行されるセキュリティリスク。

**推奨**: `RUN adduser --disabled-password appuser` + `USER appuser` を追加


#### M-6: `config.py` の `VeritasConfig.__post_init__` で `_dirs_ensured` を直接セット

**ファイル**: `core/config.py:272`

```python
self._dirs_ensured = False
```

**問題**: `@dataclass` のフィールドとして宣言されていない `_dirs_ensured` を `__post_init__` で設定。型チェッカーから見えない。

**推奨**: フィールドとして `_dirs_ensured: bool = field(default=False, init=False, repr=False)` を宣言


#### M-7: `schemas.py` の DecideResponse が `extra="allow"` で過度に寛容

**ファイル**: `api/schemas.py:387`

**問題**: 入力バリデーションとレスポンス構築の両方で `extra="allow"` が使われている。未知フィールドがサイレントに通過する。

**推奨**: レスポンス構築では `extra="allow"` は妥当だが、リクエストバリデーションでは `extra="ignore"` を検討

---

### LOW (改善余地あり)

#### L-1: `kernel.py` L47 で `import re` が重複

`re` は L13 で既にインポートされているが、doctor 実行部分の L1061 でローカルに再インポートされている。

#### L-2: `llm_client.py` の Claude モデル名が古い

**ファイル**: `core/llm_client.py:477`

```python
kwargs.setdefault("model", "claude-3-sonnet-20240229")
```

**推奨**: 最新の Claude 4.5/4.6 モデル ID に更新

#### L-3: `chainlit_app.py` でエラーメッセージにスタックトレースが露出

**ファイル**: `chainlit_app.py:312`

```python
thinking.content = f"VERITAS API 呼び出しでエラーが発生しました：\n`{e}`"
```

**推奨**: ユーザー向けには汎用メッセージ、詳細はログに

#### L-4: `web_search.py` の `_normalize_str` がリミット引数を `int()` で再キャスト

**ファイル**: `tools/web_search.py:111`

```python
if limit and len(s) > int(limit):
```

**問題**: `limit` は既に `int` 型のデフォルト引数で渡されているため、`int()` は冗長。

#### L-5: CI で `continue-on-error: true` + 後段で `exit 1`

**ファイル**: `.github/workflows/main.yml:108-143`

**問題**: テストステップが `continue-on-error: true` で実行され、後段で結果をチェックする2段構え。GitHub Actions のネイティブな失敗処理で十分。

#### L-6: `value_core.py` に `fcntl` のインポートがあるが、同一パターンが `world.py` にも存在

**推奨**: OS判定とfcntlインポートのヘルパーを共通化

---

## 4. セキュリティ総合評価

### 良好な点
- **APIキー管理**: `server.py` で毎回環境変数から取得（メモリ保持を回避）
- **HMAC署名**: リプレイ攻撃防止の nonce + timestamp 検証
- **パス検証**: `world.py` で `SENSITIVE_SYSTEM_PATHS` をチェック
- **PII検出**: 包括的な正規表現 + Luhn/マイナンバーチェックデジット検証
- **プロンプトインジェクション検知**: `fuji.py` で5パターンを検出
- **DoS対策**: Content-Length 制限、リスト長制限
- **アトミック書き込み**: データ破損防止

### 改善余地
- **CORS**: `_parse_cors_origins` で `*` を拒否しているが、設定ミスによる許可リスク
- **禁止キーワード**: 3箇所に散在（一元化が必要）
- **bandit 除外**: CI で `B101,B104,B311,B404,B603,B607` を除外。`B603`（subprocess）は kernel.py の `subprocess.Popen` に関連

---

## 5. パフォーマンス注意点

| 懸念 | 影響 | 対策案 |
|------|------|--------|
| `kernel.decide()` が毎回 doctor をバックグラウンド起動 | プロセスリーク | レート制限 |
| 同期 HTTP クライアント (requests) が async FastAPI をブロック | スループット低下 | httpx.AsyncClient への移行 |
| `trust_log.json` の全件読み込み (`_load_logs_json`) | メモリ消費 (MAX_JSON_ITEMS=2000件で限定済み) | 現状で許容範囲 |
| `pipeline.py` の決定処理パスが長い | レイテンシ | fast_mode でスキップ可能（既に実装済み） |

---

## 6. テスト品質

- **テストファイル数**: 70+
- **カバレッジ要件**: 40% (CI)
- **テスト対象**: core, api, tools, memory, logging の主要モジュール
- **改善点**:
  - integration テストが少ない
  - kernel.decide() の end-to-end テストが不十分な可能性
  - mock が多用されており、実際の連携テストが弱い可能性

---

## 7. まとめ

VERITAS OS は **AGI意思決定支援システム** として、安全性（FUJI Gate）、監査性（TrustLog）、適応性（ValueCore/MemoryOS）のバランスが取れた設計になっている。

**最優先で対応すべき3点**:

1. **C-1**: `subprocess.Popen` の doctor 起動にレート制限を導入
2. **C-2**: API secret のプレースホルダーをデフォルト空文字に変更
3. **H-3/H-4**: 同期 HTTP クライアントの非同期化（スループット改善）

**中期的に対応すべき点**:

1. **M-2**: 禁止キーワードリストの一元化
2. **M-4/M-5**: Dockerfile のヘルスチェックと非特権ユーザー追加
3. **H-1**: pipeline.py の分割リファクタリング

全体として、セキュリティ意識が高く、耐障害設計が行き届いたプロジェクトである。上記の改善点を段階的に対応することで、プロダクション品質をさらに高められる。
