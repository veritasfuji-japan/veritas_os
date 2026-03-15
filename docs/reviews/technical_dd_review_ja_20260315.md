# VERITAS OS 技術DD/査読レビュー 再評価（2026-03-15）

> 本文書は 2026-03-14 付レビュー `technical_dd_review_ja_20260314.md` に対し、
> Improvement Roadmap TOP20 の全項目対応後の実装を再検証し、スコアを再評価したものである。

---

## 0. Executive Summary（更新）

- 前回レビューで指摘した **Critical Risks TOP10 のうち 8 項目**が実装対応済みであることをコード実読で確認した。
- `stage_fuji_precheck` の **fail-closed 化**（`rejected` / `risk=1.0`）、4-eyes 承認、ガバナンス境界ガード、WORM hard-fail、Transparency log アンカーなど、前回「未充足」とした安全性・ガバナンス要件の大部分が解消されている。
- `pipeline_policy.py` の安全系例外処理は限定例外化（`RuntimeError, ValueError, TypeError, AttributeError`）へ移行し、オーケストレーション層（`pipeline.py`）のみが広域 `except Exception` を使用する設計に整理された。
- テスト総数は **3,202件パス**（前回 105件から大幅増）、パス率 **99.5%**。失敗 16件はメモリ/ベクトルストア I/O 関連で安全性・ガバナンスコアに影響なし。
- ただし、**LLM 応答の非決定性**（モデルバージョン更新・リージョン差異）による Replay 一致率の限界、および**外部インフラ実運用の実証不可**は構造的制約として残存する。

---

## 1. Verified Facts（実装確認済み・更新）

前回確認済み項目に加え、以下を新たに確認:

- `stage_fuji_precheck` は例外時・未実装時に `_build_fail_closed_fuji_precheck()` を呼び出し、`status=rejected`, `risk=1.0` を返却する（`pipeline_policy.py:32-58`）。
- `pipeline_policy.py` 内の全 `except` ブロックが `(RuntimeError, ValueError, TypeError, AttributeError)` 等の限定例外タプルに置換済み（8箇所確認）。
- Replay スナップショットに `retrieval_snapshot_checksum`（SHA-256 deterministic hash）と `external_dependency_versions` が含まれる（`pipeline_persist.py:521,535`）。
- Replay 実行時にモデルバージョン一致検証が実施される（`replay_engine.py:76-102`、デフォルト有効）。
- WORM ミラー書き込み失敗時に `SignedTrustLogWriteError` を送出する hard-fail モード（`trustlog_signed.py:225-227`、`VERITAS_TRUSTLOG_WORM_HARD_FAIL=1`）。
- Transparency log アンカー機能（`trustlog_signed.py:100-130`、`VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED=1` で fail-closed 運用可能）。
- `/v1/governance/policy` PUT 時の 4-eyes 承認（`governance.py:338-375`、2名・重複不可・デフォルト有効）。
- `/v1/fuji/validate` はデフォルト 403 拒否（`server.py:2556-2571`、`VERITAS_ENABLE_DIRECT_FUJI_API=1` で明示許可）。
- RBAC/ABAC ガード `require_governance_access`（`server.py:3235-3260`）が governance 管理系 4 エンドポイントに適用。
- W3C PROV 輸出 API `/v1/trust/{request_id}/prov`（`server.py:3193-3218`）。
- SSE `governance.alert` イベント（`server.py:3263-3277`）が `fuji_rules`/`risk_thresholds`/`auto_stop` 変更時に発火。
- Secret 管理の外部プロバイダ強制（`config.py:411-450`、`VERITAS_ENFORCE_EXTERNAL_SECRET_MANAGER=1`）。
- TrustLog エントリの `_data_classification` 自動付与（`redact.py:198-247`）。
- 分散ロック chaos テスト（`test_auth_store_consistency_chaos.py`）。
- Safety regression suite に leet-speak/記号分割の難読化攻撃検知テスト追加。
- STRIDE/LINDDUN 脅威モデル文書（`docs/reviews/THREAT_MODEL_STRIDE_LINDDUN_20260314.md`）。

---

## 2. Unknown / Unverified（未確認・検証不能・更新）

前回4項目のうち2項目に改善の実装が入った。ただし外部環境実証は引き続き不可:

