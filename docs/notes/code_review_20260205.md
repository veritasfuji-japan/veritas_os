# VERITAS OS v2.0 全コードレビュー

**レビュー日**: 2026-02-05
**対象**: 全ソースコード（veritas_os/ 配下 159 Python ファイル）
**レビュアー**: Claude Code Review

---

## サマリー

VERITAS OS は LLM エージェント向けの監査可能な意思決定 OS で、安全性・ガバナンスを重視した成熟したアーキテクチャを持つ。全体的にコード品質は高く、エラーハンドリングやフォールバック戦略が徹底されている。以下に発見された問題点を重要度別に報告する。

| 重要度 | 件数 |
|--------|------|
| HIGH (要修正) | 7 |
| MEDIUM (推奨修正) | 12 |
| LOW (改善提案) | 8 |

---

## HIGH（要修正）

### H-1: `threading` の二重インポート — `server.py`

**ファイル**: `veritas_os/api/server.py:11` および `server.py:450`

```python
# Line 11
import threading
...
# Line 450
import threading  # 重複
```

同一モジュール内で `threading` が2回インポートされている。機能的な問題はないが、コードの品質指標として修正すべき。

**修正方針**: L450 の `import threading` を削除。

---

### H-2: `_redact_text` / `redact_payload` のコード重複 — `pipeline.py` と `kernel.py`

**ファイル**:
- `veritas_os/core/pipeline.py:221-245`
- `veritas_os/core/kernel.py:159-187`

両ファイルで `_redact_text()` と `redact_payload()` が完全に同一の実装で定義されている。DRY 原則に違反し、一方だけ修正されるリスクがある。

**修正方針**: 共通の `utils.py` または `sanitize.py` に統合し、両モジュールからインポートする。

---

### H-3: `get_last_hash()` がファイル全体をメモリに読み込む — `trust_log.py`

**ファイル**: `veritas_os/logging/trust_log.py:82-94`

```python
def get_last_hash() -> str | None:
    try:
        if LOG_JSONL.exists():
            with open(LOG_JSONL, "r", encoding="utf-8") as f:
                lines = f.readlines()  # ★ 全行をメモリに読み込み
```

JSONL ファイルはローテーション前に数千行に達する可能性がある。最後の行だけが必要なのに全体を読み込むのは非効率であり、大規模運用時に OOM のリスクがある。

**修正方針**: ファイル末尾からシークして最終行を読む実装に変更。例:
```python
def get_last_hash() -> str | None:
    if not LOG_JSONL.exists():
        return None
    try:
        with open(LOG_JSONL, "rb") as f:
            f.seek(0, 2)  # EOF
            pos = f.tell()
            if pos == 0:
                return None
            # 末尾から最大4KBを読んで最終行を取得
            chunk_size = min(4096, pos)
            f.seek(pos - chunk_size)
            lines = f.read().decode("utf-8").strip().split("\n")
            if lines:
                return json.loads(lines[-1]).get("sha256")
    except Exception:
        return None
    return None
```

---

### H-4: `kernel.py` が未使用の `subprocess` をインポート — セキュリティリスク

**ファイル**: `veritas_os/core/kernel.py:18`

```python
import subprocess  # ★ 使用箇所なし
```

`subprocess` は任意コマンド実行が可能なモジュールで、安全性を重視する本プロジェクトで未使用のままインポートすることは攻撃面を不必要に拡大する。

**修正方針**: `import subprocess` を削除。

---

### H-5: `_save_valstats()` がアトミック書き込みを使用していない — `pipeline.py`

**ファイル**: `veritas_os/core/pipeline.py:458-465`

```python
def _save_valstats(d: Dict[str, Any]) -> None:
    try:
        p = Path(VAL_JSON)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
```

TrustLog では `atomic_write_json` を使用しているが、value stats ファイルは通常の `json.dump` で書き込んでいる。クラッシュや電源断時にファイルが破損するリスクがある。

**修正方針**: `atomic_write_json` を使用する。

---

### H-6: ダッシュボードのデフォルトパスワードがハードコード — `dashboard_server.py`

**ファイル**: `veritas_os/api/dashboard_server.py:42`

```python
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "change_me_in_production")
```

デフォルト値 `"change_me_in_production"` は推測可能であり、環境変数未設定のまま本番デプロイされた場合にセキュリティ侵害のリスクがある。起動時に警告はあるが、ブロックされない。

**修正方針**: デフォルト値を空にし、未設定の場合は起動を拒否するか、ランダムパスワードを生成してログ出力する。

---

### H-7: CORS 設定が過度に緩い — `server.py`

**ファイル**: `veritas_os/api/server.py:389-395`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=getattr(cfg, "cors_allow_origins", []),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`allow_methods=["*"]` と `allow_headers=["*"]` は過度に緩い設定。特に `allow_credentials=True` との組み合わせはセキュリティリスクを高める。

**修正方針**: 必要なメソッド (`GET`, `POST`, `OPTIONS`) とヘッダー (`X-API-Key`, `Content-Type` 等) を明示的に指定する。

