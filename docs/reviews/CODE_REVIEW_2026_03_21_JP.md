# VERITAS OS コードレビュー（2026-03-21）

## 概要

本レビューでは、リポジトリ全体の構成を走査した上で、特に以下を重点確認した。

- Planner / Kernel / FUJI / MemoryOS の責務境界
- API サーバと pipeline オーケストレーション
- BFF / フロントエンド API プロキシ
- セキュリティ対策と代表テスト

総評として、VERITAS OS は**責務分離・監査性・セキュリティ意識が高い**一方、
互換レイヤを多く抱えるため、中核モジュールのレビューコストが高い。
また、一部に可用性優先で fail-open 気味の設計が見られるため、
production では fail-closed を強める余地がある。

---

## 総合評価

- **設計品質**: 高い
- **責務分離**: 概ね良好
- **テスト文化**: 強い
- **セキュリティ意識**: 高い
- **保守性**: 良いが、中核ファイルの肥大化が課題

---

## 良い点

### 1. 責務境界が文書化され、テストでも担保されている

Planner / Kernel / FUJI / MemoryOS の責務がアーキテクチャ文書で明文化され、
import 方向・I/O 所有・公開 API をテストで固定している点は非常に良い。

### 2. Pipeline 分割の方向性が良い

`pipeline.py` は orchestration に寄せ、
input / execute / policy / response / persist / replay に処理を分割している。
大型コードベースの中でも、この部分は改善方向が明確である。

### 3. BFF の権限制御が堅実

フロント側の `/api/veritas/*` プロキシでは、
許可パスのホワイトリスト化、ロール制御、危険な path segment の拒否、
trace ID の伝播などが実装されている。

### 4. セキュリティ対策が具体的

Kernel の subprocess 起動周辺では、seccomp / AppArmor / 実行ファイル検証 /
`O_NOFOLLOW` を考慮したログ FD 作成など、防御的な実装が入っている。

### 5. 外部入力のサニタイズが丁寧

GitHub Adapter は control chars / bidi chars / 不正 URL /
credential 埋め込み URL を除外し、UI 偽装や header 汚染リスクを下げている。

---

## 主な懸念点

### 1. Planner / Kernel がまだ重い

責務境界の方針は正しいが、`planner.py` と `kernel.py` は
依然として互換レイヤと制御分岐を多く抱えている。
新規ロジックが helper/stage 側に寄らず本体に戻ると、
今後さらにレビューが難しくなる。

### 2. production では fail-open 気味な箇所がある

API サーバは可用性を高める設計になっているが、
安全機能の読み込み失敗時にも warning のみで継続する箇所がある。
これは「落ちない」代わりに「保護が弱まったまま動く」リスクを持つ。

### 3. Memory 破損時の見え方が弱い

MemoryStore は JSON decode error や I/O error 時に空配列へフォールバックするため、
破損・消失・未登録の区別が上位から見えにくい。
監査性・運用性の面で改善余地がある。

---

## セキュリティ警告

### 警告 1. sanitize import failure 時に API が継続する

PII masking の import に失敗しても warning のみで動作継続する設計は、
production では注意が必要である。
安全機能の障害を availability 優先で吸収しているため、
規制環境では fail-closed を検討すべきである。

### 警告 2. BFF の API キーが import 時に固定される

Next.js 側の BFF ルートでは `VERITAS_API_KEY` を module import 時に読み込んでいる。
そのため緊急ローテーション時に即時反映されず、
再起動まで古いキーが残る可能性がある。

### 警告 3. Memory 読み込み失敗が silent degradation になりやすい

memory ファイルの破損や読み込み失敗時に empty-state へ倒れるため、
障害検知が遅れるおそれがある。
health / audit への明示的な露出が望ましい。

---

## 優先度つき改善提案

### P0