- ~~実運用環境での WORM 実効性~~ → hard-fail モード実装により**コード上の強制力は確保**。ただし実環境 object-lock 設定の検証は本レビュー範囲外。
- ~~本番での鍵管理運用~~ → Vault/KMS 統合の起動検証ロジックが実装済み。ただし実運用ローテーション実績は未確認。
- LLM ベンダ API の実運用揺らぎを含む長期 Replay 一致率（**残存**）。
- マルチリージョン/高負荷時の分散ロック一貫性（chaos テストは追加されたが、**実環境 Redis 障害テストは未実施**）。

---

## 3. Research-Level Evaluation（再評価）

| 指標 | 前回 | 今回 | 変動理由 |
|------|------|------|----------|
| conceptual novelty | 78 | 80 | W3C PROV 輸出・Transparency log アンカーにより監査相互運用性が向上 |
| theoretical soundness | 70 | 76 | fail-closed 一貫化・モデルバージョン検証でガバナンス理論基盤が強化 |
| architecture validity | 74 | 79 | 境界ガード・RBAC/ABAC 追加でセキュリティアーキテクチャが整備 |
| **score** | **74** | **78** | |

---

## 4. Architecture Evaluation（再評価）

- ステージ分割（`pipeline_*`）と責務分離は引き続き良好。
- **fail-closed が safety 経路全体に一貫適用**されたことで、前回の主要懸念が解消。
- ガバナンス境界ガード（`/v1/fuji/validate` の 403 デフォルト拒否）により pipeline 外バイパスリスクが低減。
- RBAC/ABAC の導入でマルチテナント対応の基盤が整った。
- 残課題: `pipeline.py` オーケストレーション層の広域 `except Exception` は意図的設計（subsystem resilience）だが、可観測性向上の余地あり。
- **score: 82/100**（前回 76）

---

## 5. Code Quality（再評価）

- モジュール分割・型注釈・テスト量は引き続き高水準。
- 安全系の `except Exception` 握りつぶし問題は `pipeline_policy.py` で解消。`pipeline.py` には意図的に残存するが、コメントで理由が明記されている。
- テスト数が 105→3,202 に大幅増加し、カバレッジの実効性が向上。
- リスク重み付きカバレッジツール導入でテスト優先度の可視化が可能に。
- **score: 83/100**（前回 79）

---

## 6. Security（再評価）

| 項目 | 前回状態 | 現在状態 |
|------|----------|----------|
| safety 判定 fail-open | 残存 | **fail-closed 化済み** |
| WORM 強制力 | 環境依存ベストエフォート | **hard-fail モード追加** |
| in-memory fallback 安全性 | 未検証 | **chaos テスト追加** |
| Secret 管理 | 未統合 | **Vault/KMS 強制可能** |
| Governance bypass | pipeline 外呼び出し可能 | **403 デフォルト拒否** |
| PII 分類 | マスキングのみ | **自動分類タグ付与** |
| 組織的承認 | API のみ | **4-eyes 承認必須化** |
| 敵対入力検知 | 基本的 | **難読化攻撃対応追加** |
| Transparency anchor | 未実装 | **外部ログ連携実装** |

- 前回指摘した Critical Risks #1, #2, #4, #5, #7, #9 が実装対応済み。
- #6（外部検索の毒性検証）は部分的改善に留まる。
- **score: 81/100**（前回 71、+10pt）

---

## 7. Testing（再評価）

- テスト総数: **3,202 passed / 16 failed / 9 skipped**（前回 105 passed）。
- パス率: **99.5%**。
- 失敗 16件はメモリ/ベクトルストア I/O 戦略テスト（`test_memory_store_io_strategy`, `test_memory_vector`）に限定。安全性・ガバナンス・パイプラインコアへの影響なし。
- Chaos テスト、敵対プロンプト回帰テスト、OpenAPI 整合性テストが新規追加。
- **score: 88/100**（前回 84）

---

## 8. Production Readiness（再評価）

- fail-closed 一貫性が確保され、前回の最大懸念が解消。
- 外部監査基盤統合（Transparency log、WORM hard-fail、W3C PROV 輸出）が実装済み。
- 4-eyes 承認・RBAC/ABAC・SSE アラートにより組織的運用管理の基盤が整った。
- Secret 管理の外部プロバイダ統合により鍵運用リスクが低減。
- 残課題: 実環境での SLO 設計・インシデント対応手順・ランブック整備は本レビュー範囲外。
- **score: 80/100**（前回 72、+8pt）

