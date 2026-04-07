# VERITAS OS Threat Model（STRIDE / LINDDUN）

## 1. Scope（対象範囲）
- 対象システム: `veritas_os` の API / Decision Pipeline / Replay / TrustLog / Governance 更新経路。
- 本ドキュメントの目的: セキュリティ脅威（STRIDE）とプライバシー脅威（LINDDUN）を体系化し、優先対応の根拠を監査可能な形で残す。
- 非対象: 外部クラウド基盤（WORM 実体、KMS/HSM 実装詳細、IdP 実装）は運用設計側で別途補完。

## 2. Assets / Security Objectives
### 2.1 主要アセット
- 意思決定入力（ユーザープロンプト、Evidence、Memory取得結果）
- 意思決定出力（判定結果、理由、リスク）
- Governance Policy（FUJI/ValueCore 関連設定）
- TrustLog（チェーンハッシュ、署名、検証証跡）
- Replay Snapshot（再現検証メタデータ）
- API 認証情報（API keys, 署名鍵）

### 2.2 セキュリティ目標
- C: 機密性（PII/機微データ漏えい防止）
- I: 完全性（判定・監査証跡の改ざん防止）
- A: 可用性（安全停止しつつ運用継続）
- G: ガバナンス強制（バイパス不可、fail-closed）
- P: プライバシー（最小化・追跡可能性制御）

## 3. Trust Boundaries / Data Flows
1. Client → API（`/v1/decide`, `/v1/governance/policy`）
2. API → Pipeline stages（Planner / Kernel / FUJI / Persist）
3. Pipeline → Storage（TrustLog, replay artifacts, policy files）
4. Replay runner → Stored snapshots / model metadata
5. Governance updater → policy persistence + approval signature checks

## 4. STRIDE Analysis
| 区分 | 脅威例 | 影響 | 現状コントロール | ギャップ / 追加対策 |
|---|---|---|---|---|
| S: Spoofing | API key なりすまし、承認者ID偽装 | 不正実行、ポリシー改変 | APIキー検証、4-eyes（署名2名） | 署名鍵ローテーションと失効リスト運用を標準化 |
| T: Tampering | TrustLog / policy / replay への改ざん | 監査不能、誤判定誘導 | チェーンハッシュ、署名、atomic write | 外部 Transparency anchor 必須化の段階的導入 |
| R: Repudiation | 更新者・承認者が実行否認 | 監査不成立 | Governance 変更履歴、署名付き記録 | 承認イベントの外部監査系 SIEM 連携 |
| I: Information Disclosure | PII 含有ログ漏えい | 法令・契約違反 | PII マスキング、ログレダクション | データ分類タグの全ログ強制（Roadmap #13） |
| D: Denial of Service | 外部依存障害、例外連鎖 | 可用性低下 | fail-closed 部分実装、レート制限 | 重要経路のサーキットブレーカ・段階的劣化運用 |
| E: Elevation of Privilege | pipeline外直呼び、管理API濫用 | ガバナンス回避 | direct FUJI API デフォルト拒否 | 管理系エンドポイントに RBAC/ABAC（Roadmap #19） |

## 5. LINDDUN Analysis
| 区分 | 脅威例 | リスク | 現状コントロール | ギャップ / 追加対策 |
|---|---|---|---|---|
| Linkability | 複数意思決定ログの同一主体連結 | プロファイリング | 既定で限定メタ情報 | 主体識別子のハッシュ化ポリシー明文化 |
| Identifiability | ログから個人再識別 | 個人情報漏えい | PII マスク | 高リスク項目の保存禁止ルールを追加 |
| Non-repudiation | 履歴が個人に強固紐付け | 過剰監視 | 監査目的の署名運用 | 監査用途限定のアクセス制御を強化 |
| Detectability | 外部から処理有無推定 | 行動推測 | 401/403制御、標準レスポンス | レスポンスサイズ/時間差の統制 |
| Disclosure | Memory/検索経由の秘匿情報露出 | 機密漏えい | 安全フィルタ、redaction | 出力前 DLP ルールの段階追加 |
| Unawareness | 利用者が処理/保存を認識しない | 同意不備 | ドキュメント/ポリシー公開 | 利用者向け通知テンプレート整備 |
| Non-compliance | 保持期間・開示要件不一致 | 法令違反 | retention 設定、監査ログ | jurisdiction 別保存・削除ポリシーを追加 |

## 6. Prioritized Mitigations（優先順）
1. **P0継続**: fail-closed 一貫性の維持（FUJI/Policy/TrustLog）と bypass 防止。
2. **P1-11**: 本脅威モデルを基準ドキュメントとして運用手順（レビュー頻度、責任者、証跡保管先）へ接続。
3. **P1-12**: 署名鍵・暗号鍵を Vault/KMS 管理前提にし、ローテーション証跡を必須化。
4. **P1-13**: ログ全項目へデータ分類タグを付与し、保存・閲覧ポリシーを機械検証。
5. **P1-15**: 敵対プロンプト安全回帰を定期ジョブ化し、閾値逸脱時は自動アラート。

## 7. Operational Rules
- 本文書は四半期ごとに再評価し、重大インシデント発生時は臨時更新する。
- 変更は Governance レビュー（4-eyes）を通し、更新履歴を TrustLog へ記録する。
- 外部監査向け提出時は、環境依存項目（WORM/KMS/SIEM）を別紙で補完する。

## 8. Security Warnings
- **警告**: WORM・KMS・SIEM など外部基盤が未構成の環境では、改ざん耐性/鍵管理/検知能力が低下する。
- **警告**: Replay strict モードでも外部モデル更新により完全決定論は保証できない。