- [x] production で sanitize import failure を fail-closed にする
  - 2026-03-21 対応済み。`veritas_os/api/startup_health.py` の `check_runtime_feature_health()` を更新し、`sanitize` モジュール未ロード時は non-production では警告、production (`VERITAS_ENV=production` / `prod`) では `RuntimeError` を送出して API 起動を停止するよう変更した。これにより PII masking 欠落状態での fail-open 起動を防止する。
  - `veritas_os/tests/test_api_startup_health.py` に、non-production 警告動作を維持しつつ production では fail-closed になる回帰テストを追加した。
  - 2026-03-22 追記。`veritas_os/api/routes_system.py` の `/health` / `/v1/health` に `runtime_features` を追加し、`sanitize` / `atomic_io` の欠落を `degraded` として返すようにした。起動自体は継続する non-production でも、監視側が安全機能の欠落をレスポンスだけで検知できる。
  - `veritas_os/tests/test_api_backend_improvements.py` に、runtime feature の degradation が health 応答へ露出する回帰テストを追加した。
  - 2026-03-22 追記。`veritas_os/api/auth.py` に `auth_store_health_snapshot()` を追加し、`veritas_os/api/routes_system.py` の `/health` / `/v1/health` で `checks.auth_store` と `auth_store` 詳細を返すようにした。これにより `VERITAS_AUTH_SECURITY_STORE=redis` を要求しながら in-memory にフォールバックしている状態や、non-production の fail-open 設定を health 監視だけで検知できる。
  - `veritas_os/tests/test_api_backend_improvements.py` に、auth store の degraded 状態が health 応答へ露出する回帰テストを追加した。
  - 2026-03-22 追記。`veritas_os/api/routes_system.py` の `/health` / `/v1/health` に `checks.trust_log` と `trust_log` 詳細を追加し、aggregate `trust_log.json` が `invalid` / `unreadable` / `too_large` へ劣化した状態を health 監視から直接検知できるようにした。これにより audit trail の degraded 状態が `/v1/metrics` だけでなく軽量 health poll でも観測可能になり、silent degradation を避けやすくなる。
  - `veritas_os/tests/test_api_backend_improvements.py` に、trust log の degraded 状態が health 応答へ露出する回帰テストを追加した。
  - 2026-03-22 追記。`veritas_os/api/routes_system.py` の `/v1/metrics` に `auth_store_effective_mode` / `auth_store_status` / `auth_store_reasons` を追加し、health poll だけでなく監査・運用メトリクス収集側でも auth store の degrade を追跡できるようにした。これにより redis 要求時の in-memory フォールバックや fail-open 設定が、定期メトリクス収集からも把握できる。
  - `veritas_os/tests/test_api_backend_improvements.py` に、metrics 応答へ auth store degradation が露出する回帰テストを追加した。
  - 2026-03-22 追記。`veritas_os/api/routes_system.py` の `/v1/metrics` に `memory_status` / `memory_health` / `runtime_features` を追加し、Memory 破損フォールバックや `sanitize` / `atomic_io` 欠落を health endpoint 以外の定期メトリクス収集からも追跡できるようにした。これにより empty-state へ倒れた非致命障害や安全機能の欠落が、監査・監視パイプライン上で見落とされにくくなる。
  - `veritas_os/tests/test_api_backend_improvements.py` に、metrics 応答へ memory/runtime の degradation が露出する回帰テストを追加した。
  - 2026-03-22 追記。`veritas_os/api/auth.py` の `_create_auth_security_store()` を更新し、`VERITAS_AUTH_SECURITY_STORE=redis` を要求した production (`VERITAS_ENV=production` / `prod`) では、`VERITAS_AUTH_REDIS_URL` 未設定や Redis 初期化失敗時に `RuntimeError` を送出して fail-closed で起動停止するようにした。これにより distributed-safe な auth store を要求した本番構成が silent に in-memory へ degrade する経路を閉じた。
  - `veritas_os/tests/test_auth_core.py` に、non-production では従来どおり warning + fallback を維持しつつ、production では missing URL / Redis 初期化失敗を fail-closed にする回帰テストを追加した。
  - 2026-03-22 追記。`veritas_os/api/startup_health.py` の `check_runtime_feature_health()` を更新し、`atomic_io` モジュール未ロード時も production (`VERITAS_ENV=production` / `prod`) では `RuntimeError` を送出して API 起動を停止するよう変更した。これにより trust-log / shadow-log が direct file I/O に silently degrade したまま本番稼働する経路を閉じ、監査ログの crash-safe 性を fail-closed で守る。
  - `veritas_os/tests/test_api_startup_health.py` に、non-production では従来どおり warning を維持しつつ production では fail-closed になる回帰テストを追加した。

### P1

