# Veritas OS Repository Precision Review Report

**Date:** 2026-04-07  
**Scope:** Full repository (937 files)  
**Reviewed Areas:** Python Core, Frontend (TypeScript/React), Tests & CI/CD, Policies & Security

---

## Executive Summary

| Severity | Count |
|----------|-------|
| Critical | 3 |
| High     | 12 |
| Medium   | 16 |
| Low      | 12 |
| **Total** | **43** |

最も緊急性の高い問題は、**未認証の SSE イベントストリーム**、**暗号化テストの例外マスキング**、**CI テスト失敗の見落とし**です。

---

## 1. Security (セキュリティ)

### [CRITICAL] S-1: Unauthenticated SSE Event Stream
- **File:** `veritas_os/api/routes_system.py:495-520`
- **Issue:** `/v1/events` エンドポイントに認証がない。ガバナンス更新、Trust Log 追記、コンプライアンスアラートなどの機密イベントが未認証クライアントに公開される。WebSocket の `/v1/ws/trustlog` は認証済みだが、REST SSE は未保護。
- **Fix:** `@events_router.get("/v1/events", dependencies=[Depends(require_api_key_header_or_query)])` を追加。

### [HIGH] S-2: Governance RBAC Can Be Disabled Without Safe Defaults
- **File:** `veritas_os/api/routes_governance.py:36-59`
- **Issue:** `VERITAS_GOVERNANCE_ENFORCE_RBAC=0` で RBAC を無効化すると、全ガバナンスエンドポイントが無制限にアクセス可能になる。警告ログのみで、ブロックしない。
- **Fix:** Fail-closed アプローチ: RBAC 無効時はエラーを返すか、エンドポイント単位の明示的オプトインを要求。

### [HIGH] S-3: Missing Security Definitions in OpenAPI Schema
- **File:** `openapi.yaml` (multiple endpoints)
- **Issue:** `/v1/compliance/config`、`/v1/system/halt`、`/v1/events` など複数のセンシティブなエンドポイントで OpenAPI 上のセキュリティ要件が未定義。自動生成クライアントが保護なしでアクセスする可能性あり。
- **Fix:** 全保護エンドポイントに `security: [ApiKeyAuth: []]` を追加。

### [HIGH] S-4: Chainlit App Missing Input Validation
- **File:** `chainlit_app.py:68, 365`
- **Issue:** ユーザー入力が `strip()` のみで `/v1/decide` API に直接転送される。Null バイト、制御文字、長さ制限のチェックなし。
- **Fix:** `MAX_QUERY_LENGTH` チェック、制御文字バリデーションを追加。

### [MEDIUM] S-5: Regex DoS Protection Incomplete
- **File:** `veritas_os/policy/evaluator.py:111-141`
- **Issue:** パターン長 256 文字制限とネストされた量指定子のガードがあるが、`(a+)+b` のような短いパターンでの壊滅的バックトラッキングに対応できない。正規表現実行にタイムアウトなし。
- **Fix:** `regex` ライブラリのタイムアウトサポートを使用するか、`signal.alarm` を追加。

### [MEDIUM] S-6: Policy Scope Missing Context Defaults to "allow"
- **File:** `veritas_os/policy/evaluator.py:150-167, 296`
- **Issue:** スコープコンテキスト (`domain`, `route`, `actor`) が欠落するとポリシーがスキップされ、デフォルトで "allow" が返される。
- **Fix:** クリティカルドメインでポリシーマッチがない場合は "halt" にエスカレーションを検討。

### [MEDIUM] S-7: Missing Minimum Evidence Enforcement
- **File:** `veritas_os/policy/evaluator.py:287-318`
- **Issue:** `required_evidence: []` のポリシーはエビデンスチェックを完全にバイパスする。
- **Fix:** 高リスクルートにはグローバル最小エビデンス要件を設定。

### [MEDIUM] S-8: Chainlit Error Logs Expose Query Content
- **File:** `chainlit_app.py:379`
- **Issue:** `logger.error("VERITAS API call failed for query=%r: %r", query, e)` でクエリ内容がログに記録される。PII 漏洩リスク。
- **Fix:** ログにはリクエスト ID のみ記録し、クエリ本文は除外。

---

## 2. Python Core (コアロジック)

### [HIGH] P-1: Silent JSON Extraction Failure
- **File:** `veritas_os/core/utils.py:291-298`
- **Issue:** `_extract_json_object()` が `ValueError` / `json.JSONDecodeError` を捕捉し、空文字列を返すが、エラーをログに記録しない。本番環境でのデバッグが困難。
- **Fix:** `except` ブロック内に `logger.debug()` を追加。

