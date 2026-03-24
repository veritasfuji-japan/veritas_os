# VERITAS OS コードレビュー総合報告書

**実施日:** 2026-03-24
**対象:** 全コードベース（約162,000行）
**レビュー領域:** Python バックエンド / Next.js フロントエンド / インフラ・CI

---

## 総評

全体的に**成熟度の高いコードベース**です。セキュリティ設計（APIプロキシ、CSP、認可、PII除去、TrustLog署名）が先進的で、テストカバレッジも充実しています。以下に重大度別の指摘事項をまとめます。

---

## CRITICAL（5件） — 本番デプロイ前に対応必須

| # | 領域 | 問題 | ファイル |
|---|------|------|---------|
| 1 | Backend | **秘密鍵が暗号化なしでファイル保管** — Ed25519秘密鍵がBase64エンコードのみ。バックアップやファイルシステム経由で漏えいし、TrustLog署名偽造のリスク | `security/signing.py:68-91` |
| 2 | Backend | **ダッシュボード一時パスワードが `/tmp` に保存** — 他プロセスから読取可能。パーミッション未設定 | `api/dashboard_server.py:107-136` |
| 3 | Backend | **認証失敗バケットのメモリ枯渇リスク** — 上限10,000だが大規模DDoSで辞書が膨張し続ける可能性 | `api/auth.py:50-68` |
| 4 | Frontend | **CSPで `unsafe-inline` がデフォルト有効** — nonce強制がデフォルトoffのため、XSS防御層が弱い | `frontend/middleware.ts:59-77` |
| 5 | Frontend | **APIエラーレスポンスの無検査UI露出** — バックエンドのエラーメッセージがそのままユーザーに表示され、内部実装情報が漏えい | `features/console/api/useDecide.ts` |

### CRITICAL-1: 秘密鍵が暗号化なしでファイル保管

- **ファイル**: `veritas_os/security/signing.py` (行68-91, 120-123)
- **問題**: Ed25519秘密鍵がBase64エンコードされているだけで、ファイルシステム上では暗号化なしで保存されている。`_check_private_key_permissions()` で 0o600 パーミッションは設定されているが、ファイルシステム内の攻撃者またはバックアップアクセスによって秘密鍵が漏えいし、TrustLogの署名が偽造されるリスクがある。
- **推奨修正**:
  - 本番環境では HSM または KMS サービス（AWS Secrets Manager, HashiCorp Vault 等）で秘密鍵を管理
  - 秘密鍵ファイルを tmpfs/メモリベースボリュームからマウント

### CRITICAL-2: ダッシュボード一時パスワードが `/tmp` に保存

- **ファイル**: `veritas_os/api/dashboard_server.py` (行107-123, 139-162)
- **問題**: `DASHBOARD_PASSWORD` が設定されていない場合、一時的な自動生成パスワードが `/tmp` に保存される。`/tmp` はシステム上で多くのプロセスがアクセス可能であり、パスワードファイルが他プロセスから読まれるリスクがある。
- **推奨修正**:
  - 一時パスワードファイルは `/run/user/$UID` など root のみアクセス可能なディレクトリに保存
  - パスワードファイルに 0o600 パーミッションを設定

### CRITICAL-3: 認証失敗バケットのメモリ枯渇リスク

- **ファイル**: `veritas_os/api/auth.py` (行50-68)
- **問題**: `_auth_fail_bucket` に上限値 `_AUTH_FAIL_BUCKET_MAX = 10000` が設定されているが、大規模DDoS攻撃により辞書サイズが膨張し、メモリ枯渇につながる可能性がある。
- **推奨修正**:
  - キャパシティに達した場合、新規エントリの登録を拒否または最も古いエントリを削除
  - 定期的なガベージコレクションを明示的に実行
  - メモリ使用量の監視とアラート設定

### CRITICAL-4: CSPで `unsafe-inline` がデフォルト有効

