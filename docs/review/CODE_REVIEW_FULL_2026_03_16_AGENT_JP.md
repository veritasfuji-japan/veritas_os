# VERITAS OS 完成度レビュー（バックエンド + フロントエンド全体）

- 日付: 2026-03-16
- レビュー方法:
  - バックエンド (`veritas_os/**/*.py`) とフロントエンド (`frontend/**/*.ts`, `frontend/**/*.tsx`) の全ファイルを機械走査
  - コア責務ファイル（Planner/Kernel/Fuji/MemoryOS, API/BFF, Middleware）を精読
  - 自動テストとセキュリティ/責務境界チェッカーを実行

---

## エグゼクティブサマリー

**総合完成度: 86/100（実運用直前レベル）**

- **バックエンド: 87/100**
  - 3789 tests pass の土台は非常に強い
  - Pipeline/FUJI/Memory/監査ログ/Replay が実装済み
  - 一方で `api/server.py`, `core/memory.py`, `core/fuji.py` の巨大化が継続しており、保守性と変更リスクを押し上げている
- **フロントエンド: 84/100**
  - 140 tests pass、BFF + CSP + trace_id の防御設計は良い
  - 主要画面（Console/Audit/Governance/Risk）が機能単位で揃っている
  - ただし CSP が互換モードでは `unsafe-inline` を残しており、厳格運用はフラグ依存

---

## 根拠（コードベース事実）

1. プロジェクトは「In Development」ステータスで明示。README でも「production-approaching governance infrastructure」と位置付け。  
2. パイプラインは責務分離モジュール群（inputs/execute/policy/response/persist/replay）へ分割済みで、単一エントリポイントを維持。  
3. FUJI は deny/hold/allow の不変条件と fail-closed 的思想をコメントで明示し、実装上も安全寄り。  
4. MemoryOS は pickle 実行をランタイムでブロックし、RCEリスクを警告する設計。  
5. フロントエンド BFF で API キーをサーバ側に閉じ、経路制限・ロール制御・body size 制限・trace_id 伝搬を実装。  
6. Middleware は CSP nonce 配布・httpOnly BFF cookie・各種セキュリティヘッダを実装。  
7. Planner / Kernel / Fuji / MemoryOS の責務境界チェックが専用スクリプトで維持され、レビュー時実行でも pass。

---

## セキュリティ評価（必須警告を含む）

### 良い点
- BFF で API 秘密情報がブラウザへ露出しにくい設計
- Memory の pickle 廃止方針がコードで強制
- リスクの高い subprocess shell / raw upload / public key exposure / runtime pickle を専用スクリプトで検査可能

### 警告（運用上の注意）
1. **Auth store failure mode を `open` にすると、nonce登録失敗時に通過する設計が存在**。本番では `closed` 固定が望ましい。  
2. **CSP はデフォルト互換モードで `unsafe-inline` を残すため、厳格なXSS耐性は nonce 強制フラグ依存**。段階導入後は strict 常時化を推奨。  
3. **BFF が `NEXT_PUBLIC_VERITAS_API_BASE_URL` をフォールバック参照**するため、運用ミスで公開側環境変数に内部構成を載せる余地がある。`VERITAS_API_BASE_URL` 専用運用へ寄せると安全。

---

## 完成度内訳（5段階）

- 機能網羅性: **4.5/5**
- 品質保証（テスト）: **5.0/5**
- セキュリティ基盤: **4.0/5**
- 保守性/可読性: **3.5/5**
- 運用準備（監査/可観測性/ガバナンス）: **4.5/5**

---

## 優先度つき改善提案（責務境界を越えない範囲）

### P0（直近）
- `VERITAS_AUTH_STORE_FAILURE_MODE` を本番プロファイルで `closed` 強制
- `VERITAS_CSP_ENFORCE_NONCE=true` の本番既定化（互換検証完了後）
- `NEXT_PUBLIC_VERITAS_API_BASE_URL` 依存を運用ガイドで禁止

### P1（次スプリント）
- `api/server.py` の機能分割（ルータ層・監査層・ヘルス/メトリクス層）
- `core/memory.py` / `core/fuji.py` のサブモジュール化をさらに進める

### P2（継続改善）
- フロントE2E（Playwright）を CI 標準ゲートへ強化
- 既存の豊富なレビュー文書群を「最新1本 + 変更差分」に再編成し、運用判断を簡素化

---

## 結論

VERITAS OS は、**監査可能性・安全ゲート・再現性・ガバナンス UI** の主要要件が実装済みで、テスト密度も高い。現時点の完成度は「実運用直前」だが、

- Auth failure fail-open 設定余地の封じ込み
- CSP strict 化
- 巨大モジュールの分割による変更安全性向上

を完了すれば、運用品質はさらに安定する。

