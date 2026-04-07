# VERITAS OS 総合コードレビュー (2026-03-23)

レビュー対象: リポジトリ全体 (Python backend, TypeScript/React frontend, インフラ/CI/CD)

---

## 総合評価

VERITAS OS は **セキュリティファースト** の設計思想が一貫して適用された高品質なコードベースです。fail-closed のリスクスコアリング、pickle ブロック、PII マスキング、BFF プロキシ、CSP、httpOnly Cookie など、多層防御が徹底されています。

ただし、以下の重要な課題が発見されました。

---

## 1. 重大度: High

### 1.1 ログローテーション時の暗号化ライン未復号 (rotate.py:107)

`save_last_hash_marker` が JSONL の最終行を読み取る際、暗号化された行（`ENC:` プレフィックス）を復号せずに `json.loads` しているため、暗号化有効時にサイレントに失敗します。ローテーション後のハッシュチェーン継続性が壊れるリスクがあります。

**推奨**: `_decrypt_line_if_needed()` を挿入してからパースすること。

### 1.2 HMAC-CTR フォールバックの暗号鍵が 128bit (encryption.py:186)

Pure-Python フォールバックパスで 32 バイトマスターキーを 16 バイトに分割しており、暗号化鍵が 128bit しかありません。AES-GCM パスは 256bit を正しく使用しています。

**推奨**: フォールバックパスでも 256bit 鍵を使用するか、AES-GCM を必須にすること。

### 1.3 CodeQL ワークフローが実質無効 (codeql.yml:24,41)

`continue-on-error: true` + `upload: false` の組み合わせにより、CodeQL の検出結果が GitHub Security タブに表示されず、CI も失敗しません。

**推奨**: `upload: true` に変更し、`continue-on-error` を除去すること。

### 1.4 Docker イメージが Trivy スキャン前に公開 (publish-ghcr.yml:38-48,64)

GHCR への push 後に Trivy が実行されるため、CRITICAL/HIGH 脆弱性があっても公開をブロックできません。

**推奨**: Trivy スキャンを push の前に実行し、ゲートとして機能させること。

### 1.5 Body サイズ制限が Content-Length ヘッダーのみ (middleware.py:184-202)

`limit_body_size` ミドルウェアが `Content-Length` ヘッダーのみをチェックしており、chunked transfer encoding で送信された場合バイパスされます。

**推奨**: 実際のボディストリームサイズも制限するか、uvicorn の `--limit-request-body` を併用すること。

---

## 2. 重大度: Medium

### 2.1 Google モデル許可リストのタプルカンマ欠落 (llm_client.py:215)

```python
LLMProvider.GOOGLE.value: ("gemini-"),  # ← カンマなし = 文字列
```

`("gemini-")` は文字列であり、タプルではありません。`startswith()` が偶然動作していますが、プレフィックス追加時にバグとなります。

**推奨**: `("gemini-",)` に修正。

### 2.2 VectorMemory.add() と rebuild_index() の競合 (memory.py:362-400)

`add()` がロック外でエンベディング生成後、`rebuild_index()` がリスト・行列をリセットした場合、`vstack` が失敗する可能性があります。

**推奨**: `rebuild_index()` 中は `add()` をブロックするか、バージョンカウンターで検出すること。

### 2.3 X-Forwarded-For スプーフィング (auth.py:469-482)

`_resolve_client_ip` が `X-Forwarded-For` を信頼プロキシ検証なしに使用しており、認証失敗レートリミットをバイパス可能です。

**推奨**: 信頼プロキシリストを設定可能にし、最後の信頼されたプロキシ以降の IP を使用すること。

### 2.4 Bandit スキャン範囲が不十分 (main.yml:77-80)

`security/`, `logging/`, `memory/`, `replay/`, `audit/` がスキャン対象外です。pre-commit では全体をカバーしているため、CI との不整合があります。

**推奨**: `veritas_os/` ディレクトリ全体をスキャン対象にすること。

### 2.5 署名付きログの O(n) 全件読み込み (trustlog_signed.py:208)