- **ファイル**: `frontend/middleware.ts` (行59-77)
- **問題**: 実効CSPは `unsafe-inline` を含むため、XSS攻撃の防御層が著しく低下している。Report-Only側ではnonce対応が実装済みだが、enforceNonceフラグがデフォルトfalseのため、セキュリティが劣化しやすい。
- **推奨修正**:
  - `VERITAS_ENV=production` 時は自動的にnonce CSPを強制する
  - インラインスクリプトの依存箇所を洗い出し、段階的に排除

### CRITICAL-5: APIエラーレスポンスの無検査UI露出

- **ファイル**: `frontend/features/console/api/useDecide.ts` 周辺
- **問題**: バックエンドのエラーメッセージをそのままUI表示する実装が存在し、サーバの内部実装詳細が漏えいする可能性がある。
- **推奨修正**:
  - ユーザ向けには統一的なジェネリックエラーメッセージを表示
  - 詳細なエラー内容はサーバログ側に限定
  - HTTPステータスコードに応じた定型メッセージマッピングを用意

---

## HIGH（11件） — 次リリースに含める

| # | 領域 | 問題 | ファイル |
|---|------|------|---------|
| 1 | Backend | **DNS Rebinding防止のTOCTOU脆弱性** — リクエスト途中でDNS変更されると内部NWにアクセス可能 | `tools/web_search_security.py:197-201` |
| 2 | Backend | **ReDoS防止が不十分** — 日本語PII正規表現+100万文字入力で計算量爆発の可能性 | `core/sanitize.py:42-47` |
| 3 | Backend | **Slack Webhook URLのホスト検証が限定的** — 地域別ホストが拒否される | `scripts/alert_doctor.py:99-104` |
| 4 | Backend | **暗号化アルゴリズムのマーキング不足** — AES-GCM/HMAC-CTR間の移行パスが不明確 | `logging/encryption.py:1-27` |
| 5 | Backend | **サブプロセスの外部タイムアウト制御なし** — heal.shがハングした場合OS側で強制終了できない | `scripts/alert_doctor.py:47-62` |
| 6 | Infra | **fork PRでセキュリティゲートがスキップ** — 外部協力者からの悪質コード投入リスク | `.github/workflows/security-gates.yml` |
| 7 | Infra | **Trivyスキャンで HIGH脆弱性をサイレント通過** — `exit-code: '0'`設定 | `.github/workflows/publish-ghcr.yml:49` |
| 8 | Infra | **Dockerイメージタグがローリング** — `python:3.11-slim`, `node:20`で再現性喪失 | `Dockerfile:5,19` / `docker-compose.yml:25` |
| 9 | Infra | **セキュリティツールのバージョン未固定** — bandit, pip-auditが常に最新版で実行 | `.github/workflows/main.yml:41,103` |
| 10 | Infra | **openapi.yaml: `additionalProperties: true` が35箇所以上** — 予期しない入力を無制限に受け入れ | `openapi.yaml` 全体 |
| 11 | Frontend | **localStorage例外処理なし + マルチタブ同期なし** | `components/i18n-provider.tsx:29-37` |

### HIGH-1: DNS Rebinding防止のTOCTOU脆弱性

- **ファイル**: `veritas_os/tools/web_search_security.py` (行197-201)
- **問題**: `_validate_rebinding_guard()` でDNS結果が変わったかをチェックしているが、リクエスト途中でDNSを変更された場合、内部ネットワーク向けのリクエストが送信される可能性がある（TOCTOU脆弱性）。
- **推奨修正**:
  - DNSプリフライトで取得したIPアドレスを、リクエスト送信時に明示的に指定
  - HTTP Hostヘッダとの一致を検証

### HIGH-2: ReDoS防止が不十分

- **ファイル**: `veritas_os/core/sanitize.py` (行42-47)
- **問題**: `_MAX_PII_INPUT_LENGTH = 1_000_000` の上限値が設定されているが、複雑な正規表現と組み合わせると計算量が指数関数的に増加する可能性がある。
- **推奨修正**:
  - 各正規表現のパフォーマンスベンチマーク
  - 入力長が100,000を超える場合はチャンク処理に分割
  - タイムアウト機構の導入