---

## 改善実施ログ（2026-03-16 / 高優先度順）

### 1) P0: Auth store failure mode の本番 fail-closed 強制（完了）
- 変更内容:
  - `veritas_os/api/auth.py` の `_auth_store_failure_mode()` を強化し、`VERITAS_ENV=prod|production` の場合は `VERITAS_AUTH_STORE_FAILURE_MODE` の値に関わらず `closed` を返すようにした。
- 目的:
  - 本番での設定ミス（`open`）による認証/nonce/rate-limit 迂回リスクを排除。
- テスト:
  - `veritas_os/tests/test_auth_core.py` に「production では open 指定でも closed を返す」ケースを追加。
- セキュリティ警告:
  - 非本番環境では `open` 許可仕様が残るため、検証時に本番相当の挙動が必要なら `VERITAS_ENV=production` を明示すること。

### 2) P0: CSP nonce strict の本番既定化（完了）
- 変更内容:
  - `frontend/middleware.ts` の `shouldEnforceNonceCsp()` を強化し、`VERITAS_ENV` または `NODE_ENV` が `prod|production` の場合は `VERITAS_CSP_ENFORCE_NONCE` 未設定でも strict（nonce 必須）を有効化。
- 目的:
  - 本番で `unsafe-inline` が残る構成を既定で防止し、XSS耐性を引き上げる。
- テスト:
  - `frontend/middleware.test.ts` に production 既定 strict のテストを追加。
- セキュリティ警告:
  - strict 化により、nonce 未対応のインラインスクリプトは本番で実行不可になる。デプロイ前に対象ページのランタイム検証を必ず実施すること。

### 3) P0: `NEXT_PUBLIC_VERITAS_API_BASE_URL` 依存の排除（完了）
- 変更内容:
  - `frontend/app/api/veritas/[...path]/route.ts` で API ベースURL解決を `VERITAS_API_BASE_URL` のみに限定。
  - `resolveApiBaseUrl()` を追加し、未設定/空文字時のみ `http://localhost:8000` を使うよう明確化。
- 目的:
  - 公開プレフィックス環境変数（`NEXT_PUBLIC_*`）への誤設定による内部構成露出リスクを低減。
- テスト:
  - `frontend/app/api/veritas/[...path]/route.test.ts` に、server-only env 優先と localhost フォールバックのテストを追加。
- セキュリティ警告:
  - `VERITAS_API_BASE_URL` 未設定のまま本番起動すると localhost フォールバックにより意図しない接続先となる。運用では必ず明示設定すること。

### 4) フォローアップ: Next.js Route export 制約への適合（完了）
- 背景:
  - `app/api/veritas/[...path]/route.ts` で `resolveApiBaseUrl` を named export した結果、Next.js の Route export 制約によりビルド失敗。
- 変更内容:
  - `resolveApiBaseUrl()` を `route-config.ts` に移設し、`route.ts` は許可された Route handler export のみを保持。
  - 既存テストは `route-config.ts` を参照するよう更新。
- セキュリティ警告:
  - BFF設定は引き続き `VERITAS_API_BASE_URL`（server-only）で管理し、`NEXT_PUBLIC_*` への再回帰を禁止すること。

### 5) フォローアップ: frontend quality gate の失敗可視性改善（完了）
- 背景:
  - `Run frontend quality gate` を `continue-on-error: true` で実行後、後段の `Fail job if frontend quality gate failed` が `exit 1` を返すため、失敗理由がサマリ上で不透明になっていた。
- 変更内容:
  - `frontend-quality-gate` ジョブの gate 実行ステップを fail-fast（標準失敗）へ変更し、失敗箇所を直接表示。
  - `Fail job if frontend quality gate failed` の冗長ステップを削除。
  - Playwright 失敗アーティファクトは `if: failure() && matrix.gate == 'e2e'` で維持。
- セキュリティ警告:
  - quality gate を迂回しない運用を継続すること。失敗時は警告（未使用変数等）を放置せず、lint/test/e2e の根本原因を修正してからマージすること。

### 6) フォローアップ: frontend e2e の Playwright browser 解決失敗を修正（完了）
- 背景:
  - CI の `frontend-e2e` で `Executable doesn't exist ... chromium_headless_shell` が発生し、quality gate が失敗。
- 変更内容:
  - e2e 用ブラウザインストールを `pnpm exec playwright install --with-deps chromium chromium-headless-shell` に変更。
  - `chromium` と `chromium-headless-shell` の両方を明示し、Playwright の起動ターゲット不一致を回避。
- セキュリティ警告:
  - E2E が失敗した状態で quality gate を bypass しないこと。UI 改修時は必ず e2e 証跡（report / trace）を確認してからマージすること。