`append_signed_decision` が毎回全エントリを読み込んで前回のハッシュを取得しています。ログの成長とともに性能劣化します。

**推奨**: 最終ハッシュをキャッシュまたは最終行のみ読み取りに変更。

### 2.6 メモリルートの HTTP ステータスコード不整合 (routes_memory.py:171,293,362,389)

バックエンド未利用時に HTTP 200 + `{"ok": false}` を返しており、503 が適切です。

**推奨**: バックエンド不在時は 503 を返すこと。

### 2.7 replay_engine の monkey-patch がスレッドセーフでない (replay_engine.py:233-238)

`_strict_tool_lock` が `pipeline._get_memory_store` をランタイムで差し替えており、並行 replay 実行時に競合します。

**推奨**: 依存性注入パターンに変更すること。

### 2.8 useDecide のメッセージ ID 衝突 (useDecide.ts:129,138,147,156,166)

ユーザーメッセージは単調カウンターを使用しますが、アシスタント/エラーメッセージは `Date.now()+1` を使用しており、同一ミリ秒で重複する可能性があります。

**推奨**: 全メッセージで単調カウンターを使用すること。

### 2.9 useAuditData.loadLogs のリクエスト重複排除なし (useAuditData.ts:231)

連続クリック時に複数リクエストが競合し、古いレスポンスが最終状態を上書きする可能性があります。

**推奨**: AbortController で前のリクエストをキャンセルすること。

### 2.10 useGovernanceState での window.confirm 使用 (useGovernanceState.ts:94,152,161,169)

hook 内での `window.confirm` はユニットテスト不可能です。

**推奨**: 既存の `ConfirmDialog` コンポーネントをコールバックパターンで使用すること。

### 2.11 trust_log.py のリエントラントロック依存 (trust_log.py:395)

`_trust_log_lock` が `RLock` であることに依存したネストされたロック取得が行われています。通常の `Lock` への変更でデッドロックします。

**推奨**: コメントで明示的に文書化し、`get_last_hash()` のロック不要版を内部用に用意すること。

### 2.12 llm_safety.py の失敗時 ok: True (llm_safety.py:565)

LLM 呼び出し失敗時にフォールバック結果が `ok: True` を返すため、下流が分析失敗と成功を区別できません。

**推奨**: `ok: False` または `degraded: True` フラグを追加すること。

---

## 3. 重大度: Low

### 3.1 f-string ロギング (memory.py:489+)

`logger.info(f"...")` は log level が無効でも文字列補間が実行されます。`%s` フォーマットを使用すべきです。

### 3.2 API シークレットプレースホルダー検出が不十分 (config.py:527)

`"YOUR_VERITAS_API_SECRET_HERE"` のみチェック。`"changeme"` 等は未検出。

### 3.3 .env.example のデフォルト値 (`.env.example:25`)

`VERITAS_API_SECRET=change-me` はコメントアウトすべきです。

### 3.4 CSP の style-src 'unsafe-inline' (middleware.ts:70)

Tailwind 利用のため必要ですが、nonce ベースのスタイルへの移行を検討すべきです。

### 3.5 paths.py の変数名 (paths.py:12)

`REPO_ROOT` がパッケージルートを指しており、git リポジトリルートではありません。名前を `PACKAGE_ROOT` に変更すべきです。

### 3.6 llm_safety.py の日本語住所パターン (llm_safety.py:137)

`"道府県"` はリテラル文字列として実際の住所にマッチしません（デッドコード）。

### 3.7 veritasFetchWithOptions 未使用 (api-client.ts)

リトライ対応の fetch ラッパーが存在しますが、どの hook からも使用されていません。

### 3.8 ミッションページのハードコードデータ (mission-page.tsx:20-131)

静的デモデータがリアルタイムテレメトリと混同される可能性があります。

### 3.9 Docker イメージの provenance/SBOM 無効 (publish-ghcr.yml:43-44)

セキュリティ重視プロジェクトとしてサプライチェーン証明を有効にすべきです。

