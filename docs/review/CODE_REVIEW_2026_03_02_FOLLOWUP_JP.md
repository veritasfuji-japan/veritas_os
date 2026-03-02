# VERITAS OS フォローアップレビューレポート

**日付:** 2026-03-02
**対象:** 前回レビュー（2026-02-27）で指摘した全50件の改善点
**レビュー方法:** 各ファイルの実コードを直接検証 + git commit 履歴を照合
**結論:** **49/50件 解消確認。残存1件（C-3 部分残存）。**

---

## 総合サマリー

| 深刻度 | 指摘件数 | 完全解消 | 部分解消 | 未対応 |
|--------|----------|----------|----------|--------|
| CRITICAL | 5 | 4 | 1 | 0 |
| HIGH | 12 | 12 | 0 | 0 |
| MEDIUM | 18 | 18 | 0 | 0 |
| LOW | 15 | 15 | 0 | 0 |
| **合計** | **50** | **49** | **1** | **0** |

---

## 1. CRITICAL

### C-1 ✅ メモリAPI ユーザー分離 — **解消**
- `server.py`: `_resolve_memory_user_id()` を実装。APIキーからuser_idを導出し、
  任意の `user_id` への書き込みをブロック。
- `/v1/memory/put` および `/v1/memory/search` 双方で適用済み。

### C-2 ✅ メモリ検索 kinds バリデーション — **解消**
- `server.py`: `_validate_memory_kinds()` を実装。
  `VALID_MEMORY_KINDS` ホワイトリストに対して全 kinds を検証。
  不正値は即座に400エラーを返す。

### C-3 ⚠️ CSPヘッダー unsafe-inline — **部分解消（残存課題あり）**
- **改善点:**
  - CSPを Report-Only から **エンフォースモード** (`Content-Security-Policy`) に昇格。
  - nonce-based の厳格な `Content-Security-Policy-Report-Only` を追加し、
    段階的移行の準備を整備。
- **残存課題:**
  - 強制CSP の `script-src` に `'unsafe-inline'` が残存。
  - ファイルコメントには「Next.js ランタイムとの互換性維持のため」と説明あり。
  - `style-src` の `'unsafe-inline'` も両ポリシーに残存。
- **推奨:** Next.js の `nonce` 対応 (`generateNonces`) で `unsafe-inline` を完全排除可能。
  継続的な対応が必要。

### C-4 ✅ React エラーバウンダリ — **解消**
- `frontend/app/error.tsx` を新規作成。Next.js App Router のグローバルエラーバウンダリ。
- 「再試行」ボタン付きのリカバリUI を実装。
- `useEffect` で `console.error` によるエラーログも確保。

### C-5 ✅ kernel.py テスト完全欠如 — **解消**
- `veritas_os/tests/test_kernel.py` を新規作成（139行）。
- 主要 decide() フローの回帰テストをカバー。

---

## 2. HIGH

### H-1 ✅ 認証失敗時のレート制限 — **解消**
- `server.py`: `_enforce_auth_failure_rate_limit()` を実装。
  IPベースのトークンバケット方式で認証失敗を制限 (429 Too Many Requests)。
- `_AUTH_FAIL_BUCKET_MAX` でバケット上限も設定し、メモリ枯渇対策も実施。

### H-2 ✅ ゼロ除算リスク — **解消**
- `agi_goals.py:236`: `safe_total = max(total, 1e-8)` を使用。
  ZeroDivisionError と NaN 伝播を防止。

### H-3 ✅ パス走査シンボリックリンク攻撃 — **解消**
- `code_planner.py`: `p.is_symlink()` チェックを明示的に追加。
  シンボリックリンクのファイルはスキップして警告ログを出力。
  `resolved_p.relative_to(resolved_base)` によるパストラバーサル防止も継続。

### H-4 ✅ ダッシュボード Null クライアントクラッシュ — **解消**
- `dashboard_server.py`: `_get_request_client_host()` を実装。
  `request.client is None` の場合を安全に処理（`X-Forwarded-For` ヘッダーにフォールバック）。

### H-5 ✅ エフェメラルパスワードのマルチワーカー競合 — **解消**
- `dashboard_server.py`: `_load_or_create_shared_ephemeral_password()` を実装。
  `O_EXCL` フラグ付きファイル書き込みでアトミックに生成し、複数ワーカーで共有。
  `FileExistsError` 競合も安全に処理。