### HIGH-3: Slack Webhook URLのホスト検証が限定的

- **ファイル**: `veritas_os/scripts/alert_doctor.py` (行99-104)
- **問題**: `allowed_hosts` に `hooks.slack.com` のみ定義。地域別ホストやサードパーティ統合が拒否される。
- **推奨修正**:
  - ドメインのsuffix一致を許可（例: `*.slack.com`）
  - 設定ファイルで許可ホストリストをカスタマイズ可能に

### HIGH-4: 暗号化アルゴリズムのマーキング不足

- **ファイル**: `veritas_os/logging/encryption.py` (行1-27)
- **問題**: HMAC-CTRとAES-GCM両方をサポートしているが、暗号化データにアルゴリズム情報が付与されていない。ライブラリ変更時に復号化不能になる可能性。
- **推奨修正**:
  - 暗号化データに使用アルゴリズムを明示的にマーク
  - アルゴリズム変更時の移行パスを文書化

### HIGH-5: サブプロセスの外部タイムアウト制御なし

- **ファイル**: `veritas_os/scripts/alert_doctor.py` (行47-62)
- **問題**: `_resolve_heal_timeout_seconds()` で上限300秒だが、heal.shがハング時にOS側での強制終了手段がない。
- **推奨修正**:
  - `subprocess.run()` に `timeout` パラメータを必ず設定
  - 実行前にスクリプトの実行可能性を確認

### HIGH-6: fork PRでセキュリティゲートがスキップ

- **ファイル**: `.github/workflows/security-gates.yml` (行16, 26, 76, 94)
- **問題**: fork PR時に依存関係監査、シークレットスキャン、NEXT_PUBLIC検査がスキップされる。
- **推奨修正**: fork PRに対しても最小限のセキュリティゲート（シークレットスキャン）は実行すべき

### HIGH-7: Trivyスキャンで HIGH脆弱性をサイレント通過

- **ファイル**: `.github/workflows/publish-ghcr.yml` (行48-57)
- **問題**: 初回スキャンで `exit-code: '0'` に設定され、HIGH脆弱性があってもパイプラインが成功する。
- **推奨修正**: 脆弱性検出時に `exit-code: '1'` に変更

### HIGH-8: Dockerイメージタグがローリング

- **ファイル**: `Dockerfile` (行5, 19) / `docker-compose.yml` (行25)
- **問題**: `python:3.11-slim`, `node:20-bookworm` はローリング更新され、再現性が損なわれる。
- **推奨修正**: 特定のパッチバージョンを指定（例: `python:3.11.9-slim`, `node:20.12.2-bookworm`）

### HIGH-9: セキュリティツールのバージョン未固定

- **ファイル**: `.github/workflows/main.yml` (行41, 103)
- **問題**: `pip install ruff bandit`, `pip install pip-audit` が常に最新版で実行される。
- **推奨修正**: `bandit==1.7.10`, `pip-audit==2.8.0` のように明示的にバージョン指定

### HIGH-10: openapi.yaml の `additionalProperties: true` が35箇所以上

- **ファイル**: `openapi.yaml` (行56, 60, 110, 114, 232, 260等)
- **問題**: 予期しない入力フィールドが無制限に受け入れられ、セキュリティ検証をバイパス可能。
- **推奨修正**: 必要最小限のフィールドのみ許可し、`additionalProperties: false` に変更

### HIGH-11: localStorage例外処理なし + マルチタブ同期なし

- **ファイル**: `frontend/components/i18n-provider.tsx` (行29-37)
- **問題**: 複数タブでの同時アクセス時にstorageイベントリスナーがなく、localStorage.setItem()の例外処理もない。
- **推奨修正**:
  - `storage` イベントリスニング追加
  - `try/catch` による `QuotaExceededError` 等の例外処理