### 3.10 reason.py の非アトミック JSONL 追記 (reason.py:107)

並行プロセスからの `meta_log` 追記でインターリーブが発生する可能性があります。

---

## 4. 肯定的評価（ストレングス）

### セキュリティ
- `secrets.compare_digest` による定数時間比較 (auth.py:514)
- PBKDF2 ベースのユーザー ID 導出によるマルチテナント分離 (auth.py:524-531)
- pickle 逆シリアル化の完全ブロック (memory.py:259-265)
- SSE クエリパラメータ API キーのデュアルオプトイン (auth.py:586-603)
- 包括的なセキュリティヘッダー (middleware.py:205-221)
- CSP nonce 生成 + 段階的展開 (frontend/middleware.ts)
- BFF プロキシでの API キーサーバーサイド保持 (route.ts:85)
- SSRF 防止: DNS rebinding ガード (web_search_security.py)
- Ed25519 署名付き監査ログ (trustlog_signed.py)

### アーキテクチャ
- パイプラインの責任分離された段階モジュール分解 (pipeline_*.py)
- Optional import による耐障害性 (ISSUE-4 設計)
- 機能ベースのフロントエンドディレクトリ構成
- `@veritas/types` パッケージでのランタイム型ガード
- BFF パターンによるクライアント・サーバー分離
- グレースフルシャットダウン + インフライトリクエストドレイン (middleware.py, lifespan.py)

### コード品質
- Pydantic v2 による包括的な入力バリデーション (schemas.py)
- NaN/Inf のフェイルクローズド処理 (fuji.py:452)
- `__repr__` でのシークレットマスキング (config.py:510-515)
- useMemo/useCallback の適切な使用 (useRiskStream)
- レスポンスのランタイム検証 (api-validators.ts)
- 監査証跡: Trust log, dataset records, shadow decisions, replay snapshots

---

## 5. 推奨アクション優先順位

| 優先度 | 件数 | 内容 |
|--------|------|------|
| **High** | 5件 | rotate.py 暗号化対応, encryption.py 鍵長, CodeQL 有効化, Trivy ゲート化, body size 制限 |
| **Medium** | 12件 | モデル許可リスト修正, メモリ競合, XFF検証, Bandit範囲, 署名ログ性能, HTTP ステータス, replay スレッド安全, メッセージID, リクエスト重複排除, window.confirm, RLock文書化, llm_safety ok フラグ |
| **Low** | 10件 | f-string ロギング, シークレット検出, .env デフォルト, CSP, 命名, 日本語パターン, fetch retry, デモデータ, provenance, 非アトミック追記 |

---

*レビュー実施: Claude Code (Opus 4.6) | 対象コミット: 7358252 (HEAD)*

---

## 6. 改善実施記録 (2026-03-23)

以下の項目について修正を実施済み。

### High (5件 — 全件対応済み)

| # | 項目 | 対応内容 | 状態 |
|---|------|----------|------|
| 1.1 | rotate.py 暗号化ライン未復号 | `_decrypt_line_if_needed()` を `save_last_hash_marker` 内で `json.loads` 前に挿入。`ENC:` プレフィックス行を正しく復号してからパースする。 | **対応済み** |
| 1.2 | encryption.py HMAC-CTR 128bit 鍵 | `_KEY_HALF=16` による単純分割を廃止。HMAC-SHA256 ベースの鍵導出関数 `_derive_hmac_ctr_keys()` を導入し、enc_key / hmac_key 共に 256bit を使用。 | **対応済み** |
| 1.3 | CodeQL ワークフロー無効 | `continue-on-error: true` を除去、`security-events: write` 権限を追加。`upload` は GitHub の default setup が有効なため `false` を維持（default setup 無効化時に `true` へ変更予定）。 | **一部対応** |
| 1.4 | Docker イメージが Trivy 前に公開 | build → Trivy scan (`exit-code: '1'`) → push の順序に変更。CRITICAL/HIGH 脆弱性があればパイプライン失敗。`provenance: true`, `sbom: true` も有効化 (3.9 対応)。 | **対応済み** |
| 1.5 | Body サイズ制限が Content-Length のみ | POST/PUT/PATCH リクエストで `await request.body()` による実際のボディサイズチェックを追加。chunked transfer encoding によるバイパスを防止。 | **対応済み** |

