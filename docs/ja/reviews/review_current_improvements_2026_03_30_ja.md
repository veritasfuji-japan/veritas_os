# VERITAS OS 改善点レビュー（2026-03-30）

## レビュー方針

- 対象: API / Frontend / 運用設定 / セキュリティ境界。
- 制約: Planner / Kernel / Fuji / MemoryOS の責務境界は変更提案で侵害しない。
- 目的: 現在の改善が必要な点を、影響度・難易度付きで優先順位化する。

## 現在の改善ポイント

1. **実効 CSP の互換モードが `unsafe-inline` を許容している**
   - 影響度: **high**
   - 難易度: **medium**
   - 内容: `buildCspEnforced(..., enforceNonce=false)` で `script-src 'unsafe-inline'` を許可している。nonce 強制は本番プロファイルまたは専用フラグに依存しており、移行未完了環境で XSS 耐性が下がる。

2. **SSE / WebSocket の query パラメータ API key 許可が残っている**
   - 影響度: **high**
   - 難易度: **low**
   - 内容: ヘッダ優先設計だが、2段階フラグで query `api_key` を許可できる。ログにも「credential exposure risk」と警告されており、運用ミス時の漏えい面積が大きい。

3. **Dashboard の自動生成パスワードが共有テンポラリファイルに依存**
   - 影響度: **medium**
   - 難易度: **medium**
   - 内容: `tempfile.gettempdir()` 配下固定名ファイルを使用するため、環境によっては資格情報ライフサイクル管理が不明瞭。特に長寿命ノードでは明示ローテーション運用を追加すべき。

4. **CSP の strict rollout 観測がコード外依存（運用ルール依存）**
   - 影響度: **medium**
   - 難易度: **medium**
   - 内容: `Report-Only` は実装済みだが、違反収集→段階強制の自動化がコード上で完結していない。セキュリティ改善が運用成熟度に強く依存している。

5. **改善提案のリポジトリ内「最新」統合ビューが不足**
   - 影響度: **medium**
   - 難易度: **low**
   - 内容: フロントエンドレビュー文書は 2026-03-03 時点で存在するが、全体（API/Memory/運用）を横断する最新版の改善バックログは見当たらない。意思決定の一元化が必要。

6. **責務境界チェックは良好だが、PR 単位の改善テーマ接続が弱い**
   - 影響度: **low**
   - 難易度: **low**
   - 内容: 責務境界チェッカーは CI で実行される一方、出力を改善テーマ（セキュリティ・UX・運用）に自動マッピングする導線が薄い。

## 優先度付きテーマ（次アクション）

1. **認証情報露出面の縮小（最優先）**
   - 対象: Query API key の段階廃止、Dashboard 認証情報の寿命管理方針の明文化。
2. **CSP strict 化の完了**
   - 対象: `unsafe-inline` 依存の完全除去、違反収集の定常運用化。
3. **改善バックログの統合運用**
   - 対象: Frontend/API/Security の指摘を単一フォーマットで管理し、優先順位と担当を固定。

## セキュリティ警告（必読）

- **警告A:** `script-src 'unsafe-inline'` を許容する互換モードは、XSS の影響範囲を拡大する可能性がある。
- **警告B:** SSE / WebSocket で query `api_key` を許可すると、URL 経由で機密情報が漏れるリスクが上がる。
- **警告C:** Dashboard の自動生成パスワードをテンポラリ共有ファイルに保持する方式は、環境によっては資格情報管理監査が難しくなる。

## 2026-03-30 追記（実装済み改善）

### 実施した改善

- **Dashboard 自動生成パスワードの保存先を共有テンポラリ依存から変更**
  - 変更前: `tempfile.gettempdir()` 配下の固定名ファイル。
  - 変更後: 既定で `VERITAS_HOME/runtime_secrets/dashboard_ephemeral_password`（`VERITAS_HOME` 未設定時は `~/.veritas_os/runtime_secrets/dashboard_ephemeral_password`）。
  - 効果: グローバル共有テンポラリでの資格情報混在リスクを低減し、ノード単位での資格情報境界を明確化。

