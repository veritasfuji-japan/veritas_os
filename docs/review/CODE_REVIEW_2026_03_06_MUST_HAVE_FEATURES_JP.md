# VERITAS 全体コードレビュー（2026-03-06）

## 1. レビュー目的
- リポジトリ全体（backend / frontend / scripts / docs）を横断し、
  **今後の VERITAS に必須となる機能**を抽出する。
- 既存責務（Planner / Kernel / FUJI / MemoryOS）を越えず、
  境界を維持したまま拡張可能な提案のみを列挙する。

## 2. 実施方法（今回のレビュー手順）
- 構成把握: `README.md`, `veritas_os/core/*`, `veritas_os/api/server.py`, `frontend/*`, `scripts/*`
- 境界チェック: `scripts/architecture/check_responsibility_boundaries.py`
- セキュリティ/品質チェック: `scripts/security/check_next_public_key_exposure.py`, `scripts/quality/check_warning_allowlist.py`
- 実装上の未充足領域確認: ToolOS, TrustLog, API 認証・レート制御、Memory 永続化、FUJI policy fallback

## 3. 現状サマリ（強み）
- Planner / Kernel / FUJI / MemoryOS の責務境界チェックが CI 前提で用意されている。
- HMAC + nonce + rate-limit による API 保護が既に実装済み。
- TrustLog はハッシュチェーンと署名付き出力を備え、監査軸として機能。
- Frontend 側に governance / audit / risk 画面があり、運用可視化の土台がある。

## 4. 今後「必ず必要」になる機能提案（優先度順）

### P0-1. 分散対応のリプレイ防止・レート制御ストア
**理由**
- 現状の nonce / 認証失敗トラッキング / rate-limit はプロセスメモリ中心。
- 単一プロセスでは有効だが、水平分散（複数 Pod / 複数ワーカー）で一貫性が崩れる。

**提案機能**
- Redis 等を利用した共有ストア化（nonce, failure counter, token bucket）。
- TTL, clock skew, fail-open/fail-closed を明示したポリシー設定。
- 監査用に「拒否理由コード」をメトリクスとして出力。

**責務境界への配慮**
- Kernel/FUJI/Planner/Memory ロジックには触れず、API 境界（auth層）で完結。

**セキュリティ警告**
- 現状のまま多インスタンス運用すると、リプレイ耐性と brute-force 耐性が構成依存になり得る。

### P0-2. TrustLog の外部不変保管（WORM / KMS 署名鍵管理）
**理由**
- TrustLog は実装として堅牢だが、保存先がローカルファイル中心だと運用事故・権限事故の影響を受ける。

**提案機能**
- Write Once Read Many（オブジェクトロック）への二重書き込み。
- 署名鍵の KMS/HSM 管理と定期ローテーション。
- `verify_trustlog_chain` を定期ジョブ化し、逸脱時は即時アラート。

**責務境界への配慮**
- TrustLog subsystem（logging/audit）内の拡張で実現可能。

**セキュリティ警告**
- 監査ログが「改ざん困難」でも、運用層で削除・上書き可能だと法令監査の耐性が不足する。

### P0-3. Policy-as-Code の差分検証 + Canary 運用
**理由**
- FUJI は fallback と YAML policy の両経路があるため、更新時に挙動差分を定量管理すべき。

**提案機能**
- 新旧 policy に同一 decision サンプルを当てる A/B replay。
- `allow/hold/deny` 変化率、false-positive/false-negative を自動算出。
- 本番適用前に canary 比率を段階的に引き上げる運用機能。

**責務境界への配慮**
- FUJI Gate のみを対象にし、Kernel/Planner へ波及させない。

**セキュリティ警告**
- policy 更新の差分検証がないと、意図しない緩和/過遮断が本番で発生する。

### P1-4. MemoryOS のライフサイクル統制（Retention / Erasure / Legal Hold）
**理由**
- Memory 機能は豊富だが、運用で必須となる「保存期間」「削除要求」「法的保全」が明示機能として不足。

**提案機能**
- memory item に retention class / expires_at / legal_hold フラグを標準化。
- user_id 単位の erase API（監査証跡付き）。
- distill 済み semantic memory への連鎖削除ルール。

**責務境界への配慮**
- MemoryOS 内で完結。Planner/Kernel の意思決定処理には手を入れない。

**セキュリティ警告**
- 個人情報を含む長期保存データに削除統制がない場合、法令・契約違反リスクが高い。

### P1-5. ToolOS の実行証跡強化（Tool Provenance + Egress 制御）
**理由**
- Tool whitelist/blocklist はあるが、「どの tool 実装を誰がいつ許可したか」の供給網証跡が弱い。

**提案機能**
- tool registry に version / digest / approval ticket を必須化。
- outbound 通信先 allowlist（domain/IP）と request signing。
- tool call 単位で TrustLog 相関IDを付与し、監査検索性を向上。

**責務境界への配慮**
- ToolOS 層の拡張で完結。Planner/FUJI 判定ロジックは非変更。

**セキュリティ警告**
- 外部ツール連携はサプライチェーン攻撃・データ外部流出の主要起点になりやすい。

## 5. 実装順序（推奨）
1. P0-1（分散 replay/rate-limit）
2. P0-2（TrustLog 外部不変保管）
3. P0-3（FUJI policy canary）
4. P1-4（Memory lifecycle）
5. P1-5（Tool provenance/egress）

## 6. 完了条件（Definition of Done）
- 各機能で「仕様」「脅威モデル」「運用 Runbook」「失敗時のフォールバック」をセットで定義。
- 既存の責務境界チェッカーで違反 0 を維持。
- 主要 API 経路で replay test と監査ログ検証 test を CI 化。

## 7. 総括
VERITAS は意思決定ガバナンスの中核要素を既に備えている。
次フェーズで本当に必要なのは、**単体機能の追加よりも、分散運用・監査運用・法務運用に耐える「運用制御機能」**の実装である。

## 8. 対応状況追記（2026-03-06）
本ドキュメントに記載した改善点（P0-1〜P1-5）は、すべて対処済み。
