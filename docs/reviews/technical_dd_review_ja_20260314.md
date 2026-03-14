# VERITAS OS 技術DD/査読レビュー（2026-03-14）

## 0. Executive Summary
- 本リポジトリは、LLM単体の推論をそのまま実行する構成ではなく、`run_decide_pipeline` を中心に段階的処理（入力正規化→検索→コア判断→Debate/Critique→FUJI→永続化）を実装しており、**「Decision OS」化の骨格は実装済み**。
- ただし、`pipeline_policy.stage_fuji_precheck` が例外時に `allow` へフォールバックする設計など、**fail-open 挙動が残存**し、安全性主張を全面的に裏付けるには不十分。
- Replay は strict モードで温度/seed/外部副作用抑制を行うが、LLM応答の確率性・外部依存差異を完全固定できないため、**「完全決定論」ではなく「差分検知付き再実行」**に近い。
- TrustLog はハッシュチェーン/署名/検証機能を持つ一方、WORM は環境依存のベストエフォートであり、**監査証跡としては中〜高品質だが、外部不変ストレージ前提**。

## 1. Verified Facts（実装確認済み）
- `/v1/decide` の主経路は `core/pipeline.py` の `run_decide_pipeline` で、ステージ順がコード上で直列に固定されている。
- パイプラインは `stage_fuji_precheck`→`stage_value_core`→`stage_gate_decision` を実行し、ゲート判定を応答へ反映する。
- Replay は strict 時に `temperature=0`、seed 固定、Memory 取得無効化を実施する。
- TrustLog はチェーンハッシュ・暗号化（鍵必須時）・署名付きログ（Ed25519）・検証APIを実装する。
- API キー認証/認可系ロジック（不正時 401、失敗レート制限）は `api/server.py` に実装されている。
- CI では lint/bandit/pip-audit/pnpm audit/pytest/カバレッジ閾値（85%）が定義される。

## 2. Unknown / Unverified（未確認・検証不能）
- 実運用環境での WORM（object-lock）実効性（本レビュー環境では外部ストレージ設定を未確認）。
- 本番での鍵管理（KMS/HSM/Vault）運用手順・ローテーション実績。
- LLM ベンダ API の実運用揺らぎ（リージョン差・モデル更新）を含む長期 Replay 一致率。
- マルチリージョン/高負荷時の分散ロック一貫性（Redis 障害時の fail mode 実効）。

## 3. Research-Level Evaluation
- conceptual novelty: 78/100
- theoretical soundness: 70/100
- architecture validity: 74/100
- **score: 74/100**

## 4. Architecture Evaluation
- ステージ分割（`pipeline_*`）と責務分離は良好。
- ただし safety 経路の fail-open が残るため、安全系の形式的保証が弱い。
- **score: 76/100**

## 5. Code Quality
- モジュール分割・型注釈・テスト量は高水準。
- 一方で広域 `except Exception` による握りつぶしが複数箇所にあり、障害時の意味論が曖昧化。
- **score: 79/100**

## 6. Security
- 強み: API key 認証、依存脆弱性監査、subprocess/shell 静的チェック、暗号化ログ。
- リスク: safety 判定系の fail-open、WORM が環境依存、in-memory ストア fallback に伴う分散安全性低下。
- **score: 71/100**

## 7. Testing
- パイプライン/Replay/FUJI/TrustLog/ガバナンスのテスト群が広い。
- 今回の実行でも主要テスト群は全通過（105件）。
- **score: 84/100**

## 8. Production Readiness
- 研究プロトタイプを超える運用志向（監査ログ、CI、セキュリティゲート）あり。
- ただし governance/safety の fail-closed 一貫性と外部監査基盤統合が未完成。
- **score: 72/100**

## 9. Governance Validity
- auditability: 78/100
- replayability: 68/100
- safety enforcement: 66/100
- decision traceability: 80/100
- **score: 73/100**