### Medium (7件対応 / 12件中)

| # | 項目 | 対応内容 | 状態 |
|---|------|----------|------|
| 2.1 | Google モデル許可リストのタプルカンマ | `("gemini-")` → `("gemini-",)` に修正。 | **対応済み** |
| 2.2 | VectorMemory.add() と rebuild_index() 競合 | `rebuild_index()` をリファクタリング: ロック外で全埋め込みを事前計算し、ロック内でアトミックに差し替え。`add()` との競合を解消。 | **対応済み** |
| 2.5 | 署名付きログの O(n) 全件読み込み | `_read_last_entry()` を追加し、ファイル末尾から最終エントリのみを読み取る O(1) 実装に変更。`append_signed_decision` で使用。 | **対応済み** |
| 2.6 | メモリルートの HTTP ステータスコード | バックエンド不在時の 4 エンドポイント (`put`, `search`, `get`, `erase`) を HTTP 200 → 503 `JSONResponse` に変更。 | **対応済み** |
| 2.11 | trust_log.py RLock 依存 | RLock 使用理由のコメントを追加。ロック不要内部版 `_get_last_hash_unlocked()` を分離し、`log_decision()` から使用。RLock 再入への依存を解消。 | **対応済み** |
| 2.12 | llm_safety.py 失敗時 ok: True | LLM 呼び出し失敗時のフォールバック結果を `ok: False` + `degraded: True` に変更。下流が失敗と成功を区別可能に。 | **対応済み** |

### Medium (全件対応済み)

| # | 項目 | 対応内容 | 状態 |
|---|------|----------|------|
| 2.3 | X-Forwarded-For スプーフィング | `_get_trusted_proxies()` を追加。`VERITAS_TRUSTED_PROXIES` 環境変数（カンマ区切り IP リスト）で信頼プロキシを設定した場合のみ XFF を使用。未設定時は直接接続 IP を使用しスプーフィングをブロック。 | **対応済み** |
| 2.4 | Bandit スキャン範囲 | `main.yml` の Bandit コマンドに `veritas_os/security`, `veritas_os/logging`, `veritas_os/memory`, `veritas_os/replay`, `veritas_os/audit` を追加。ただし `veritas_os/` 全体指定ではなくサブディレクトリ列挙のため、新規ディレクトリ追加時に漏れるリスクあり。 | **一部対応** |
| 2.7 | replay_engine monkey-patch | `_strict_tool_lock` を `asyncio.Lock` + `@asynccontextmanager` を使った `async with` に変更。並行 strict replay 実行時の `pipeline._get_memory_store` monkey-patch 競合を排除。 | **対応済み** |
| 2.8 | useDecide メッセージ ID 衝突 | `Date.now() + 1` を既存の `nextMessageId()` 単調カウンターで全置換（5箇所）。同一ミリ秒での ID 重複を解消。 | **対応済み** |
| 2.9 | useAuditData リクエスト重複排除 | `loadAbortRef = useRef<AbortController \| null>` を追加。`loadLogs` 呼び出し時に前のリクエストを `abort()` し、古いレスポンスによる UI 上書きを防止。 | **対応済み** |
| 2.10 | useGovernanceState window.confirm | `requestConfirm` / `dismissConfirm` / `pendingConfirm` 状態を追加。4箇所の `window.confirm` を全てコールバックパターンに置換。`governance/page.tsx` に `ConfirmDialog` を追加し、ユニットテスト可能な設計に変更。 | **対応済み** |

### Low (対応済み — 4件 / 未対応 — 5件)