- [x] BFF の `VERITAS_API_KEY` を request 時に取得する形へ変更し、緊急ローテーションを即時反映できるようにする
  - 2026-03-21 対応済み。`frontend/app/api/veritas/[...path]/route.ts` で module import 時の固定読み込みを廃止し、各 request ごとに `process.env.VERITAS_API_KEY` を再評価するよう変更した。これにより BFF 再起動なしでもキー更新が次リクエストから反映される。
  - `frontend/app/api/veritas/[...path]/route.test.ts` に、未設定時の 503 応答と、連続 2 リクエストで異なる API キーが upstream に送られる回帰テストを追加した。
- [x] Memory corruption / load failure を health / audit に反映する
  - 2026-03-21 対応済み。`veritas_os/memory/store.py` に非致命な読み込み障害を記録する health telemetry を追加し、boot rebuild / targeted payload load での JSON decode error・I/O error・サイズ超過・truncation を `health_snapshot()` で取得できるようにした。
  - `veritas_os/api/routes_system.py` の `/health` / `/v1/health` は、MemoryStore が degraded telemetry を持つ場合に `checks.memory="degraded"` と `memory_health` を返すよう変更した。これにより empty-state へフォールバックしても運用監視から破損兆候を検知できる。
  - 2026-03-21 追記。health 応答に top-level の `status` (`ok` / `degraded` / `unavailable`) を追加し、Memory の非致命障害と依存欠落をレスポンスだけで判別できるようにした。`ok` の既存ブール契約は維持しつつ、監視側が `checks` の深掘りなしで degradation を扱える。
  - 2026-03-22 追記。`veritas_os/memory/store.py` の production 判定を `VERITAS_ENV=production` だけでなく `prod` も含むよう修正し、`VERITAS_MEMORY_DIR_ALLOWLIST` の強制が `prod` 別名では抜け落ちる経路を閉じた。これにより Memory ディレクトリの fail-closed 制約が、他の startup hardening と同じ production alias 契約で一貫する。
  - `veritas_os/tests/test_memory_store.py` と `veritas_os/tests/test_api_backend_improvements.py` に回帰テストを追加した。
  - 2026-03-22 追記。`veritas_os/memory/store.py` の health telemetry に `issue_code` / `issue_counts` を追加し、JSON 破損・ファイル消失・権限不備などの非致命な読み込み失敗を `file_missing` / `permission_denied` / `io_error` の安定コードで識別できるようにした。これにより、従来の `detail` 文字列だけでは曖昧だった「破損・消失・I/O 障害」の区別を監視側が機械的に扱える。
  - `veritas_os/tests/test_memory_store.py` と `veritas_os/tests/test_api_backend_improvements.py` に、`issue_code` の露出と missing file 分類の回帰テストを追加した。

### P2

- [x] `planner.py` / `kernel.py` の互換ロジックを helper/stage へさらに移送する
  - 2026-03-21 対応。`veritas_os/core/planner.py` 先頭に集中していた inventory 判定・step 正規化・simple QA 判定を `veritas_os/core/planner_helpers.py` へ移送し、`planner.py` 側は既存の `_wants_inventory_step` / `_normalize_step` / `_normalize_steps_list` / `_is_simple_qa` を helper alias として再公開する形に整理した。これにより Planner 本体の責務は plan 生成フローに寄り、既存呼び出し互換も維持した。
  - `veritas_os/tests/test_planner.py` に helper alias の互換性テストを追加し、既存 API の挙動が変わっていないことを固定した。

### P3

- [x] フロント API client の abort 原因判定を改善し、timeout と user cancel を分離する
  - 2026-03-21 対応済み。`frontend/lib/api-client.ts` の `veritasFetchWithOptions()` で timeout 起因の abort と caller 起因の abort を分離し、`ApiError.kind` に `cancelled` を追加した。これにより UI は timeout と明示的な user cancel を別扱いできる。
  - `frontend/lib/api-client.test.ts` に timeout / caller abort の回帰テストを追加した。

---

## 結論

VERITAS OS は、研究用途の試作を超えて、
**監査性・安全性・責務分離を強く意識した実装**になっている。
特に boundary 契約、BFF 制御、セキュリティ回帰テストは評価できる。

一方で、今後の継続改善では、
「壊れても落とさない」設計を「壊れたら安全側に倒す」設計へどこまで寄せるかが重要である。
production / enterprise 運用を強く意識するなら、
fail-closed の適用範囲を広げることを推奨する。