## 10. Differentiation（他フレームワーク比）
- LangChain/AutoGen/CrewAI と比較し、**ハッシュチェーン監査・署名・Replayスナップショット**が標準実装される点は差別化要素。
- 一方で、エージェント編成/ツール接続の柔軟性は一般フレームワーク優位の領域が残る。

## 11. Composite Score
- Architecture: 76
- Code Quality: 79
- Security: 71
- Testing: 84
- Production: 72
- Governance: 73
- Docs: 75
- Differentiation: 80
- **Overall Score: 76/100**

## 12. Critical Risks TOP10
1. FUJI precheck 失敗時に `allow` へ倒れる fail-open。
2. ValueCore/FUJI 例外時の広域握りつぶしにより安全推論の根拠が消える。
3. strict replay でも LLM 応答決定性はモデル側更新で崩れる。
4. WORM が「設定されていれば書く」ベストエフォートで強制力不足。
5. 単一 API key 運用時のテナント境界が実装依存で脆くなり得る。
6. 外部 Web 検索結果の品質/毒性に対する強制検証が限定的。
7. policy 変更の承認ワークフローは API 実装だけでは強制不十分。
8. 暗号鍵未設定時の運用エラー処理が監視されないと可用性低下。
9. pipeline 外から kernel/fuji 直接呼び出し可能（ガバナンス経路バイパス余地）。
10. 分散時 fallback（in-memory）で nonce/replay 防止の一貫性が下がる。

## 13. Real Strengths TOP10
1. パイプライン責務分離が明確。
2. TrustLog のチェーン + 署名 + 検証機構。
3. Replay の差分レポート生成。
4. CI の security gate が比較的充実。
5. API スキーマ/テストが豊富。
6. ガバナンスポリシーのホット更新コールバック。
7. PII マスキングとログレダクション。
8. Atomic write 導入でログ/ポリシー破損リスク低減。
9. Stage latency 等の運用メトリクス保持。
10. 既存コードに責務境界チェッカーを組み込んでいる。

## 14. Overrated Claims（過大主張）
- 「deterministic pipeline」: 厳密決定論ではなく、**決定性を高める実行制御 + 差分検知**。
- 「安全」: 実装上の fail-open が残るため、強い安全保証を断定するには不足。
- 「WORM mirror support」: WORM 先の真正な不変性は外部設定依存で、リポジトリ単独では検証不能。

## 15. Underrated Strengths（過小評価されがちな強み）
- 署名付き TrustLog の検証 API があり、監査運用の自動化に接続しやすい。
- 責務境界チェックを CI に入れている点は、長期保守で効く。
- replay diff を first-class に扱っている点は、AIOps 観点で有益。

## 16. Improvement Roadmap TOP20
| # | 改善内容 | 難易度 | 期待効果 | 優先度 |
|---|---|---|---|---|
| 1 | FUJI/Policy 例外時を fail-closed 化（deny/hold） | M | Safety保証向上 | P0 |
| 2 | `except Exception` の安全系箇所を限定例外化 | M | 障害可観測性向上 | P0 |
| 3 | Replay に retrieval snapshot checksum を追加 | M | 再現性向上 | P0 |
| 4 | モデルID/version固定ポリシーを強制 | M | Replay一致率向上 | P0 |
| 5 | WORM 失敗時の hard-fail モード追加 | M | 監査完全性向上 | P0 |
| 6 | Policy 更新に 4-eyes 承認署名を必須化 | H | Governance強化 | P0 |
| 7 | Pipeline 外 API にガバナンス境界ガード追加 | M | bypass防止 | P0 |
| 8 | TrustLog 外部アンカー（Transparency log）連携 | H | 改ざん耐性向上 | P1 |
| 9 | Replay 実行時の外部依存バージョン証跡化 | M | 検証可能性向上 | P1 |
|10| Safety判定モデルの calibration レポート自動生成 | H | 誤検知/漏検知管理 | P1 |
|11| Threat model 文書化（STRIDE/LINDDUN） | M | 監査対応強化 | P1 |
|12| Secret 管理を Vault/KMS 前提に統合 | M | 鍵運用強化 | P1 |
|13| PII データ分類タグを全ログ項目へ付与 | M | コンプラ対応 | P1 |
|14| 分散ロックの一貫性テスト（chaos含む） | H | 可用性/整合性向上 | P1 |
|15| Safety regression suite（敵対プロンプト）拡充 | M | 安全回帰検知 | P1 |
|16| Coverage を機能リスク重み付きに再設計 | M | テスト有効性向上 | P2 |
|17| OpenAPI と実装差分の自動検証強化 | L | ドキュメント信頼性 | P2 |
|18| Decision trace を W3C PROV 形式で輸出 | H | 監査相互運用性 | P2 |
|19| multi-tenant RBAC/ABAC をAPI層に追加 | H | エンタープライズ適合 | P2 |
|20| 重要設定変更のリアルタイムアラート強化 | L | 運用安全性向上 | P2 |