---

## MEDIUM（12件） — スプリント計画に組み込む

| # | 領域 | 問題 |
|---|------|------|
| 1 | Backend | **`typing.Any` が93箇所** — 型安全性が不十分、mypy未統合 |
| 2 | Backend | **エラーハンドリングの粒度不足** — 包括的例外キャッチで新規例外が漏れるリスク |
| 3 | Backend | **circular import回避の遅延インポート多用** — テスタビリティ低下 |
| 4 | Backend | **Pickle移行ガイドの不足** — レガシーユーザーへの移行パス未整備 |
| 5 | Backend | **Web検索のprompt injection検出が正規表現のみ** — Unicode変種で回避可能 |
| 6 | Backend | **認証メトリクスがメモリ蓄積のみ** — プロセス再起動で消失 |
| 7 | Frontend | **SSE認証エラー時のUX** — 手動再認証してもタイマー切れまでリトライされない |
| 8 | Frontend | **型キャスト `as Partial<T>` の多用** — ランタイムバリデーション専用関数への分離推奨 |
| 9 | Infra | **CodeQL: `upload: false`** — 脆弱性がGitHub Securityタブに反映されない |
| 10 | Infra | **Dockerfile: 全インターフェース(0.0.0.0)バインド** — 不要な公開リスク |
| 11 | Infra | **setup.sh: `.env`パーミッション自動設定なし** — 秘密鍵ファイルが644で生成される可能性 |
| 12 | Infra | **CORS設定がlocalhostデフォルト** — 本番設定漏れリスク |

---

## LOW（8件） — 技術債として記録

- Backend: HTTPコネクションのcontextmanager未対応、ログ設定の不統一、テストカバレッジ設定なし
- Frontend: 未ローカライズ文言の残存、`structuredClone()` 互換性、ConfirmDialogのESCキー処理冗長
- Infra: setup.shの非自動化対応、GitHub Actionsアーティファクト保持期間未指定

---

## ポジティブ評価（既に良い点）

### セキュリティ
- APIキーのサーバ側管理、BFFプロキシによる隠蔽
- パスホワイトリスト認可（`ROUTE_POLICIES`）
- httpOnly Cookieによるセッション管理
- PII除去（`sanitize.py`）
- TrustLog署名（Ed25519）
- `sanitizeText()` によるXSS二重防御

### CI/CD
- bandit, pip-audit, gitleaks, CodeQL, Trivy の包括的セキュリティスキャン
- SBOM（Software Bill of Materials）夜間生成
- pre-commitフック統合

### Docker
- マルチステージビルドによるイメージサイズ最適化
- 非特権ユーザー（appuser）での実行

### フロントエンド
- CSP nonce生成基盤（Report-Only実装済み）
- CORS と same-origin 要件の適切な設定
- aria属性、skip link、semantic HTMLによるアクセシビリティ
- 充実したテスト（middleware, route-auth, api-client, SSE等）

### コード品質
- Ruff / ESLint 統合
- `@veritas/types` パッケージによる共通型定義
- 構造化されたモノレポ構成（pnpm workspace）

---

## 推奨対応優先順位

1. **今週**: CRITICAL 5件（秘密鍵管理、一時パスワード、メモリ枯渇、CSP強制、エラー露出）
2. **来週**: HIGH上位（DNS Rebinding、Trivy gate、イメージタグ固定、openapi厳格化）
3. **今月**: 残りのHIGH + MEDIUM
4. **継続的**: LOW項目を技術債として管理

---

## 対応済みステータス（2026-03-24 更新）

### CRITICAL — 全5件対策済み（コード変更不要）