- **資格情報ディレクトリ権限の強化**
  - 共有パスワード格納ディレクトリ作成時に `0700` を強制。
  - 既存ファイル作成時の `0600` と合わせ、ローカル横断参照リスクを抑制。

### 追加テスト

- `VERITAS_HOME` 使用時の既定パス解決テストを追加。
- 共有パスワード用ディレクトリが `0700` で作成されることのテストを追加。

### セキュリティ警告（継続）

- **警告A/B は引き続き有効**: CSP `unsafe-inline` 互換モード、および SSE/WS query `api_key` 許可は依然として高リスク設定。
- **運用推奨**: 本変更後も `DASHBOARD_PASSWORD` の明示設定を優先し、エフェメラル認証は例外運用に限定すること。

### 2026-03-30 追加追記（CodeQL 指摘対応）

- `dashboard_server.py` の権限設定失敗ログで、資格情報ファイルパス（`...password...`）を含む可変値を出力しないよう修正。
- 監査上必要な事象（権限設定失敗）は維持しつつ、ログ上の機微情報露出リスクを低減。
- 単体テストで「警告ログにパス文字列が含まれないこと」を検証。

### 2026-03-30 追加追記（SSE/WS query API key の本番 fail-closed 強化）

- **実施した改善**
  - `VERITAS_ALLOW_*_QUERY_API_KEY` と `VERITAS_ACK_*_QUERY_API_KEY_RISK` の2フラグが同時に有効でも、`VERITAS_ENV=prod|production` または `NODE_ENV=production` では **query API key 認証を無効化** するよう変更。
  - SSE (`/v1/events`) / WebSocket (`/v1/ws/trustlog`) ともに、production runtime ではヘッダ認証（`X-API-Key`）のみ許可する fail-closed 動作へ統一。
  - 本番で query 有効化フラグが誤設定された場合、セキュリティ警告ログを出力して設定無効化を明示。

- **追加テスト**
  - SSE: production runtime では dual opt-in フラグ有効時でも query `api_key` を拒否することを単体テストで検証。
  - WebSocket: production runtime では dual opt-in フラグ有効時でも query `api_key` を拒否することを単体テストで検証。

- **セキュリティ警告（更新）**
  - 開発/検証環境では query API key 許可フラグを有効化すると、引き続き URL 経由の機密情報露出リスクがある。
- 本番環境では fail-closed 化により誤設定耐性を高めたが、運用上は引き続き `X-API-Key` ヘッダ運用を標準とし、query 経路は移行用途に限定すること。

### 2026-03-30 追加追記（CSP `unsafe-inline` 互換モードの本番 fail-closed 強化）

- **実施した改善**
  - CSP 適用判定を見直し、`VERITAS_ENV=prod|production` **または** `NODE_ENV=production` のランタイムでは、nonce ベース CSP を既定で強制するよう変更。
  - 互換モード（`script-src 'unsafe-inline'`）は、`VERITAS_CSP_ALLOW_UNSAFE_INLINE_COMPAT=true` を明示した場合のみ有効化する「一時的エスケープハッチ」へ変更。
  - 本番ランタイムでエスケープハッチが有効な場合は、セキュリティ警告ログを出力して誤運用を可視化。

- **追加テスト**
  - `NODE_ENV=production` 単体でも nonce 強制が有効になることを検証。
  - 本番ランタイムでエスケープハッチを有効化した場合のみ nonce 強制が無効化されることを検証。
  - 本番ランタイムでエスケープハッチ有効時に警告ヘルパー/警告ログが発火することを検証。

- **セキュリティ警告（更新）**
  - `VERITAS_CSP_ALLOW_UNSAFE_INLINE_COMPAT=true` は XSS 耐性を下げるため、**本番では原則禁止**。
  - やむを得ず一時利用する場合は、期限付き運用（期限・担当者・ロールバック条件）を明文化し、解除を必須タスクとして追跡すること。

### 2026-03-30 追加追記（CSP strict rollout 判定の運用境界修正）