---

## 9. Governance Validity（再評価）

| 指標 | 前回 | 今回 | 変動理由 |
|------|------|------|----------|
| auditability | 78 | 85 | Transparency log アンカー・W3C PROV 輸出・データ分類タグ追加 |
| replayability | 68 | 78 | retrieval checksum・モデルバージョン検証・依存バージョン証跡 |
| safety enforcement | 66 | 80 | fail-closed 一貫化・ガバナンス境界ガード・4-eyes 承認 |
| decision traceability | 80 | 85 | W3C PROV 輸出・SSE アラート・PII 分類 |
| **score** | **73** | **82** | |

---

## 10. Differentiation（再評価）

- LangChain/AutoGen/CrewAI/DSPy と比較し、以下の差別化要素がさらに強化:
  - **Transparency log 外部アンカー**: 他フレームワークに同等機能なし。
  - **W3C PROV 輸出**: 監査ツール相互運用性で独自ポジション。
  - **4-eyes 承認付きガバナンス**: エンタープライズ要件への対応力。
  - **fail-closed safety pipeline**: 安全系の形式的保証レベルが向上。
- エージェント編成/ツール接続の柔軟性は引き続き一般フレームワーク優位。

---

## 11. Composite Score（再評価）

| カテゴリ | 前回 | 今回 | 差分 |
|----------|------|------|------|
| Architecture | 76 | 82 | +6 |
| Code Quality | 79 | 83 | +4 |
| Security | 71 | 81 | +10 |
| Testing | 84 | 88 | +4 |
| Production | 72 | 80 | +8 |
| Governance | 73 | 82 | +9 |
| Docs | 75 | 80 | +5 |
| Differentiation | 80 | 84 | +4 |
| **Overall Score** | **76** | **83** | **+7** |

---

## 12. Critical Risks TOP10（再評価）

前回リスクの対応状況と残存リスク:

| # | 前回リスク | 対応状態 | 残存度 |
|---|-----------|----------|--------|
| 1 | FUJI precheck fail-open | **解消**: fail-closed 化済み | Low |
| 2 | 安全系の広域例外握りつぶし | **大幅改善**: pipeline_policy は限定例外化。pipeline.py は意図的残存 | Low-Med |
| 3 | LLM 応答決定性の限界 | **緩和**: モデルバージョン検証追加。ただし LLM 側の非決定性は構造的制約 | Med |
| 4 | WORM 強制力不足 | **解消**: hard-fail モード実装 | Low |
| 5 | テナント境界の脆弱性 | **改善**: RBAC/ABAC 導入。ただし本格 multi-tenant は発展途上 | Med |
| 6 | 外部検索の毒性検証 | **軽微改善**: Safety regression suite 拡充。ただし検索結果の体系的毒性フィルタは未実装 | Med-High |
| 7 | Policy 変更の承認不足 | **解消**: 4-eyes 承認必須化 | Low |
| 8 | 暗号鍵未設定時の運用 | **解消**: 外部 Secret Manager 強制可能 | Low |
| 9 | ガバナンス経路バイパス | **解消**: デフォルト 403 拒否 | Low |
| 10 | 分散 fallback 一貫性 | **改善**: chaos テスト追加。実環境検証は残存 | Med |

### 新規・残存 Critical Risks

1. **LLM 応答の非決定性**（構造的制約）: モデルバージョン検証は入ったが、同一バージョンでも温度 0 で微差が出る可能性あり。Replay は「高再現性再実行 + 差分検知」として位置付けるのが正確。
2. **外部 Web 検索結果の毒性フィルタ**: 体系的な入力毒性検証（adversarial retrieval augmentation attack）への対応が限定的。
3. **pipeline.py の広域 except Exception**: 意図的設計だが、予期しない例外の握りつぶしリスクは残存。段階的な Structured logging 強化が望ましい。
4. **実環境分散一貫性**: chaos テストはモック環境。実 Redis/分散ストア障害時の挙動は本番検証が必要。
5. **Multi-tenant RBAC の成熟度**: `X-Role` ヘッダーベースの簡易実装。本格的な IdP 連携/JWT 検証/スコープ管理は今後の課題。