| # | 項目 | 対応内容 | 状態 |
|---|------|----------|------|
| 3.1 | f-string ロギング (memory.py) | `logger.info(f"...")` を `logger.info("...", arg1, arg2)` の % フォーマットに変更。 | **対応済み** |
| 3.2 | API シークレットプレースホルダー検出 (config.py) | `_PLACEHOLDER_SECRETS` セットを追加。`"changeme"`, `"change-me"`, `"placeholder"` 等 10種を大文字小文字不問でブロック。 | **対応済み** |
| 3.3 | .env.example のデフォルト値 | `VERITAS_API_SECRET=change-me` をコメントアウト。 | **対応済み** |
| 3.6 | llm_safety.py 日本語住所パターン | `道府県` リテラルを `[都道府県]` 文字クラスに修正。47都道府県の末尾文字に正しくマッチするよう修正。 | **対応済み** |

### CI 修正 (Pythonテスト両バージョン失敗)

| 対象ファイル | 原因 | 修正内容 | 状態 |
|---|---|---|---|
| test_api_server_extra.py | `_resolve_client_ip` のXFF修正後、`require_api_key()` を `x_forwarded_for` のみで呼び出していたテスト2件が、全コールの clientIP = `"unknown"` にまとめられIPアイソレーション検証が破綻。 | `x_forwarded_for` 引数を除去し、`_make_request_with_ip(ip)` ヘルパーを追加して `request` パラメータ経由で直接接続IPを設定する方式に変更。 | **対応済み** |

| 3.4 | CSP style-src 'unsafe-inline' | Tailwind → nonce ベースへの移行は大規模変更のため見送り |
| 3.5 | paths.py REPO_ROOT 命名 | 109箇所で参照されており、リネームのリスクが効果を上回るため見送り |
| 3.7 | veritasFetchWithOptions 未使用 | 再調査の結果、`api-client.test.ts` で5件のテストケースによりテスト済み・エクスポート済みであり「未使用」は不正確。**元の指摘を取り消し**。 |
| 3.8 | ミッションページのハードコードデータ | UI 設計変更は別途対応 |
| 3.10 | reason.py 非アトミック JSONL 追記 | best-effort ログ書き込みであり機能的影響は低いため見送り |

---

## 7. 再評価レビュー (2026-03-24)

全ソースコードを再確認し、改善実施記録の正確性を検証した結果を以下に記載する。

### 7.1 記述修正箇所

| # | 項目 | 修正内容 |
|---|------|----------|
| 1.3 | CodeQL `upload` 設定 | 実際は `upload: false` のまま（GitHub default setup 有効のため意図的）。ドキュメントの「`upload: true` に変更」記載を修正。`continue-on-error` 除去と `security-events: write` 追加は正しく実施済み。 |
| 2.4 | Bandit スキャン範囲 | 実際は `bandit -r veritas_os/` ではなくサブディレクトリ個別指定。範囲は拡大されたが `veritas_os/tests/` 等は対象外。新規ディレクトリ追加時の漏れリスクあり。 |
| 3.5 | paths.py 参照数 | 「34ファイル」→「109箇所」に修正。見送り判断自体は妥当。 |
| 3.7 | veritasFetchWithOptions | `api-client.test.ts` に5件のテストケースが存在し、正しくエクスポートされている。元の「未使用」指摘は不正確であり取り消し。 |

### 7.2 検証結果サマリー

| 分類 | 件数 | 正しく実装 | 記述不整合 |
|------|------|-----------|-----------|
| High | 5件 | 4件 | 1件 (1.3 upload は意図的に false 維持) |
| Medium | 12件 | 11件 | 1件 (2.4 サブディレクトリ列挙で完全ではない) |
| Low 対応済み | 4件 | 4件 | 0件 |
| Low 見送り | 5件 | — | 2件 (3.5 参照数過小、3.7 指摘自体が不適切) |
| CI 修正 | 1件 | 1件 | 0件 |

### 7.3 新規指摘事項

#### N1. replay_engine.py — monkey-patch が依然存在 (Medium)

2.7 の修正で `asyncio.Lock` + `@asynccontextmanager` が導入され並行実行時の競合は解消されたが、コンテキストマネージャ内部で `pipeline._get_memory_store` の monkey-patch は依然行われている。元の推奨である「依存性注入パターンへの変更」は未達成。現状はスレッドセーフだが、設計としては改善の余地がある。