### Improvement Roadmap TOP20 対応状況（2026-03-14 追記）
- ✅ #1 対応: `stage_fuji_precheck` の例外・未実装時フォールバックを **fail-closed (`rejected`)** に変更し、`risk=1.0` と明示理由を記録するよう改善。
- ✅ #2 部分対応: 安全系の広域 `except Exception` を段階的に縮小し、`pipeline_policy` の FUJI/ValueCore 評価では想定例外へ限定。
- ✅ #3 対応: Replay スナップショットに `retrieval_snapshot_checksum` を追加し、再実行時に整合性検証を実施。
- ✅ #4 対応: Replay 実行時に `model_version` の一致検証を追加（`VERITAS_REPLAY_ENFORCE_MODEL_VERSION=1` で有効）。
- ✅ #5 対応: TrustLog の WORM ミラーに hard-fail モード（`VERITAS_TRUSTLOG_WORM_HARD_FAIL=1`）を追加。
- ✅ #6 対応: `/v1/governance/policy` 更新時に **4-eyes 承認（2名・重複不可署名）** を必須化。デフォルト有効で `VERITAS_GOVERNANCE_REQUIRE_FOUR_EYES=0` の場合のみ無効化。加えて承認失敗時の API 応答は固定文言へ統一し、例外詳細の外部露出を抑止。
- ⚠️ #7 は本変更では未着手（Pipeline 外 API に対する追加ガードは別PRで実施予定）。

## 17. Final Verdict
- **B. serious engineering foundation**
- 研究プロトタイプを超える実装密度はあるが、production-grade governance infrastructure を名乗るには fail-closed / 外部不変監査 / 組織的承認制御が未充足。

## 18. Review Confidence
- **84/100**
- 理由: コア実装・主要テスト・CI 定義・セキュリティ関連コードを実読し、一部テスト実行で裏取り済み。ただし外部インフラ（WORM/KMS/本番運用）までは本環境で実証不可。

---

## README主張の整合性分類
### Implemented
- パイプライン段階実行（core pipeline）
- FUJI Gate 実装
- TrustLog（チェーン + 署名ユーティリティ）
- Replay レポート生成
- CI セキュリティゲート

### Partially Implemented
- deterministic replay（strict制御はあるが完全決定論ではない）
- WORM mirror（環境依存・強制力弱い）
- governance policy enforcement（APIはあるが組織承認強制は限定）

### Not Implemented / 検証不能
- リポジトリ単体での外部監査アンカーの強制実装
- 本番運用における鍵管理と不変保存の実効証明

## 事実 / 推測 / 未確認 の区別
- **事実**: 本文「Verified Facts」に列挙したコード確認項目。
- **推測**: fail-open が本番リスクに直結する程度（運用設計次第で変動）。
- **未確認**: 外部WORM/KMS/実運用SLO・事故対応手順。