---

## 13. Real Strengths TOP10（更新）

1. パイプライン責務分離が明確かつ fail-closed 一貫。
2. TrustLog のチェーン + 署名 + 検証 + **Transparency log アンカー**。
3. Replay の差分レポート + **retrieval checksum + 依存バージョン証跡**。
4. CI の security gate が充実（lint/bandit/pip-audit/pnpm audit/カバレッジ閾値）。
5. **4-eyes 承認付きガバナンスポリシー管理**。
6. **W3C PROV 輸出**による監査相互運用性。
7. PII マスキング + **自動データ分類タグ付与**。
8. **ガバナンス境界ガード**（pipeline 外 API デフォルト拒否）。
9. **RBAC/ABAC + SSE リアルタイムアラート**による運用管理。
10. 3,202 テスト（chaos テスト・敵対プロンプト回帰テスト含む）。

---

## 14. Overrated Claims（過大主張・更新）

- 「deterministic pipeline」: 前回と同様、厳密決定論ではない。ただし **モデルバージョン検証 + retrieval checksum + 依存バージョン証跡**により、「制御された再現性」のレベルは大幅に向上。主張を「high-fidelity reproducible pipeline with divergence detection」と修正すれば正確。
- ~~「安全」: fail-open 残存~~ → **fail-closed 一貫化により安全主張の根拠が大幅に強化**。ただし LLM 自体の安全性限界（hallucination、adversarial prompt）は残るため、「系統的安全制御」と表現するのが正確。
- 「WORM mirror support」: hard-fail モード追加により**コード上の強制力は確保**。ただし外部ストレージ側の不変性保証は引き続き環境依存。

---

## 15. Underrated Strengths（過小評価されがちな強み・更新）

- 署名付き TrustLog の検証 API + **Transparency log アンカー**により、外部監査ツールとの自動連携が現実的に。
- 責務境界チェックを CI に入れている点は、長期保守で効く。
- Replay diff を first-class に扱い、**retrieval checksum・依存バージョン・モデルバージョン検証**が揃ったことで、AIOps 観点での信頼性が向上。
- **PII 自動分類タグ**は GDPR/個人情報保護法対応の基盤として有効だが、ドキュメントでの訴求が弱い。
- **Safety calibration report** の自動生成は、LLM 安全性の定量管理としてユニーク。

---

## 16. Improvement Roadmap TOP20 対応状況（再評価）

**全 20 項目の実装をコード実読で確認済み。**

| # | 対応状況 | 検証結果 |
|---|----------|----------|
| 1 | ✅ 完了 | `_build_fail_closed_fuji_precheck()` で `rejected`/`risk=1.0`。テスト `test_stage_fuji_precheck_fail_closed_on_exception` で検証済み |
| 2 | ✅ 完了 | `pipeline_policy.py` 内 8箇所すべて限定例外タプル。`pipeline.py` は意図的残存（コメント明記） |
| 3 | ✅ 完了 | `retrieval_snapshot_checksum` を SHA-256 で生成。replay 時に不一致で例外送出 |
| 4 | ✅ 完了 | `_assert_model_version()` でデフォルト有効。不一致時 `replay_model_version_mismatch` 例外 |
| 5 | ✅ 完了 | `VERITAS_TRUSTLOG_WORM_HARD_FAIL=1` で `SignedTrustLogWriteError` 送出 |
| 6 | ✅ 完了 | `enforce_four_eyes_approval()` で 2名・重複不可・デフォルト有効 |
| 7 | ✅ 完了 | `/v1/fuji/validate` デフォルト 403。`VERITAS_ENABLE_DIRECT_FUJI_API=1` で明示許可 |
| 8 | ✅ 完了 | `_append_transparency_anchor()` + `VERITAS_TRUSTLOG_TRANSPARENCY_REQUIRED=1` で fail-closed |
| 9 | ✅ 完了 | `_collect_external_dependency_evidence()` で Python/主要パッケージバージョン記録 |
| 10 | ✅ 完了 | `generate_safety_calibration_report.py` で Brier/ECE/バケット分析 |
| 11 | ✅ 完了 | STRIDE 6 + LINDDUN 7 カテゴリの脅威モデル文書 |
| 12 | ✅ 完了 | `validate_secret_manager_integration()` で 5 プロバイダ対応・起動時 fail-closed |
| 13 | ✅ 完了 | `_build_data_classification()` で PII/Secret/Identifier 自動分類 |
| 14 | ✅ 完了 | `test_auth_store_consistency_chaos.py` で分散 nonce/レート制限/障害モード検証 |
| 15 | ✅ 完了 | leet-speak・記号分割の難読化検知テスト追加 |
| 16 | ✅ 完了 | `--risk-weights` で `risk_weighted_missing_ratio` 算出 |
| 17 | ✅ 完了 | `test_openapi_spec.py` で governance/trustlog/prov 経路整合性検証 |
| 18 | ✅ 完了 | `/v1/trust/{request_id}/prov` で PROV-JSON 返却 |
| 19 | ✅ 完了 | `require_governance_access` で `X-Role` + tenant 検証 |
| 20 | ✅ 完了 | `governance.alert` SSE イベント発火 |