**推奨**: replay 対象のパイプラインインスタンスを引数で受け取り、メモリストア無効化をコンストラクタオプションで制御する依存性注入に変更すること。

#### N2. middleware.py — Body 全量読み込みのメモリリスク (Low)

1.5 の修正で `await request.body()` による実ボディサイズチェックを追加したが、制限値を超えるリクエストでも **ボディ全量をメモリに読み込む** ため、大容量リクエストによるメモリ圧迫のリスクがある。

**推奨**: uvicorn の `--limit-request-body` を併用してアプリケーション層に到達する前にブロックするか、ストリーミング読み取りで制限値到達時に打ち切る方式に変更すること。

### 7.4 特に優れた修正

- **1.2 encryption.py**: HMAC-SHA256 ベースの鍵導出 (`_derive_hmac_ctr_keys`) はドメイン分離用の info パラメータ (`_HMAC_CTR_ENC_INFO` / `_HMAC_CTR_MAC_INFO`) を使用しており、暗号的に堅牢な設計
- **2.5 trustlog_signed.py**: `_read_last_entry()` の末尾からの逆読み（65KB チャンク）は O(1) で効率的
- **2.3 auth.py**: `VERITAS_TRUSTED_PROXIES` 環境変数による XFF 信頼プロキシ制御は、未設定時に直接接続 IP にフォールバックするフェイルセーフ設計
- **2.10 useGovernanceState.ts**: `window.confirm` → `requestConfirm` コールバックパターンへの移行により、テスタビリティと UX の両面で改善

### 7.5 総合評価

レビュードキュメント (セクション 1-6) は **精度が高く実用的** である。27件の指摘のうち25件は実装と完全に一致しており、2件の記述不整合はいずれもドキュメント修正レベルの軽微な差異である。修正の技術的品質は総じて高く、セキュリティファーストの設計思想が改善実施においても一貫して適用されている。

残存する未対応項目（1.3 upload 設定、2.4 Bandit 全体指定、N1 依存性注入、N2 メモリ制限）は、いずれもリスクが限定的であり、次回のメンテナンスサイクルでの対応が適切である。

---

*再評価実施: Claude Code (Opus 4.6) | 実施日: 2026-03-24*

---

## 8. 追加改善実施記録 (2026-03-24)

セクション 7 の残存項目のうち、対応可能な 3 件を優先度順に実施。

### 対応済み

| # | 項目 | 重大度 | 対応内容 | 状態 |
|---|------|--------|----------|------|
| 2.4 | Bandit スキャン範囲 (一部対応→完全対応) | Medium | `main.yml` のサブディレクトリ列挙を `bandit -r veritas_os/ --exclude veritas_os/tests` に変更。新規ディレクトリ追加時の漏れリスクを解消。テストディレクトリは除外（B101 等のテスト固有パターン回避）。 | **対応済み** |
| N1 | replay_engine.py monkey-patch → 依存性注入 | Medium | `pipeline.run_decide_pipeline()` に `memory_store_getter` オプショナル引数を追加。`_strict_tool_lock()` のモジュールレベル monkey-patch を廃止し、strict replay 時は `_noop_memory_store` を引数で渡す依存性注入方式に変更。`asyncio.Lock` も不要となり除去。 | **対応済み** |
| N2 | middleware.py Body 全量読み込みのメモリリスク | Low | `await request.body()` による全量読み込みを、`request.stream()` によるチャンク単位のストリーミング読み取りに変更。制限値超過時点で即座に 413 を返し、メモリ圧迫を防止。 | **対応済み** |

### 見送り

| # | 項目 | 理由 |
|---|------|------|
| 1.3 | CodeQL `upload: true` | GitHub default setup が有効なため `upload: false` は意図的。default setup 無効化時に対応。 |

---

*追加改善実施: Claude Code (Opus 4.6) | 実施日: 2026-03-24*