### H-6 ✅ レガシー Pickle デシリアライゼーション経路 — **解消**
- `memory/index_cosine.py`: `allow_pickle=False` のみで `np.load()` を呼び出す。
  レガシー pickle パスを完全削除。環境変数による有効化オプションも除去済み。

### H-7 ✅ debate.py リソース枯渇 — **解消**
- `debate.py`: `_estimate_option_payload_size()` と `MAX_OPTIONS_PAYLOAD_BYTES` を実装。
  累積ペイロードサイズが上限を超えた場合に打ち切り。
  `MAX_OPTIONS` による件数制限も追加。

### H-8 ✅ ドメインサフィックス攻撃 — **解消**
- `web_search.py`: `_is_hostname_exact_or_subdomain()` を実装。
  完全一致 (`hostname == domain`) またはサブドメイン (`hostname.endswith(f".{domain}")`) のみ許可。
  部分文字列マッチを排除。

### H-9 ✅ LLMクライアントのAPIレスポンスログ漏洩 — **解消**
- `llm_client.py`: `_redact_response_preview()` を実装。
  `_redact_text()` ユーティリティを使ってセンシティブ情報をマスク後、200文字に切り詰めてログ出力。

### H-10 ✅ ハッシュチェーンのローテーション後検証不備 — **解消**
- `trust_log.py`: `_recover_last_hash_from_rotated_log()` を実装。
  マーカーファイルが欠落した場合、ローテーション済みログからチェーンを回復。
  回復失敗時は警告ログを出力。

### H-11 ✅ trust_log.py シンボリックリンク競合 — **解消**
- `logging/rotate.py`（新規モジュール）: ローテーション処理を分離。
  `os.replace()` でアトミックにファイルを置換（TOCTOU競合を排除）。
  `is_symlink()` チェックも残存し、二重防御を実現。

### H-12 ✅ fetchタイムアウト欠如（フロントエンド） — **解消**
- `features/console/api/useDecide.ts`: `AbortController` + `window.setTimeout()` でタイムアウトを実装。
  タイムアウト時はユーザーにエラーメッセージを表示し、モノトニックなリクエストIDで応答の入れ替わりも防止。
- `frontend/app/audit/page.tsx`: `AbortController` を使ったタイムアウト付きfetchを実装。
- ※ `console/page.tsx` は大規模リファクタリングで `useDecide` フックに分離済み。

---

## 3. MEDIUM

### M-1 ✅ CORS設定リスク — **解消**
- `server.py`: `_resolve_cors_settings()` を実装。
  `origins == ["*"]` かつ `allow_credentials=True` の組み合わせを禁止。
  ワイルドカード時は `allow_credentials=False` にフォールバックし、警告ログを出力。

### M-2 ✅ ガバナンスポリシーの部分更新バリデーション不足 — **解消**
- `governance.py`: パッチのマージ後に即座に `model_validate()` を呼び出し。
  Pydanticバリデーションのバイパスを防止。

### M-3 ✅ メトリクスエンドポイントの無制限ファイル一覧 — **解消**
- `server.py`: `_collect_recent_decide_files()` を `heapq` を使って実装。
  `decide_file_limit` クエリパラメータで件数を制限（デフォルト500、最大5000）。
  メモリ使用量を有界に保ちながら最新ファイルのみを返す。

### M-4 ✅ データセット統計のOOMリスク — **解消**
- `dataset_writer.py`: `for line in f` によるストリーミング処理に変更。
  全レコードをリストに読み込まず、逐次集計。

### M-5 ✅ LLMモデル名バリデーション不足 — **解消**
- `llm_client.py`: `_validate_model_name()` を実装。
  制御文字・NULLバイト・パストークンを拒否し、プロバイダー別のallowlistプレフィックスを適用。

### M-6 ✅ JSON再帰パースの深さ制限なし — **解消**
- `debate.py`: `MAX_JSON_NESTED_DEPTH = 100` を定数として定義。
  `_extract_objects_from_array()` の `max_depth` パラメータで深度を制限。
  超過時は警告ログを出力して処理を打ち切り。

### M-7 ✅ クエリ長バリデーション欠如 — **解消**
- `kernel_qa.py`: `MAX_QA_QUERY_LENGTH = 10_000` を定義し、
  処理前に `len(q) > MAX_QA_QUERY_LENGTH` チェックを実施。