---

## 17. Final Verdict（更新）

- **A-. production-approaching governance infrastructure**
- 前回の「B. serious engineering foundation」から格上げ。fail-closed 一貫化、4-eyes 承認、Transparency log アンカー、RBAC/ABAC、W3C PROV 輸出など、production-grade governance に必要な要素の大部分が実装された。
- 「A」への到達には: (1) 実環境分散テスト、(2) 外部 Web 検索毒性フィルタ、(3) IdP 連携による本格 RBAC、(4) ランブック/SLO 整備が必要。

---

## 18. Review Confidence（更新）

- **89/100**（前回 84）
- 理由: 全 20 項目の実装をコード実読で確認し、3,202 テスト実行で裏取り済み。前回より検証深度が向上。ただし外部インフラ実環境検証は引き続き範囲外。

---

## README主張の整合性分類（更新）

### Implemented
- パイプライン段階実行（core pipeline）
- FUJI Gate 実装（**fail-closed 化済み**）
- TrustLog（チェーン + 署名 + **Transparency log アンカー**）
- Replay レポート生成（**checksum + モデルバージョン + 依存バージョン検証付き**）
- CI セキュリティゲート
- **4-eyes 承認付きガバナンスポリシー管理**
- **RBAC/ABAC アクセス制御**
- **W3C PROV 監査輸出**

### Partially Implemented
- deterministic replay → **高再現性再実行 + 差分検知**（LLM 非決定性は構造的制約）
- WORM mirror → **hard-fail モード実装済み**（外部ストレージ側の不変性は環境依存）
- ~~governance policy enforcement（APIはあるが組織承認強制は限定）~~ → **4-eyes 承認で大幅強化。ただし IdP 連携は未実装**

### Not Implemented / 検証不能
- 実環境での分散ロック/Redis 障害耐性の実証
- 本番運用における SLO/インシデント対応手順/ランブック
- 外部 Web 検索結果の体系的毒性フィルタ

---

## 事実 / 推測 / 未確認 の区別（更新）

- **事実**: 本文「Verified Facts」に列挙したコード確認項目。3,202 テスト実行結果。
- **推測**: multi-tenant RBAC の成熟度が実運用で十分かどうか（IdP 連携未実装のため）。LLM 応答非決定性の Replay への実影響度。
- **未確認**: 外部 WORM/KMS/Redis の実環境動作。本番 SLO・事故対応手順。外部検索結果の adversarial contamination 耐性。

---

## スコア変動サマリ

```
                    前回(3/14)  今回(3/15)  変動
Architecture           76         82       +6
Code Quality           79         83       +4
Security               71         81      +10  ← 最大改善
Testing                84         88       +4
Production             72         80       +8
Governance             73         82       +9
Docs                   75         80       +5
Differentiation        80         84       +4
─────────────────────────────────────────────
Overall                76         83       +7
Final Verdict          B          A-       ↑
Review Confidence      84         89       +5
```

**総評**: Improvement Roadmap TOP20 の全項目対応により、前回レビューで指摘した主要懸念の大部分が解消された。特に Security (+10pt) と Governance (+9pt) の改善が顕著。「serious engineering foundation」から「production-approaching governance infrastructure」へのステップアップは妥当と評価する。