---

## MEDIUM（推奨修正）

### M-1: レート制限が `/v1/decide` にのみ適用されている

**ファイル**: `veritas_os/api/server.py`

以下のエンドポイントにレート制限がない:
- `/v1/fuji/validate` (L1045)
- `/v1/memory/put` (L1161)
- `/v1/memory/search` (L1231)
- `/v1/memory/get` (L1267)
- `/v1/trust/feedback` (L1325)
- `/v1/metrics` (L1287)

DoS 攻撃のリスクがある。

**修正方針**: 全エンドポイントに `Depends(enforce_rate_limit)` を追加。

---

### M-2: ダッシュボードの 404 レスポンスにファイルパスが露出 — `dashboard_server.py`

**ファイル**: `veritas_os/api/dashboard_server.py:345-347, 364-367`

```python
return JSONResponse(
    {"error": "status file not found", "path": str(STATUS_JSON)},
    status_code=404,
)
```

サーバーの内部パスがクライアントに露出する。

**修正方針**: `"path"` フィールドを削除するか、デバッグモードでのみ含める。

---

### M-3: `memory_get` がエラー詳細をクライアントに返す — `server.py`

**ファイル**: `veritas_os/api/server.py:1280`

```python
return {"ok": False, "error": str(e), "value": None}
```

例外メッセージがそのままクライアントに返されるため、内部構造が漏洩する可能性がある。

**修正方針**: 汎用エラーメッセージを返し、詳細はサーバーログに記録する。

---

### M-4: `value_core.py` がユーザーホームディレクトリに書き込み — `value_core.py`

**ファイル**: `veritas_os/core/value_core.py:54-56`

```python
CFG_DIR = Path(os.path.expanduser("~/.veritas"))
CFG_PATH = CFG_DIR / "value_core.json"
TRUST_LOG_PATH = Path(os.path.expanduser("~/.veritas/trust_log.jsonl"))
```

Docker コンテナ等の環境ではホームディレクトリが適切でない場合がある。`config.py` で定義された `log_dir` 等と整合性がない。

**修正方針**: `config.py` の `cfg.log_dir` を使用するか、環境変数で上書き可能にする。

---

### M-5: `config.py` がインポート時にディレクトリを作成する

**ファイル**: `veritas_os/core/config.py:264-267`

```python
self.log_dir.mkdir(parents=True, exist_ok=True)
self.dataset_dir.mkdir(parents=True, exist_ok=True)
self.data_dir.mkdir(parents=True, exist_ok=True)
self.kv_path.parent.mkdir(parents=True, exist_ok=True)
```

モジュールインポート時の副作用としてディレクトリが作成される。読み取り専用環境やテスト環境で問題を引き起こす可能性がある。

**修正方針**: ディレクトリ作成を遅延実行（最初の書き込み時）に移動する。

---

### M-6: `/v1/decide` がバリデーションエラー時に 200 を返す — `server.py`

**ファイル**: `veritas_os/api/server.py:1006-1016`

```python
except Exception as e:
    return JSONResponse(
        status_code=200,
        content={
            **coerced,
            "ok": True,
            "warn": "response_model_validation_failed",
            ...
        },
    )
```

レスポンスモデルのバリデーション失敗時に 200 OK を返すのは、クライアントが正常レスポンスと区別しにくい。

**修正方針**: 少なくとも `"ok": False` にするか、専用のステータスコード（207 Multi-Status 等）を使用する。

---

### M-7: `utc_now_iso_z()` の実装が複数箇所に存在

**ファイル**:
- `veritas_os/api/server.py:71-73`
- `veritas_os/core/pipeline.py:70-71`
- `veritas_os/logging/trust_log.py:43-45` (`iso_now`)

同一機能が3箇所で独立に実装されている。

**修正方針**: `utils.py` に統合し、各モジュールからインポートする。

---

### M-8: `_to_bool` が同一ファイル内で定義と使用前に参照 — `pipeline.py`

**ファイル**: `veritas_os/core/pipeline.py:87-98`

`_to_bool` は L87 で定義されているが、L103 の `_warn` 関数内で使用される。それ自体は問題ないが、関数定義前のコメント（L199）に「Note: _to_bool is defined earlier」と記載があり、コードの配置に関する混乱が見られる。

---

### M-9: メモリの `kind` バリデーション値がハードコード — `server.py`

**ファイル**: `veritas_os/api/server.py:1181`

```python
if kind not in ("semantic", "episodic", "skills", "doc", "plan"):
    kind = "semantic"
```

同じリストが `types.py` の `MemoryEntry` TypedDict でも定義されている。定数として共有すべき。

---

### M-10: `_extract_json_object` のパース戦略が脆弱 — `utils.py`

**ファイル**: `veritas_os/core/utils.py:247-271`

```python
def _extract_json_object(raw: str) -> str:
    start = raw.index("{")
    end = raw.rindex("}") + 1
    return raw[start:end]
```