### M-8 ✅ ワールドモデル更新のレース条件 — **解消**
- `kernel_stages.py`: `adapt.PERSONA_UPDATE_LOCK` でコンテキストマネージャーを使い、
  `bias_weights` の読み取り→更新→保存をアトミックに処理。
  並行 decide() 呼び出しによる競合更新を防止。

### M-9 ✅ evidence.py の None チェック欠如 — **解消**
- `evidence.py`: `context["goals"]` が `None`、スカラー値、またはイテラブルの
  いずれでも安全に処理するよう None チェックを追加。

### M-10 ✅ VectorMemory初期化のスレッドセーフティ — **解消**
- `memory.py`: `_load_model()` にダブルチェックロッキングパターンを適用。
  `self.model is not None` の外側チェック後に `with self._lock:` で内側チェック。
  複数スレッドの同時初期化を防止。

### M-11 ✅ DNS解決のTOCTOU競合 — **解消**
- `web_search.py`: リクエスト送信時にDNS解決結果を再検証。
  プリフライト解決後に実際のリクエスト時点でIPアドレスが変化していないかを確認し、
  DNSリバインディング攻撃を防止。

### M-12 ✅ llm_safety.py ユーザー入力のプロンプト直接埋め込み — **解消**
- `llm_safety.py`: `_sanitize_text_for_prompt()` でユーザー入力をエスケープ後、
  `sanitized_text` としてプロンプトに埋め込み。

### M-13 ✅ useCallback メモ化欠如 — **解消**
- `governance/page.tsx`: `fetchValueDrift`, `fetchPolicy`, `savePolicy` を
  `useCallback` でラップ。依存配列も正しく設定。

### M-14 ✅ SVG描画パフォーマンス — **解消**
- `risk/page.tsx`: `RiskScatterCanvas` コンポーネントを `React.memo` でラップし、
  Canvas API で描画。SVGノードの大量生成とReact差分計算を排除。

### M-15 ✅ ESLint設定の不足 — **解消**
- `frontend/.eslintrc.json`: `plugin:jsx-a11y/recommended` を追加。
  `no-eval`, `no-implied-eval`, `no-new-func` などのセキュリティルールも設定。

### M-16 ✅ .pre-commit-config.yaml の不足 — **解消**
- `.pre-commit-config.yaml`: `ruff`, `black`, `bandit`, `mypy` を追加。
  `gitleaks` のみだった設定を包括的な品質・セキュリティゲートに強化。

### M-17 ✅ Bandit設定の過度な除外 — **解消**
- `.github/workflows/main.yml`: bandit の `-s` 除外を `B101` のみに削減。
  以前は B101, B104, B311, B404, B603, B607 の6件を除外していたが、5件を解除。

### M-18 ✅ テスト環境変数汚染 — **解消**
- `tests/test_governance_api.py`: `@pytest.fixture(autouse=True)` に
  `monkeypatch.setenv("VERITAS_API_KEY", ...)` を移動。
  モジュールレベルの `os.environ` 設定を排除し、テスト間の汚染を防止。

---

## 4. LOW

### L-1 ✅ config.py の空シークレット許容 — **解消**
- `config.py`: `validate_api_secret_non_empty()` を実装。
  `should_enforce_api_secret_validation()` が True の場合、起動時に非空を検証。

### L-2 ✅ カリキュラムのメモリ無制限増加 — **解消**
- `curriculum.py`: `OrderedDict` + `move_to_end()` でLRUキャッシュを実装。
  `_MAX_USERS` 上限を超えた場合、最も古いエントリを削除。

### L-3 ✅ llm_client.py の文字列結合 O(n²) — **解消**
- `llm_client.py`: `extra_parts: List[str] = []` + `"".join(extra_parts)` に変更。
  ループ内での `+=` による二次的パフォーマンス劣化を解消。

### L-4 ✅ affect.py のリスト変異 — **解消**
- `affect.py`: `source_messages = list(messages or [])` で入力リストをコピー。
  `msgs[0] = {...}` による呼び出し元への副作用を排除。

### L-5 ✅ 未使用変数 code_planner.py — **解消**
- `code_planner.py`: `_decision_count`, `_last_risk` を削除。
  `# noqa: F841` アノテーションも不要になり除去。

### L-6 ✅ ハードコード値の散在 — **解消**
- `web_search.py`: `WEBSEARCH_TIMEOUT_SECONDS`, `WEBSEARCH_TIMEOUT_DEFAULT_SECONDS`,
  `WEBSEARCH_TIMEOUT_MAX_SECONDS` として定数を集約。
  環境変数でのオーバーライドも可能に。