### 7) フォローアップ: frontend-e2e 失敗（CSP strict 強制回帰）を修正（完了）
- 背景:
  - `shouldEnforceNonceCsp()` が `NODE_ENV=production` でも strict 化していたため、Next.js の本番ビルド/e2e 実行で互換モード前提のインライン初期化スクリプトがブロックされ、smoke/axe が連鎖失敗。
- 変更内容:
  - strict 既定化の本番判定を `VERITAS_ENV=prod|production` のみに限定。
  - `NODE_ENV=production` 単独では strict を強制しない仕様へ戻し、CI/e2e の安定性を回復。
  - `frontend/middleware.test.ts` に `NODE_ENV=production` 単独では false を返す回帰テストを追加。
- セキュリティ警告:
  - 本番環境では `VERITAS_ENV=production` を必ず明示すること。未設定だと strict CSP が有効化されず、XSS耐性強化が期待どおりに働かない。

### 8) P0追加: BFF API Base URL の production fail-closed 化（完了）
- 背景:
  - `VERITAS_API_BASE_URL` 未設定時の localhost フォールバックは開発では有用だが、本番では誤接続・誤設定の検知遅延を招く。
- 変更内容:
  - `frontend/app/api/veritas/[...path]/route-config.ts` の `resolveApiBaseUrl()` を `string | null` 化し、`VERITAS_ENV=prod|production` かつ `VERITAS_API_BASE_URL` 未設定時は `null` を返すよう変更。
  - `frontend/app/api/veritas/[...path]/route.ts` で `resolveApiBaseUrl()` の戻り値を毎リクエスト評価し、`null` の場合は 503 (`server_misconfigured`) を返す fail-closed 挙動を追加。
  - `frontend/app/api/veritas/[...path]/route.test.ts` に production 未設定時 `null` を返す回帰テストを追加。
- 目的:
  - 本番環境でのサーバー間通信設定ミスを即時に顕在化し、誤接続による運用・セキュリティ事故を防止。
- セキュリティ警告:
  - `VERITAS_ENV` を production 指定せずに運用すると fail-closed が有効化されない。`VERITAS_ENV=production` と `VERITAS_API_BASE_URL` の明示設定を必須化すること。

### 9) P1着手: `api/server.py` から Trust Log I/O を分離（完了）
- 背景:
  - `api/server.py` はルータ分離後も Trust Log のI/O実装（JSON/JSONL保存、shadow snapshot 書き込み）を内包しており、単一ファイル保守コストが高い。
- 変更内容:
  - `veritas_os/api/trust_log_io.py` を新設し、以下の関心事を抽出。
    - `load_logs_json`（サイズ上限付き安全ロード）
    - `secure_chmod`（機微ファイル権限 0600）
    - `save_json`（集約JSON保存）
    - `append_trust_log_entry`（JSONL + 集約JSONの追記）
    - `write_shadow_decide_snapshot`（`decide_*.json` スナップショット保存）
  - `veritas_os/api/server.py` 側は後方互換API（`_load_logs_json`, `_save_json`, `append_trust_log`, `write_shadow_decide`）を維持したまま、上記モジュールへ委譲する構成に変更。
- テスト:
  - `veritas_os/tests/test_api_trust_log_io.py` を追加し、I/O 抽出モジュールの主要挙動（ロード互換、追記、shadow保存）を単体検証。
- セキュリティ警告:
  - ログファイル権限の強制はベストエフォート（OS/FS制約で `chmod` が失敗し得る）であり、デプロイ環境側でもログ保存先の権限制御を二重化すること。

### 10) P1継続: `core/memory.py` からランタイムセキュリティガードを分離（完了）
- 背景:
  - `core/memory.py` が 2,000 行超の単一モジュールで、メモリ本体ロジックとセキュリティガード（legacy pickle 検知）が混在していた。
- 変更内容:
  - `veritas_os/core/memory_security.py` を新設し、以下を抽出。
    - `is_explicitly_enabled`
    - `emit_legacy_pickle_runtime_blocked`
    - `warn_for_legacy_pickle_artifacts`
  - `veritas_os/core/memory.py` 側は後方互換のため、既存 private 関数名（`_is_explicitly_enabled` など）を薄い委譲ラッパとして維持。
- テスト:
  - `veritas_os/tests/test_memory_security.py` を追加し、truthy env 判定と legacy pickle 検知ログの挙動を検証。
- セキュリティ警告:
  - runtime での pickle/joblib 読み込み禁止は維持されるが、検知はファイル走査ベースのため、運用では `docs/operations/MEMORY_PICKLE_MIGRATION.md` に従い legacy artifact 自体を配置しないこと。