- **実施した改善**
  - strict CSP の自動強制条件を `VERITAS_ENV=prod|production` または `VERITAS_CSP_ENFORCE_NONCE=true` に限定し、`NODE_ENV=production` 単体では警告のみ（互換維持）に修正。
  - 互換モードのエスケープハッチ（`VERITAS_CSP_ALLOW_UNSAFE_INLINE_COMPAT=true`）警告は維持しつつ、`NODE_ENV=production` で strict 未完了の場合も警告して移行漏れを検知可能にした。

- **追加テスト**
  - `NODE_ENV=production` 単体では nonce 強制が有効化されないことを単体テストで検証。
  - `VERITAS_ENV=production` かつエスケープハッチ無効時は警告しないことを単体テストで検証。
  - `NODE_ENV=production` で strict 未完了時に警告ヘルパーが `true` を返すことを単体テストで検証。

- **セキュリティ警告（継続）**
  - `NODE_ENV=production` 警告状態を放置すると、`script-src 'unsafe-inline'` 互換モードが残る可能性があり、XSS リスクが高止まりする。
  - 本番判定は必ず `VERITAS_ENV=production` を明示し、段階移行完了後は `VERITAS_CSP_ALLOW_UNSAFE_INLINE_COMPAT` を未設定に固定すること。

### 2026-03-30 追加追記（責務境界チェックの改善テーマ自動マッピング）

- **実施した改善**
  - `scripts/architecture/check_responsibility_boundaries.py` の JSON レポートに `improvement_theme` を追加し、責務境界違反を PR 単位で扱いやすいテーマへ自動分類するようにした。
  - 分類ルール:
    - `boundary_violation` は原則 `architecture`。
    - ただし `fuji` / `memory` の責務境界違反は安全性影響を重視して `security` に昇格。
    - `permission_denied` は `security`、`doc_alignment_error` / `input_invalid` は `operations`。
  - これにより、既存の責務境界 CI 結果を「セキュリティ・運用・アーキテクチャ」テーマに接続しやすくした。

- **追加テスト**
  - machine report に `improvement_theme` が出力されることを検証。
  - `fuji` / `memory` の責務境界違反が `security` に分類されることを単体テストで検証。

- **セキュリティ警告（継続）**
  - 本改善は triage 導線の強化であり、実際の責務境界違反を無害化するものではない。
- `fuji` / `memory` の違反検知時は、従来どおりリリースブロック相当で扱い、根本修正を優先すること。

### 2026-03-30 追加追記（改善バックログの統合ビュー運用を追加）

- **実施した改善**
  - リポジトリ内の最新版改善バックログの単一正本を `docs/ja/reviews/review_current_improvements_2026_03_30_ja.md` に固定し、CI / ローカル quality-checks で必須マーカーを検証するガードを追加。
  - 追加した品質ゲート:
    - `scripts/quality/check_review_improvements_consistency.py`
    - `.github/workflows/main.yml` の lint job
    - `Makefile` の `quality-checks` ターゲット

- **統合ビュー更新手順（単一正本）**
  1. 重要改善を実装した PR では、このドキュメントに「日付付き追記セクション」を追加する。
  2. 追記では最低限「実施した改善 / 追加テスト / セキュリティ警告（継続・更新）」を明記する。
  3. 複数領域（API / Frontend / 運用 / セキュリティ）に跨る変更は、優先度付きテーマへの影響も併記する。

- **進捗ステータス（2026-03-30 時点）**
  - 高優先度:
    - Query API key の本番 fail-closed 化: **完了（production では query 無効）**
    - CSP strict 化の本番 fail-closed 強化: **完了（本番で nonce 既定強制、エスケープハッチは警告付き）**
  - 中優先度:
    - 改善バックログの統合運用: **完了（この文書 + 自動整合性チェック）**
  - 継続監視:
    - `VERITAS_CSP_ALLOW_UNSAFE_INLINE_COMPAT` の残留利用
    - 開発/検証環境での query `api_key` 例外運用

- **週次更新ルール（運用固定）**
  - 毎週金曜 UTC で本ドキュメントの「優先度付きテーマ」と「進捗ステータス」を更新し、未完了項目に担当・期限を追記する。
  - 更新漏れは docs consistency チェック失敗として検知し、main 反映前に修正する。