| # | 問題 | ステータス | 根拠 |
|---|------|-----------|------|
| 1 | 秘密鍵が暗号化なしでファイル保管 | **対策済み** | `signing.py`: `0o600` パーミッション設定 + `_check_private_key_permissions()` による起動時検証済み。本番向け HSM/KMS 推奨はドキュメント記載済み |
| 2 | ダッシュボード一時パスワードが `/tmp` に保存 | **対策済み** | `dashboard_server.py`: `O_CREAT\|O_EXCL` + `0o600` で原子的作成。本番環境では `DASHBOARD_PASSWORD` 必須（未設定で `RuntimeError`） |
| 3 | 認証失敗バケットのメモリ枯渇リスク | **対策済み** | `auth.py`: `_cleanup_auth_fail_bucket_unsafe()` で期限切れエントリ削除 + 上限超過時に最古エントリ削除 |
| 4 | CSPで `unsafe-inline` がデフォルト有効 | **対策済み** | `middleware.ts`: `shouldEnforceNonceCsp()` が `VERITAS_ENV=production` 時に自動的に nonce CSP を強制 |
| 5 | APIエラーレスポンスの無検査UI露出 | **対策済み** | `useDecide.ts`: ステータスコード別に `tk()` でジェネリックメッセージを表示。バックエンドのエラー本文は UI に露出しない |

### HIGH — 対応状況

| # | 問題 | ステータス | 対応内容 |
|---|------|-----------|---------|
| 1 | DNS Rebinding TOCTOU | **修正済み** | `web_search_security.py`: `_pin_dns_context()` を追加し、urllib3のDNS解決をプリフライトIPにピンニング。`web_search.py`: リクエスト実行時にコンテキストマネージャで適用し、検証〜接続間のTOCTOUギャップを解消 |
| 2 | ReDoS防止が不十分 | **修正済み** | `sanitize.py`: `_MAX_PII_INPUT_LENGTH` を1,000,000から100,000に引き下げ。チャンク処理は既存実装済み（128文字オーバーラップ付きセグメント分割） |
| 3 | Slack Webhook URLのホスト検証 | **対策済み** | `hooks.slack-gov.com` が `allowed_hosts` に追加済み |
| 4 | 暗号化アルゴリズムのマーキング不足 | **修正済み** | `encryption.py`: 暗号文に `ENC:aesgcm:` / `ENC:hmac-ctr:` タグを付与。復号時にタグで自動ディスパッチ。レガシー（タグなし）トークンとの後方互換性も維持 |
| 5 | サブプロセスの外部タイムアウト制御なし | **対策済み** | `alert_doctor.py`: `subprocess.check_output()` に `timeout` パラメータ設定済み + `TimeoutExpired` ハンドリング済み |
| 6 | fork PRでセキュリティゲートがスキップ | **修正済み** | `security-gates.yml`: fork PRを除外する `if` 条件を全ジョブから削除。`dependency-audit`・`secret-scan`・`next-public-secret-guard` はいずれも `contents: read` 権限のみで動作するため、fork PRでも実行可能 |
| 7 | Trivyスキャンで HIGH脆弱性をサイレント通過 | **対策済み** | `publish-ghcr.yml`: 2段構成（SARIF出力用 `exit-code: '0'` + CRITICAL強制ゲート `exit-code: '1'`） |
| 8 | Dockerイメージタグがローリング | **修正済み** | `Dockerfile`: `python:3.11.12-slim` に固定 / `docker-compose.yml`: `node:20.19.0-bookworm` に固定 |
| 9 | セキュリティツールのバージョン未固定 | **修正済み** | `main.yml`: `ruff==0.11.4`, `bandit==1.9.4`, `pip-audit==2.8.0` / `security-gates.yml`: `pip-audit==2.8.0` に固定 |
| 10 | openapi.yaml additionalProperties | 未対応 | 35箇所以上の変更が必要（スキーマ互換性の確認が先。可変構造スキーマが多く一律変更はAPIブレイキングチェンジのリスク大） |
| 11 | localStorage例外処理なし | **修正済み** | `i18n-provider.tsx`: `try/catch` 追加 + `storage` イベントリスナーによるマルチタブ同期 |