### [HIGH] P-2: Global State Counters with Fragile Lock Pattern
- **File:** `veritas_os/logging/trust_log.py:90-92, 466-474`
- **Issue:** `_append_success_count` / `_append_failure_count` がグローバル変数 + `threading.Lock` で管理されている。リファクタリング時に `global` 宣言が欠落するとレースコンディションが発生する。
- **Fix:** クラスベースのアプローチまたは `threading.Lock` 付きの専用カウンタクラスに変更。

### [MEDIUM] P-3: Incomplete Exception Handling in Memory Store
- **File:** `veritas_os/core/memory/memory_store.py:132-142`
- **Issue:** `_load_all()` が `json.JSONDecodeError` と `OSError` を捕捉するが、`_normalize()` の例外は未処理でそのまま伝播する。
- **Fix:** `_normalize()` 呼び出しを含むスコープに例外ハンドラを拡張。

### [MEDIUM] P-4: Complex While-True Loop in Trust Log Recovery
- **File:** `veritas_os/logging/trust_log.py:234-254, 285-302`
- **Issue:** ファイル後方シーク用の `while True` ループが複雑で、保守性が低い。ロジック自体は正しいが、意図が不明確。
- **Fix:** ループをヘルパーメソッドに抽出し、各分岐にコメント追加。

### [LOW] P-5: Magic Number for Recursion Depth
- **File:** `veritas_os/core/utils.py:350`
- **Issue:** `redact_payload()` の最大再帰深度 `50` がハードコードされている。
- **Fix:** `MAX_REDACTION_DEPTH = 50` 定数に抽出。

---

## 3. Frontend (フロントエンド)

### [HIGH] F-1: Race Condition in SSE Stream Parsing
- **File:** `frontend/components/live-event-stream.tsx:180-268`
- **Issue:** `mounted` フラグは外側の `while` ループでのみチェックされる。`reader.read()` の内部ループ中にコンポーネントがアンマウントされると、不要なストリーム読み取りが継続する。
- **Fix:** 内部 SSE パースループの各 `reader.read()` 後に `mounted` チェックを追加。

### [HIGH] F-2: Set State Mutation Risk
- **File:** `frontend/components/live-event-stream.tsx:172-174`
- **Issue:** React state に `Set` オブジェクトを使用。`Set` は参照等価性の問題があり、Strict Mode での再レンダリングが不安定になる可能性あり。
- **Fix:** `Record<string, true>` またはイミュータブルなデータ構造に変更。

### [HIGH] F-3: Swallowed Error Details in useGovernanceState
- **File:** `frontend/app/governance/hooks/useGovernanceState.ts:93-94, 153-154`
- **Issue:** `catch` ブロックでエラー詳細が破棄される。ユーザーにはジェネリックメッセージが表示されるが、実際のエラーがログに記録されない。
- **Fix:** `console.error(err)` を追加してからユーザー向けメッセージを設定。

### [MEDIUM] F-4: Missing Null Checks in FujiRulesEditor
- **File:** `frontend/app/governance/components/FujiRulesEditor.tsx:22-24`
- **Issue:** `draft.fuji_rules[key]` のネストプロパティアクセスに null チェックなし。
- **Fix:** Optional chaining または null coalescing を追加。

### [MEDIUM] F-5: Unsafe Type Assertions in DiffPreview
- **File:** `frontend/app/governance/components/DiffPreview.tsx:18-19`
- **Issue:** `as unknown as Record<string, unknown>` でTypeScript の型安全性をバイパス。
- **Fix:** ランタイムバリデーションに変更。

### [MEDIUM] F-6: Missing SSE Error Case Tests
- **File:** `frontend/components/live-event-stream.test.tsx`
- **Issue:** 不正 JSON、ネットワークエラー、不完全な SSE メッセージ、再接続バックオフのテストケースが欠如。
- **Fix:** エラーシナリオのテストを追加。

### [MEDIUM] F-7: Missing Input Validation in TraceabilityRail
- **File:** `frontend/components/traceability-rail.tsx:35-47`
- **Issue:** `request_id` にフォーマットバリデーションなし。`encodeURIComponent` は使用されているが、期待フォーマット ("req-" prefix) のチェックがない。
- **Fix:** パターンバリデーションを追加。

### [LOW] F-8: Array Index as Key in LoadingSkeleton
- **File:** `frontend/components/ui/loading-skeleton.tsx:15-21`
- **Issue:** `key={i}` パターン。スケルトンコンポーネントでは実害は少ないが、ベストプラクティスに反する。

### [LOW] F-9: Hardcoded Locale in AppShell Skip Link
- **File:** `packages/design-system/src/app-shell.tsx:26`
- **Issue:** "メインコンテンツへスキップ" が日本語ハードコード。i18n システムを使用すべき。

---

## 4. Tests & CI/CD (テスト・CI/CD)