- **セキュリティ警告（継続）**
  - 本改善は「可視化と運用統制」の強化であり、実装上の脆弱性を直接緩和するものではない。
- query `api_key` や CSP 互換モードの例外運用が残る場合、必ず期限付きで追跡し、解除完了までリスク受容を明示すること。

### 2026-03-30 追加追記（CSP Report-Only 違反収集のコード内既定化）

- **実施した改善**
  - frontend middleware の `Content-Security-Policy-Report-Only` に `report-uri` を追加し、違反収集先をコード上で既定化。
  - 既定値は同一オリジンの `/api/veritas/csp-report` とし、`VERITAS_CSP_REPORT_ONLY_ENDPOINT` で明示上書き可能にした。
  - `VERITAS_CSP_REPORT_ONLY_ENDPOINT` が同一オリジン相対パス（`/` 始まり）でない場合にセキュリティ警告ログを出すガードを追加し、外部 collector への誤送信リスクを可視化。

- **追加テスト**
  - Report-Only CSP に既定 `report-uri /api/veritas/csp-report` が含まれることを単体テストで検証。
  - `VERITAS_CSP_REPORT_ONLY_ENDPOINT` 指定時に `report-uri` が上書きされることを単体テストで検証。
  - report endpoint 警告ヘルパーが「未指定/相対パスは警告なし、絶対URLは警告あり」を返すことを単体テストで検証。
  - 絶対URL指定時に middleware がセキュリティ警告を出力することを単体テストで検証。

- **セキュリティ警告（更新）**
  - CSP 違反レポートは URL 断片やユーザー操作由来の情報を含み得るため、`VERITAS_CSP_REPORT_ONLY_ENDPOINT` の外部送信先設定はデータ取扱い承認を前提にすること。
  - 既定の同一オリジン収集先（`/api/veritas/csp-report`）を維持し、外部 collector は期限付き・目的限定で運用すること。

### 2026-03-30 追加追記（Dashboard エフェメラル認証情報のローテーション監視を追加）

- **実施した改善**
  - 共有エフェメラル `DASHBOARD_PASSWORD` のファイル年齢を評価し、しきい値超過時にローテーション警告を出す監視を追加。
  - しきい値は `DASHBOARD_EPHEMERAL_PASSWORD_WARN_AGE_SECONDS`（既定: `86400` 秒）で制御し、負値指定時は明示的に警告機能を無効化。
  - 既存ファイル再利用時・同時起動競合後の再読込時の両方で年齢チェックを実施し、長寿命ノードでの資格情報滞留を検知しやすくした。

- **追加テスト**
  - しきい値環境変数の既定値（`86400` 秒）を検証。
  - 負値設定時に監視無効化（`None`）となり、警告ログが出ることを検証。
  - 共有パスワードファイルがしきい値を超えて古い場合に、ローテーション警告ログが出ることを検証。

- **セキュリティ警告（更新）**
  - 本改善は検知強化（warning）であり、漏えい済み資格情報を自動無効化するものではない。
  - 本番運用では引き続き `DASHBOARD_PASSWORD` の明示設定を第一選択とし、エフェメラル運用は短期例外に限定すること。

### 2026-03-30 追加追記（CodeQL 指摘: credential 関連ログ最小化）

- **実施した改善**
  - エフェメラル資格情報の経年警告ログを定型文に変更し、ファイルパス・経過秒数・しきい値などの可変メタデータをログへ出力しない形に修正。
  - これにより、CodeQL の「Clear-text logging of sensitive information」検知対象となり得る credential 関連ログ流出面を縮小。

- **追加テスト**
  - stale 警告ログに資格情報ファイルパスが含まれないことを検証。
  - stale 警告ログに `age_seconds` などの詳細値キーが含まれないことを検証。

- **セキュリティ警告（更新）**
  - ログ最小化は漏えい面積を下げるが、資格情報そのもののローテーション代替にはならない。
  - 引き続き本番は明示 `DASHBOARD_PASSWORD` を優先し、エフェメラル運用は期限付き例外として管理すること。