ネストした括弧やエスケープされた括弧を含む JSON で誤ったスライスを返す可能性がある（例: `{"a": "}"}`）。

**修正方針**: `json.JSONDecoder().raw_decode()` を使用する方が安全。

---

### M-11: ノンスストアのクリーンアップがリアクティブのみ — `server.py`

**ファイル**: `veritas_os/api/server.py:504-514`

ノンスクリーンアップは `_check_and_register_nonce()` の呼び出し時にのみ実行される。HMAC 認証が使用されていない場合、ノンスストアは無期限に成長する可能性がある（ただし `_NONCE_MAX` による上限あり）。

---

### M-12: `llm_client.py` のリトライ間隔が一定 — `llm_client.py`

**ファイル**: `veritas_os/core/llm_client.py:436-437`

```python
if attempt < LLM_MAX_RETRIES:
    time.sleep(LLM_RETRY_DELAY)
```

レート制限（429）にはエクスポネンシャルバックオフが適用されるが、その他のネットワークエラーには固定間隔が使用されている。

**修正方針**: 全リトライにエクスポネンシャルバックオフを適用。

---

## LOW（改善提案）

### L-1: ログ出力方法の不統一

一部のモジュールは `print()` を使用し（`server.py`）、他は `logging` モジュールを使用している（`llm_client.py`, `memory.py`）。本番環境ではログレベル制御やログ構造化のため、`logging` への統一が望ましい。

### L-2: 型ヒントの表記不統一

`Optional[X]`（旧式）と `X | None`（Python 3.10+）が混在している。`from __future__ import annotations` を全ファイルで使用しているため、`X | None` に統一可能。

### L-3: `constants.py` が二つの責務を持っている

`DecisionStatus` enum とセキュリティ定数（`SENSITIVE_SYSTEM_PATHS`, `MAX_RAW_BODY_LENGTH` 等）が同一ファイルに混在。責務分離のため別ファイルに分けることを推奨。

### L-4: テスト互換性のためのプレースホルダーが複雑

`server.py` の `fuji_core`, `value_core`, `MEMORY_STORE` のプレースホルダー/モンキーパッチ対応は正当だが、かなり複雑。コメントは充実しているが、将来的には dependency injection パターンへの移行を検討すべき。

### L-5: `schemas.py` の `model_validator` が多層的

`DecideResponse` の BEFORE と AFTER バリデータが両方でリストの正規化を行っており、処理が冗長になっている箇所がある（例: alternatives の AltItem → list 化は BEFORE で行い、Alt への最終変換は AFTER で行う）。

### L-6: CI/CD でテスト失敗時の continue-on-error

`.github/workflows/main.yml:73` で `continue-on-error: true` を使用し、後段で手動判定している。GitHub Actions の標準的なパターンだが、`continue-on-error` を使わずに直接失敗させる方がシンプル。

### L-7: `chat_claude` のデフォルトモデルが古い

**ファイル**: `veritas_os/core/llm_client.py:474`

```python
kwargs.setdefault("model", "claude-3-sonnet-20240229")
```

Claude 3 Sonnet のモデル ID が古い。将来的に使用する場合は最新モデルに更新が必要。

### L-8: `Dockerfile` のベースイメージ固定

`python:3.11-slim` を使用しているが、CI/CD では 3.11 と 3.12 の両方をテストしている。Docker イメージも `ARG` で Python バージョンを指定可能にすると良い。

---

## 良い設計・実装のポイント

以下は本プロジェクトで特に優れている点:

1. **堅牢なフォールバック戦略**: すべてのモジュールインポートが try/except で囲まれており、部分的な依存障害でもサーバーが起動する設計
2. **ハッシュチェーン TrustLog**: `h_t = SHA256(h_{t-1} || r_t)` による改ざん検知は理論的に堅実な実装
3. **PII マスキング**: 包括的なパターン定義（Luhn チェック、マイナンバーチェックデジット含む）
4. **型安全性**: 100+ の TypedDict/Protocol 定義、Pydantic バリデーション
5. **スレッドセーフ化**: nonce ストア、レート制限、TrustLog 書き込みにロック実装
6. **アトミック I/O**: `write → fsync → rename` パターンによるクラッシュ耐性
7. **FUJI Safety Gate**: 多層的な安全検査（キーワード、正規表現、LLM ベース）
8. **テストカバレッジ**: 80+ テストファイルによる包括的なテスト

---

## 推奨アクションの優先順位

1. **即時対応**: H-4 (subprocess 削除), H-1 (重複 import 削除), H-6 (デフォルトパスワード)
2. **短期**: H-2 (コード重複解消), H-3 (get_last_hash最適化), H-5 (atomic write), H-7 (CORS)
3. **中期**: M-1 (レート制限拡張), M-2〜M-3 (情報漏洩修正), M-4 (パス統一)
4. **長期**: L-1 (ログ統一), L-4 (DI導入), L-2 (型ヒント統一)
