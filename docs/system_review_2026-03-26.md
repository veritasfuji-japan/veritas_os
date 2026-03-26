# VERITAS OS システムレビュー（2026-03-26）

## 実施概要
- 対象: `veritas_os/`（Python backend）, `frontend/`（Next.js）, ルート設定群（`README.md`, `pyproject.toml`, `openapi.yaml` ほか）
- 観点: アーキテクチャ責務分離 / セキュリティ / 運用性 / テスト健全性
- 手法: 静的読解 + 重点ファイルレビュー + セキュリティ観点のパターンスキャン

## 総評
- **全体評価: 良好（Production-approaching）**。
- 特に、Planner / Kernel / FUJI / MemoryOS の責務境界が README とコードdocstringの双方で明確化されており、分割方針も一貫しています。
- API 層は fail-closed 指向が多く、暗号化・監査ログ・nonce/rate-limit などの運用安全機構が実装済みです。

## 良い点（維持推奨）

### 1) 責務分離の明文化と実装整合
- README で Planner / Kernel / FUJI / MemoryOS の責務境界が明記されています。
- `core/pipeline.py` は「オーケストレーション専任」を明記し、`pipeline_*` への拡張誘導が徹底されています。
- `core/fuji.py`, `core/memory.py`, `core/kernel.py` も「どこまでを自分の責務にするか」が docstring で示され、境界逸脱抑制に効いています。

### 2) セキュリティの設計姿勢
- 認証ストアは production 時に fail-open を禁止し、誤設定時も fail-closed 寄りに補正する実装です。
- CORS は wildcard+credentials の危険組み合わせを拒否する設計です。
- リクエストボディ上限、trace-id、inflight 管理、暗号化（鍵未設定時は書込み拒否）など防御層が重なっています。
- Web検索は SSRF・allowlist・入力正規化の専用ロジックに分離されており、安全性と可読性が両立しています。

### 3) テスト資産の厚み
- `veritas_os/tests/` と `frontend/**/*.test.ts(x)` が広範囲で、責務境界や契約の退行検知に有効です。

## セキュリティ警告（優先対応順）

### [HIGH] 直接FUJI API公開の運用リスク
- `/v1/fuji/validate` は `VERITAS_ENABLE_DIRECT_FUJI_API` で有効化可能。
- 誤って本番で有効化すると、本来 `/v1/decide` で行う統合パイプライン前提の運用制御をバイパスした利用が発生し得ます。
- **推奨:** 本番プロファイルでは常時無効、CIで env drift を検知。

### [HIGH] 非本番での auth store 劣化許容の誤運用リスク
- auth store は本番で fail-closed ですが、非本番では設定次第で fail-open にできる設計です。
- 共有staging環境で fail-open が紛れ込むと、検証時のセキュリティ前提が崩れます。
- **推奨:** `VERITAS_ENV` が `stg/staging` のときは policy で fail-open 禁止を追加。

### [MEDIUM] 暗号化フォールバックの説明不足リスク
- 暗号化は secure-by-default だが、`cryptography` 不在時に HMAC-CTR 実装へフォールバックする設計。
- 実装自体は妥当でも、運用者が「AES-GCM前提」と誤認する可能性があります。
- **推奨:** 起動時ヘルス/メトリクスに「現在の暗号方式」を明示し、Runbookへ追記。

## アーキテクチャ境界レビュー（禁止事項チェック）

- Planner: `core/planner.py` は計画生成と正規化に集中しており、永続化やFUJI政策ロジックを直接抱え込んでいません。
- Kernel: `core/kernel.py` は意思決定・評価中心で、API配線や記録永続は pipeline 側へ委譲されています。
- FUJI: `core/fuji.py` は最終安全ゲートと監査向け判定整形に注力。
- MemoryOS: `core/memory.py` は保存・検索・要約・ライフサイクルを担当し、他責務への侵食を避ける方針が明示。

=> **現時点で、重大な責務逸脱は見当たりません。**

## 改善提案（次スプリント）
1. `VERITAS_ENABLE_DIRECT_FUJI_API` を production profile で強制無効化する安全ガードを追加。
2. `/health` に「auth store mode」「encryption backend」「direct FUJI API flag」を集約表示。
3. セキュリティ関連環境変数の推奨値を `.env.example` と運用ドキュメントで強制力高く同期。

## 参考に確認した主要ファイル
- `README.md`
- `veritas_os/core/pipeline.py`
- `veritas_os/core/kernel.py`
- `veritas_os/core/planner.py`
- `veritas_os/core/fuji.py`
- `veritas_os/core/memory.py`
- `veritas_os/api/server.py`
- `veritas_os/api/auth.py`
- `veritas_os/api/middleware.py`
- `veritas_os/api/cors_settings.py`
- `veritas_os/api/routes_decide.py`
- `veritas_os/logging/encryption.py`
- `veritas_os/tools/web_search.py`

---

## 追記（改善実施ログ / 2026-03-26）

以下の改善を実装し、責務境界（Planner / Kernel / FUJI / MemoryOS）を越えない
API運用層の安全性向上として反映しました。

### 1) 本番環境で Direct FUJI API を強制無効化
- 対応:
  - `VERITAS_ENABLE_DIRECT_FUJI_API=true` が設定されていても、
    `VERITAS_ENV=prod|production` では実行時に `False` として扱うガードを追加。
  - 起動時セキュリティ検証で、production で当該フラグが有効なら fail-fast で起動拒否。
- 目的:
  - `/v1/decide` パイプラインを経由しない直接利用の誤運用を防止し、
    本番の統合制御（監査・運用ポリシー）を維持する。

### 2) `/health` と `/status` にセキュリティ姿勢スナップショットを追加
- 対応:
  - `security_posture.direct_fuji_api_enabled`
  - `security_posture.encryption`（暗号化有効状態・アルゴリズム等）
  を返すよう拡張。
- 目的:
  - 「今どの安全機構が有効か」を即時確認可能にし、
    運用Runbook/監視ダッシュボードでの誤認を減らす。

### 3) テスト追加・更新
- 追加:
  - production で direct FUJI API が強制無効化されることの単体テスト。
  - 起動時セキュリティ検証で direct FUJI API を
    - non-production: 警告
    - production: 例外
    として扱うテスト。
  - `/health` が `security_posture` を含むことの確認テスト。

## 追加セキュリティ警告
- **[HIGH] Direct FUJI API の本番有効化は重大リスク**  
  本改善で fail-fast + 実行時ガードを実装済みですが、設定管理（IaC / Secret Manager）
  でも `VERITAS_ENABLE_DIRECT_FUJI_API` を production で配布しない統制を継続してください。

### 追記（E2E品質改善 / 2026-03-26）
- `frontend/e2e/governance-flow.spec.ts` の待機条件に含まれていた `/version/i` が、
  画面ヘッダー文言（versioning）に誤マッチして早期通過することで、実際のロード完了前に
  `viewer role keeps apply action blocked` テストが判定へ進む不安定要因を確認。
- 対策として、`waitForPolicyLoadOutcome` ヘルパーを導入し、
  - apply ボタン可視化（ロード成功）
  - エラーバナー可視化（ロード失敗）
  のどちらかを待つ deterministic な待機へ変更。
- これにより flake を抑制し、RBAC（viewer の apply 禁止）検証の意図を維持。