### L-7 ✅ Dockerfileのパス問題 — **解消**
- `Dockerfile`: `COPY ./veritas_os/requirements.txt /tmp/requirements.txt` に修正。
  パス構造が正確になり、ビルド時のコピーエラーを解消。

### L-8 ✅ Docker CMD のシグナル処理 — **解消**
- `Dockerfile`: `CMD ["uvicorn", "veritas_os.api.server:app", ...]` として exec形式に変更。
  PID 1 問題が解消され、SIGTERM を正しく処理。`STOPSIGNAL SIGTERM` も追加。

### L-9 ✅ エラーメッセージの不一致 — **解消**
- `llm_client.py`: LLMパースエラーのメッセージ形式を統一。
  コミット `04a10aa "Unify LLM parse error message format"` で対応済み。

### L-10 ✅ SHA256正規表現で大文字拒否 — **解消**
- `trust_log.py:41`: `re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)` に変更。
  大文字の16進数も受け入れるように修正。

### L-11 ✅ フロントエンドの検索レース条件 — **解消**
- `audit/page.tsx`: `AbortController` を使ってリクエストをキャンセル可能に。
  連続検索で前のリクエストを中断し、古いレスポンスによるUIの上書きを防止。

### L-12 ✅ SSEストリームの再接続バックオフ — **解消**
- `components/live-event-stream.tsx`: 指数バックオフ (`Math.min(BASE * 2^n, MAX)`) と
  ジッター (`0.8〜1.2倍`) を実装。再接続嵐を防止。

### L-13 ✅ aria-labelの不十分な記述 — **解消**
- `audit/page.tsx:564`: `aria-label={t("リクエストIDで検索", "Search by request ID")}` に変更。
  スクリーンリーダーが正確に読み上げられるよう改善。

### L-14 ✅ テスト乱数シードの未設定 — **解消**
- `tests/test_thread_safety.py`: `np.random.default_rng(seed_base + thread_id)` で
  スレッドごとに決定論的なシードを設定。テストの再現性を確保。

### L-15 ✅ テスト用の危険プロンプトハードコード — **解消**
- `features/console/constants.ts`: `NEXT_PUBLIC_ENABLE_DANGER_PRESETS=true` を
  明示した場合かつ非本番環境のみで有効化するフィーチャーフラグを実装。
  本番ビルドでは危険プリセットは完全に無効化。

---

## 5. 残存課題

### C-3: script-src 'unsafe-inline' の完全排除

**現状:** 強制CSPの `script-src` に `'unsafe-inline'` が残存。

**推奨対応:**
1. Next.js の `generateNonces` (`next.config.mjs`) と `nonce` ミドルウェアを実装
2. `pages/_document.tsx` または App Router の `layout.tsx` で nonce を各スクリプトタグに付与
3. Report-Only の `script-src 'nonce-__VERITAS_NONCE__'` が安定したら、強制CSPに適用
4. `style-src 'unsafe-inline'` についても同様に CSS Modules または nonce 対応を検討

---

## 6. 新たに判明した改善点

### N-1. `_resolve_memory_user_id()` の実装詳細確認を推奨
- APIキーから user_id を導出するロジックが適切にユーザー間の分離を保証しているか、
  マルチテナント環境での検証を推奨。

### N-2. `test_kernel.py` のカバレッジ拡充
- 現在 139 行でコアケースをカバーしているが、エッジケース（空入力、同時呼び出し）の
  追加テストを推奨。

### N-3. `rotate.py` の統合テスト
- `trust_log.py` からローテーション処理を `rotate.py` に分離したことにより、
  結合部分の統合テストを追加することを推奨。

---

## 総評

前回レビューで指摘した全50件中、**49件が解消** されました。
対応速度とカバレッジは非常に高く評価できます。

唯一の残存課題（C-3: `unsafe-inline`）は Next.js アーキテクチャ上の技術的負債であり、
段階的な移行として Report-Only ポリシーの準備が整っています。
継続的な対応で完全解消が可能な状態です。

コードの全体的な品質は前回から大幅に向上しており、
特に **セキュリティ層の多重防御**（レート制限 + 入力検証 + ユーザー分離）と
**フロントエンドの堅牢性**（エラーバウンダリ + タイムアウト + AbortController）の
実装は高品質です。