### 11) P1継続: `core/fuji.py` のプロンプトインジェクション責務を専用モジュールへ委譲（完了）
- 背景:
  - `core/fuji.py` 内にプロンプトインジェクション検知ロジック（パターン定義・正規化・ポリシー反映）が重複しており、既存 `core/fuji_injection.py` との二重管理で保守コストが増えていた。
- 変更内容:
  - `veritas_os/core/fuji.py` の `_detect_prompt_injection` / `_normalize_injection_text` を `veritas_os/core/fuji_injection.py` 実装へ委譲。
  - `_build_runtime_patterns_from_policy` のプロンプトインジェクション関連処理を `fuji_injection` の `_build_injection_patterns_from_policy` 呼び出しへ統合し、`fuji.py` 側は PII パターン更新に責務を限定。
  - これに合わせて `fuji.py` 内の重複定数（インジェクションパターン・同形異体文字マップ・zero-width 正規化用正規表現）を削除。
- テスト:
  - `veritas_os/tests/test_fuji_runtime_pattern_delegation.py` を追加し、`fuji._build_runtime_patterns_from_policy()` 経由のランタイム更新が `fuji._detect_prompt_injection()` / `fuji._normalize_injection_text()` に反映されることを回帰検証。
- セキュリティ警告:
  - ルールベース検知はヒューリスティックであり、未知のプロンプトインジェクション亜種を完全に防ぐものではない。YAMLポリシー更新時は検知率だけでなく誤検知率も定期評価すること。

### 12) P1継続: `api/server.py` から startup health 責務を分離（完了）
- 背景:
  - `api/server.py` に起動時の fail-fast 判定・設定検証・ランタイム健全性警告が同居し、起動フロー変更時の影響範囲が広かった。
- 変更内容:
  - `veritas_os/api/startup_health.py` を新設し、以下を抽出。
    - `should_fail_fast_startup`
    - `run_startup_config_validation`
    - `check_runtime_feature_health`
  - `veritas_os/api/server.py` の `_should_fail_fast_startup` / `_run_startup_config_validation` / `_check_runtime_feature_health` は後方互換を維持しつつ、`startup_health` へ委譲する薄いラッパに変更。
- テスト:
  - `veritas_os/tests/test_api_startup_health.py` を追加し、production 判定・fail-fast の再送出・警告ログ出力を単体検証。
- セキュリティ警告:
  - `has_sanitize=False` の警告は検知のみであり、PII漏えい自体を防ぐものではない。警告発生時は sanitize import 失敗の原因を最優先で修復すること。


### 13) P0追加: BFF API Base URL fail-closed 判定に `NODE_ENV=production` を追加（完了）
- 背景:
  - 既存の fail-closed は `VERITAS_ENV=prod|production` 依存のため、環境変数未設定で `NODE_ENV=production` のみ有効なデプロイ形態では localhost フォールバックが残る余地があった。
- 変更内容:
  - `frontend/app/api/veritas/[...path]/route-config.ts` の `resolveApiBaseUrl()` で production 判定に `NODE_ENV=production` を追加。
  - これにより `VERITAS_API_BASE_URL` が未設定なまま本番相当環境で起動した場合は `null` を返し、ルート側の既存 503 fail-closed を確実に発火。
  - `frontend/app/api/veritas/[...path]/route.test.ts` に `NODE_ENV=production` 単独時に `null` を返す回帰テストを追加。
- 目的:
  - 本番設定漏れ時の誤接続（localhost への意図しない転送）を追加条件でも遮断し、BFF の server-to-server 通信をより安全にする。
- セキュリティ警告:
  - fail-closed は「可用性より安全性を優先」するため、`VERITAS_API_BASE_URL` 未設定時は 503 を返す。リリース前に必ず環境変数注入を検証すること。

### 14) P1継続: `api/server.py` から CORS 設定解決責務を分離（完了）
- 背景:
  - `api/server.py` に CORS の正規化・安全判定ロジックが直書きされ、起動/bootstrap とセキュリティ判定の関心事が混在していた。
- 変更内容:
  - `veritas_os/api/cors_settings.py` を新設し、`resolve_cors_settings()` を実装。
    - origin リストの正規化
    - 不正型入力時の fail-closed（`[], False`）
    - wildcard (`*`) 検知時の `allow_credentials=False` 強制
  - `veritas_os/api/server.py` の `_resolve_cors_settings()` は後方互換を維持した薄い委譲ラッパに変更。
- テスト:
  - `veritas_os/tests/test_api_cors_settings.py` を追加し、wildcard 拒否、明示 origin 許可、非 iterable 設定の fail-closed を単体検証。
- セキュリティ警告:
  - wildcard 設定時は認証情報付き CORS を禁止する実装を維持しているが、`allow_origins=["*"]` 自体は公開 API 面を広げる。運用では可能な限り明示オリジン列挙を用いること。