### [CRITICAL] T-1: CI Test Failures Can Be Silently Ignored
- **File:** `.github/workflows/main.yml:189-227`
- **Issue:** pytest ステップが `continue-on-error: true` を使用。後続の条件チェックで失敗を検出するが、このチェックが削除されるとテスト失敗が見落とされる。
- **Fix:** `continue-on-error: true` を削除し、テスト失敗で直接ジョブを失敗させる。

### [CRITICAL] T-2: Encryption Test Masks Crypto Bugs
- **File:** `veritas_os/tests/test_production_encryption.py:154-159`
- **Issue:** `test_different_keys_cannot_decrypt` が `except Exception: pass` を使用。復号が成功しても（暗号バグ）テストが通過する。
- **Fix:** `with pytest.raises(Exception):` に変更するか、結果が元テキストと異なることを明示的にアサート。

### [HIGH] T-3: Overly Broad Exception Catching in Encryption Tests
- **File:** `veritas_os/tests/test_production_encryption.py:85-86, 103-104`
- **Issue:** `(EncryptionKeyMissing, RuntimeError, Exception)` を捕捉。`AttributeError` などの予期しない例外も通過する。
- **Fix:** 期待する例外型のみに限定: `pytest.raises(EncryptionKeyMissing)`。

### [HIGH] T-4: Missing Docker Build Cache
- **File:** `.github/workflows/publish-ghcr.yml:38-47`
- **Issue:** Docker build-push-action にキャッシュ設定なし。毎ビルドで全レイヤーを再構築。
- **Fix:** `cache-from: type=gha` / `cache-to: type=gha,mode=max` を追加。

### [HIGH] T-5: requirements.txt / pyproject.toml Sync Not Validated
- **File:** `veritas_os/requirements.txt`, `pyproject.toml`
- **Issue:** `requirements.txt` が `pyproject.toml[full]` と同期されていることを保証する自動チェックがない。バージョンドリフトのリスク。
- **Fix:** CI に `pip-compile` ベースの同期チェックステップを追加。

### [MEDIUM] T-6: Frontend Security Check Without Error Handling
- **File:** `.github/workflows/main.yml:287-293`
- **Issue:** `NEXT_PUBLIC_*KEY` ガードが `rg` コマンドに依存するが、ripgrep のインストール確認なし。
- **Fix:** `which rg || apt-get install -y ripgrep` またはフォールバック。

### [MEDIUM] T-7: Docker Layer Cache Invalidation Order
- **File:** `Dockerfile:8-54`
- **Issue:** `apt-get upgrade` がアプリケーションコードのコピー後にあるため、コード変更でシステムパッケージキャッシュも無効化される。
- **Fix:** システム操作をアプリケーションコードコピーの前に移動。

### [MEDIUM] T-8: Inconsistent Coverage Threshold Enforcement
- **File:** `.github/workflows/main.yml:159, 201`
- **Issue:** カバレッジ閾値 85% が CI でのみ検証され、ローカル開発では確認されない。
- **Fix:** pre-commit フックにカバレッジ検証を追加。

### [LOW] T-9: Hardcoded /tmp Path in Snapshot Script
- **File:** `scripts/take_frontend_snapshot.sh:22, 43`
- **Issue:** `/tmp/frontend-dev.log` がハードコード。`${TMPDIR:-/tmp}` を使用すべき。

### [LOW] T-10: Missing Dev Dependencies in pyproject.toml
- **File:** `setup.sh:114-116`, `pyproject.toml`
- **Issue:** `pytest`, `pytest-cov` 等の開発依存が `pyproject.toml` に `[project.optional-dependencies] dev` として定義されていない。

### [LOW] T-11: .env.example Contains Invalid Model Name
- **File:** `.env.example:9`
- **Issue:** `LLM_MODEL=gpt-4.1-mini` は存在しないモデル名。`gpt-4o-mini` が正しい可能性あり。

---

## Priority Action Items (優先対応事項)

### Immediate (今すぐ)
1. **S-1:** `/v1/events` に認証を追加
2. **T-1:** CI の `continue-on-error: true` を削除
3. **T-2:** 暗号化テストの例外処理を修正

### Short-term (1-2 weeks)
4. **S-2:** RBAC 無効化時の fail-closed 動作に変更
5. **S-4:** Chainlit 入力バリデーション追加
6. **F-1:** SSE ストリームの `mounted` チェック強化
7. **T-4:** Docker ビルドキャッシュ設定
8. **T-5:** requirements.txt 同期チェック

### Medium-term (1 month)
9. **S-3:** OpenAPI セキュリティ定義の網羅
10. **S-5:** 正規表現 DoS 保護強化
11. **F-3:** エラーハンドリング改善
12. **T-7:** Dockerfile レイヤー順序最適化

---

*This review was conducted on the full repository at commit `d7a57ee`.*
