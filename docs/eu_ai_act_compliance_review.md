# VERITAS OS — EU AI Act 準拠レビュー

**初回レビュー日**: 2026-03-06
**最終更新日**: 2026-03-06
**対象バージョン**: VERITAS OS v2.0
**レビュー根拠**: Regulation (EU) 2024/1689（EU AI法、2024年8月1日発効）

---

## 目次

1. [エグゼクティブサマリー](#1-エグゼクティブサマリー)
2. [スコープと前提条件](#2-スコープと前提条件)
3. [条文別評価](#3-条文別評価)
   - [第5条：禁止AI慣行](#第5条禁止ai慣行)
   - [第6条・附属書Ⅲ：高リスクAIシステムの分類](#第6条附属書iii高リスクaiシステムの分類)
   - [第9条：リスク管理システム](#第9条リスク管理システム)
   - [第10条：データ・データガバナンス](#第10条データデータガバナンス)
   - [第11条：技術文書](#第11条技術文書)
   - [第12条：記録保持](#第12条記録保持)
   - [第13条：透明性・情報提供](#第13条透明性情報提供)
   - [第14条：人間による監視](#第14条人間による監視)
   - [第15条：精度・堅牢性・サイバーセキュリティ](#第15条精度堅牢性サイバーセキュリティ)
   - [第50条：特定AIシステムの透明性義務](#第50条特定aiシステムの透明性義務)
4. [総合リスク評価マトリクス](#4-総合リスク評価マトリクス)
5. [重大ギャップ詳細分析](#5-重大ギャップ詳細分析)
6. [推奨改善アクション](#6-推奨改善アクション)
7. [30/60/90日実行ロードマップ](#7-306090日実行ロードマップ追加)
8. [付録：コード参照インデックス](#8-付録コード参照インデックス)

---

## 1. エグゼクティブサマリー

VERITAS OSはEU AI法への準拠を明示的に設計目標として掲げており、技術的な基盤の多くが規制要件を先取りしている。初回レビューにより**17件の準拠ギャップ（うち5件が重大）**を特定し、その後の対応により **16件を解消済** とした。**残存ギャップは1件（GAP-02: リスク分類の法務承認、Critical）および GAP-01のセマンティック検出未対応（High）**であり、引き続き優先対応が必要である。GAP-01については、キーワードベースの検出を大幅に強化（多言語30+パターン、NFKC/ホモグリフ正規化、スペース挿入回避検出、入力検査、外部分類モデルIF）し、Criticalから**High**に引き下げた。

| 評価カテゴリ | 初回状態 | 現在の状態 | 主な改善 |
|-------------|---------|-----------|---------|
| **第5条**（禁止慣行） | ⚠️ 部分準拠 | ⚠️ 部分準拠 | 多言語30+パターン・入力検査・NFKC/ホモグリフ正規化・スペース挿入検出・外部分類モデルIF |
| **第6条/附属書Ⅲ**（高リスク分類） | ❌ 未準拠 | ⚠️ 部分準拠 | `risk_classification_matrix.md` 新設 |
| **第9条**（リスク管理） | ⚠️ 部分準拠 | ⚠️ 部分準拠 | 継続的モニタリング・残留リスク文書化・デフォルトリスクスコア是正・**監査不備環境での高リスク拒否（P1-6）**・リスク分類正規化（GAP-01d） |
| **第10条**（データガバナンス） | ❌ 未準拠 | ⚠️ 部分準拠 | モデルカード・バイアス評価・DPAチェックリスト新設・データリネージュ追跡・**データ品質検証のメモリ取り込み統合** |
| **第11条**（技術文書） | ⚠️ 部分準拠 | ⚠️ 部分準拠 | 附属書IV準拠文書テンプレート作成・**デプロイ前鮮度チェック（P1-5）** |
| **第12条**（記録保持） | ✅ 準拠 | ✅ 準拠 | 暗号化・保持期間180日/365日対応・**高リスクデプロイ時の暗号化必須チェック（P1-6）** |
| **第13条**（透明性） | ⚠️ 部分準拠 | ⚠️ 部分準拠 | ユーザーガイド・第三者通知対応 |
| **第14条**（人間監視） | ⚠️ 部分準拠 | ⚠️ 部分準拠 | SLAタイムアウト管理・期限切れ検出・**システム停止/再開APIエンドポイント（Art.14(4)）** |
| **第15条**（精度・堅牢性） | ⚠️ 部分準拠 | ⚠️ 部分準拠 | ベンチマーク基盤・bench_mode安全強化・縮退モード追加 |
| **第50条**（透明性義務） | ❌ 未準拠 | ⚠️ 部分準拠 | `ai_disclosure`・`regulation_notice`・`ai_content_watermark` 追加 |

**凡例**: ✅ 準拠 | ⚠️ 部分準拠 | ❌ 未準拠

### 重要な注意事項（法務・運用）

- 本レビューは**法的助言ではなく**、技術実装と公開ドキュメントに基づくコンプライアンス評価である。
- 高リスク用途（雇用・教育・医療・金融・重要インフラ等）で展開する場合は、法務・DPO・セキュリティ責任者を含む正式レビューを必須とする。
- **セキュリティ警告**: 残存ギャップ（とくにArt.5/Art.14）は、規制違反だけでなく、不正利用・説明責任不履行につながるリスクが高い。Art.10/Art.50は文書化・フィールド追加により改善済みだが、運用面の定着が必要。

---

## 2. スコープと前提条件

### 対象システムの特性

VERITAS OSは「Proto-AGI Decision Operating System」として、LLM（主にOpenAI GPT-4.1-mini）をラップし、安全ゲート付き意思決定パイプラインを提供する。本システムは以下のユースケースを想定している：

- 企業レベルのAI意思決定支援
- 規制環境下でのLLM安全運用
- AIガバナンス・コンプライアンス管理

### リスク分類の前提

EU AI法第6条および附属書Ⅲに基づき、本システムが採用・展開される用途によって適用要件が異なる。本レビューでは**高リスクAIシステムとしての展開可能性**を前提に評価する（附属書Ⅲキーワード検出が雇用・医療・金融等の分野に対応しているため）。

### 評価手法（Evidence Levels）

- **E1: 実装確認** — コード上の機能存在を確認（静的レビュー）。
- **E2: 構成確認** — policy / 設定値 / 運用パラメータを確認。
- **E3: 文書確認** — README・運用手順・監査資料の存在を確認。
- **E4: 実運用確認（未実施）** — 本番ログ・監査証跡・SLA実績に基づく確認。

> 現時点の評価は主にE1〜E3。したがって、最終判定にはE4（運用実績）の追加検証が必要。

---

## 3. 条文別評価

### 第5条：禁止AI慣行

**要件**: 潜在意識的操作、社会スコアリング、差別的バイオメトリクス使用、リアルタイム遠隔バイオメトリクス識別等の禁止。

#### 実装状況

```python
# veritas_os/core/eu_ai_act_compliance_module.py:75-87
ARTICLE_5_PROHIBITED_PATTERNS = (
    "subliminal",
    "social scoring",
    "exploit vulnerability",
    "discriminat",
    "manipulat",
)
```

#### 準拠評価: ⚠️ 部分準拠

**良い点:**
- `EUAIActSafetyGateLayer4.validate_article_5()` により出力のポストチェックを実施
- `validate_article_5_input()` により入力プロンプトの禁止慣行検査を実施（✅ P1-1対応済）
- FUJI Gateのキーワードブロックリスト（`fuji_default.yaml:100-131`）でハードブロックを実施
- 自己言及的な警告「heuristic keyword-based」という誠実な免責事項を文書内に記載
- 多言語パターン対応（EN/JA/FR/DE/ES）、同義語・婉曲表現の拡充（✅ P1-1対応済）
- NFKC正規化・Unicode同形異体文字（ホモグリフ）正規化・スペース挿入攻撃検出による回避耐性強化（✅ GAP-01対応済）
- 外部分類モデル統合インターフェース（`external_classifier`パラメータ）（✅ P1-1対応済）
- `real-time remote biometric`・`facial recognition`・`gait recognition`等のバイオメトリクスパターン対応（✅ GAP-01対応済）

**重大ギャップ:**

1. **偽陰性リスク（Critical）**: ~~5パターンのみの単純なsubstring検索は、迂回が容易~~ → ✅ **大幅改善（GAP-01）** — 30+パターンに拡充、多言語対応（5言語）、NFKC正規化、ホモグリフ変換（キリル文字・ギリシャ文字→Latin）、ハイフン/ゼロ幅文字除去、スペース挿入回避検出を追加。ただし、依然としてキーワードベースのヒューリスティックであり、セマンティック検出には対応していない。モジュール自身が `"In production, replace or augment with policy models and legal review"` と明言（L10-12）している。

2. ~~**出力のみ検査**~~: ✅ **対応済（P1-1）** — `validate_article_5_input()` により入力プロンプトも検査対象に追加。`eu_compliance_pipeline` デコレータで自動的に入力検査を実行。

3. ~~**バイオメトリクス禁止**~~: ✅ **対応済（GAP-01）** — `real-time remote biometric`・`facial recognition`・`face identification`・`gait recognition`・`voiceprint`等のバイオメトリクス関連パターンを追加。多言語対応（`リアルタイム遠隔生体認証`・`reconnaissance faciale`・`Gesichtserkennung`等）。

**推奨**: 専用の分類モデルまたは法務レビューと組み合わせた多層防御が必要。外部分類モデル統合インターフェースは実装済み。

---

### 第6条・附属書Ⅲ：高リスクAIシステムの分類

**要件**: システムが高リスクAIシステムに該当するかどうかを判断し、該当する場合は第Ⅲ章の義務（第9〜15条）を遵守。

#### 準拠評価: ⚠️ 部分準拠（初回レビュー時: ❌ 未準拠）

**改善済み:**
- `docs/eu_ai_act/risk_classification_matrix.md` に想定用途別のリスク分類マトリクスを作成済み

**重大ギャップ（残存）:**

1. **自己分類の正式承認プロセスなし（Critical）**: リスク分類マトリクス文書は作成されたが、法務部門による正式承認・署名プロセスが未確立。

2. **CEマーキングプロセス未実装**: 高リスクAIシステムとして認定された場合に必要なCEマーキングのプロセスが存在しない。

**推奨**: リスク分類マトリクスの法務承認フローを確立し、各展開シナリオでのCEマーキング要件を明示する。

---

### 第9条：リスク管理システム

**要件**: ライフサイクル全体にわたる継続的なリスク管理システムの確立・文書化・維持。

#### 実装状況

```python
# veritas_os/core/eu_ai_act_compliance_module.py:252-274
def classify_annex_iii_risk(prompt: str) -> Dict[str, Any]:
    lowered = (prompt or "").lower()
    matched = [keyword for keyword in ANNEX_III_RISK_KEYWORDS if keyword in lowered]
    if not matched:
        return {"risk_level": "LOW", "risk_score": 0.2, "matched_categories": []}
    score = max(ANNEX_III_RISK_KEYWORDS[item] for item in matched)
    risk_level = "HIGH" if score >= 0.85 else "MEDIUM"
```

#### 準拠評価: ⚠️ 部分準拠

**良い点:**
- FUJI Gateによるリアルタイムリスクスコアリング（`fuji.py`）
- policy-basedリスクアクションマッピング（allow/warn/human_review/deny）
- ステークス別しきい値（低/中/高）
- 世界状態（WorldState）による累積リスク追跡
- `RISK_MONITORING_SCHEDULE` による日次〜年次のモニタリング活動定義（✅ P3-3対応済）
- `assess_continuous_risk_monitoring()` によるモニタリング完了状況の評価（✅ P3-3対応済）
- `docs/eu_ai_act/continuous_risk_monitoring.md` に運用手順書を整備（✅ P3-3対応済）
- `docs/eu_ai_act/risk_assessment.md` に残留リスク台帳を文書化（✅ P2-1対応済）
- `classify_annex_iii_risk()` にNFKC/ホモグリフ/ハイフン正規化を適用し、キーワード回避耐性を強化（✅ GAP-01d対応済）

**残存ギャップ:**

1. **ヒューリスティック依存（High）**: `classify_annex_iii_risk()` はキーワードマッチングのみ。附属書Ⅲの文脈（例：「medical」という単語が含まれても医療AIでない場合）を正確に判定できない。

2. ~~**デフォルトスコア0.2が過小評価（High）**~~: ✅ **対応済（GAP-06）** — キーワード未一致時のデフォルトを`MEDIUM/0.4`に引き上げ。未知ユースケースの過小評価リスクを軽減。

---

### 第10条：データ・データガバナンス

**要件**: 高リスクAIの場合、訓練・検証・テストデータセットの品質基準、バイアス評価、データ収集・処理の方針等。

#### 準拠評価: ⚠️ 部分準拠（初回レビュー時: ❌ 未準拠）

**改善済み:**
- `docs/eu_ai_act/model_card_gpt41_mini.md` にGPT-4.1-miniのモデルカードを作成（✅ P1-5対応済）
- `docs/eu_ai_act/bias_assessment_report.md` に保護属性別バイアス評価レポートを作成（✅ P1-5対応済）
- `docs/eu_ai_act/third_party_model_dpa_checklist.md` にDPA証跡チェックリストを作成（✅ P1-5対応済）
- `memory.py`の`add()`メソッドにデータリネージュ自動記録を追加（✅ GAP-05対応済）

**残存ギャップ:**

1. ~~**訓練データの品質管理なし**~~: ✅ **対応済（GAP-05）** — `validate_data_quality()` を `memory.py` の `add()` メソッドに統合し、データ取り込み時にArt. 10品質検証を自動実行。品質不合格データは取り込みを拒否する。

2. **バイアス評価の定期実行未確立**: レポートテンプレートは作成されたが、四半期評価の実行体制・責任者が未確定。

---

### 第11条：技術文書

**要件**: 高リスクAIの場合、開発前から規制当局への技術文書の提出義務（附属書IV参照）。

#### 準拠評価: ⚠️ 部分準拠

**良い点:**
- `README.md`（14,767行）・`README_JP.md`（16,399行）の充実した技術文書
- `docs/notes/`配下の各種レポート（TRUSTLOG_VERIFICATION, CODE_REVIEW_PRINCIPLESなど）
- SBOMによる依存関係文書化（`security/sbom/`）
- `docs/eu_ai_act/technical_documentation.md` — 附属書IV準拠の技術文書テンプレート（✅ P2-1対応済）
- `docs/eu_ai_act/intended_purpose.md` — 意図された用途と制限（✅ P2-1対応済）
- `docs/eu_ai_act/risk_assessment.md` — リスク評価と残留リスク（✅ P2-1対応済）
- `docs/eu_ai_act/performance_metrics.md` — 精度・堅牢性指標（✅ P2-1対応済）
- `docs/eu_ai_act/model_card_gpt41_mini.md` — GPT-4.1-miniモデルカード（✅ P1-5対応済）

**残存ギャップ:**

1. **附属書IV文書の継続更新体制**: テンプレートは作成されたが、リリースごとの更新義務・レビュー担当者が未確定。

2. **変更管理プロセスの正式化**: システム変更時の技術文書更新フローが未定義。

---

### 第12条：記録保持

**要件**: 高リスクAIは自動的なログ記録機能を備え、適切な期間保管すること。

#### 実装状況

```python
# veritas_os/logging/trust_log.py
# SHA-256ハッシュチェーン付きの改ざん防止ログ
# h_t = SHA256(h_{t-1} || r_t)
```

#### 準拠評価: ✅ 準拠

**良い点:**
- SHA-256ハッシュチェーンによる改ざん防止TrustLog
- Ed25519デジタル署名による署名付きエントリ
- 180日デフォルト保持設定 / 高リスク向け365日保持（`governance.json`）（✅ P3-1対応済）
- WORMミラーオプション（`VERITAS_TRUSTLOG_WORM_MIRROR_PATH`）
- スレッドセーフな書き込みロック
- 完全なリプレイ検証機能（`POST /v1/replay/{decision_id}`）
- アトミックI/O（`atomic_io.py`）による整合性保証
- Fernetベース静止暗号化サポート（`logging/encryption.py`）（✅ P3-2対応済）
- `get_retention_config()` によるリスクレベル別保持期間管理（✅ P3-1対応済）

**軽微な課題:**
- ~~暗号化はオプトイン方式（`VERITAS_ENCRYPTION_KEY`環境変数で有効化）。高リスク展開ではデフォルトONが望ましい。~~ ✅ **対応済（P1-6）** — `validate_audit_readiness_for_high_risk()` および `validate_deployment_readiness()` が暗号化キー未設定を自動検出し、高リスクデプロイ時に警告/拒否する仕組みを追加。

---

### 第13条：透明性・情報提供

**要件**: ユーザーと影響を受ける人々への情報提供。高リスクAIの指示・使用法の明示。

#### 実装状況

```python
# veritas_os/api/schemas.py
# DecideResponse には以下が含まれる:
# - rationale（思考プロセス・根拠）
# - evidence（証拠と出所）
# - critique（批評）
# - debate（多角的議論）
# - telos_score（価値整合スコア）
# - fuji（セーフティゲート詳細）
# - ai_disclosure（AI生成開示文）
# - regulation_notice（規制準拠通知）
# - affected_parties_notice（影響を受ける第三者への通知）
```

#### 準拠評価: ⚠️ 部分準拠

**良い点:**
- `DecideResponse`の詳細な説明可能性フィールド
- `rationale`による思考プロセスの開示
- 証拠ソース・信頼度の明示
- FUJI Gate判定理由の開示
- `ai_disclosure`フィールドによるAI生成開示（✅ P1-4対応済）
- `docs/user_guide_eu_ai_act.md` にエンドユーザー向け使用説明書を作成（✅ P2-4対応済）
- `ThirdPartyNotificationService` による第三者通知メカニズム（✅ P3-4対応済）
- `affected_parties_notice` フィールドの追加（✅ P3-4対応済）

**残存ギャップ:**

1. **エンドユーザー向け透明性の運用化**: `ai_disclosure`フィールドは追加済みだが、UI/フロントエンドでの表示実装が未確認。API消費者が確実に開示を表示するための実装ガイドラインが必要。

---

### 第14条：人間による監視

**要件**: 高リスクAIは、自然人による効果的な監視を可能にする設計でなければならない。

#### 実装状況

```python
# veritas_os/core/eu_ai_act_compliance_module.py:310-347
def apply_human_oversight_hook(
    *, trust_score, risk_level, response_payload, threshold=0.8,
) -> Dict[str, Any]:
    should_pause = float(trust_score) < threshold or risk_level == "HIGH"
    if should_pause:
        response_payload["status"] = "PENDING_HUMAN_REVIEW"
        response_payload["paused_by"] = "Art.14_human_oversight_hook"
    return dict(response_payload)
```

#### 準拠評価: ⚠️ 部分準拠

**良い点:**
- リスクスコア≥0.85での`human_review`アクション
- 複数の人間レビュートリガー（PII検出・低信頼度・高リスク分野）
- `PENDING_HUMAN_REVIEW`ステータスフラグ
- `self_healing.py`による人間レビュー要請の構造化追跡
- `HumanReviewQueue`によるキュー管理・Webhook通知・SLA追跡（✅ P1-3対応済）
- `fail_close`によるオーバーライド防止（✅ P1-6対応済）
- `check_expired_entries()`によるSLA超過エントリの自動失効検出（✅ GAP-14対応済）

**残存ギャップ:**

1. ~~**第14条(4)の中止機能**~~: ✅ **対応済** — `SystemHaltController` クラスによる緊急停止/再開メカニズムを実装。`POST /v1/system/halt`・`POST /v1/system/resume`・`GET /v1/system/halt-status` APIエンドポイントを追加し、外部からの運用制御を可能にした。

---

### 第15条：精度・堅牢性・サイバーセキュリティ

**要件**: 高リスクAIは適切なレベルの精度・堅牢性・サイバーセキュリティを達成し維持すること。

#### 準拠評価: ⚠️ 部分準拠

**良い点:**
- プロンプトインジェクション検出（5パターン、重み付きスコア）
- Unicode正規化（同形異体文字マップ）
- PII検出でのDoS対策（入力長制限・マッチ数上限）
- CI/CDセキュリティゲート（pip-audit・gitleaks・pnpm audit）
- SBOM（Software Bill of Materials）夜間生成
- カバレッジゲート85%以上
- `analyze_accuracy_benchmarks()` による精度モニタリングダッシュボード（✅ P2-2対応済）
- `docs/eu_ai_act/performance_metrics.md` に精度・堅牢性指標を文書化（✅ P2-1対応済）
- bench_mode安全制限強化：PII保護有効化・合成データ限定・実PIIマーカー拒否（✅ P2-3対応済）
- `build_degraded_response()` によるLLM不可時の安全な縮退応答生成（✅ GAP-16対応済）

**残存ギャップ:**

（主要な技術的ギャップは解消済み。運用面での定期的な堅牢性テスト実施体制の確立が推奨される。）

---

### 第50条：特定AIシステムの透明性義務

**要件**: AIが生成したコンテンツの開示（ディープフェイク等）。チャットボットの場合「AI操作中」を通知。

#### 準拠評価: ⚠️ 部分準拠（初回レビュー時: ❌ 未準拠）

**改善済み:**
- `DecideResponse.ai_disclosure` フィールド追加（デフォルト値: `"This response was generated by an AI system (VERITAS OS)."` ）（✅ P1-4対応済）
- `DecideResponse.regulation_notice` フィールド追加（デフォルト値: `"Subject to EU AI Act Regulation (EU) 2024/1689."` ）（✅ P1-4対応済）
- `build_ai_content_watermark()` によるC2PA互換の機械可読ウォーターマークメタデータ生成（✅ GAP-04対応済）
- `eu_compliance_pipeline` デコレータが `ai_content_watermark` を全レスポンスに自動付与（✅ GAP-04対応済）

**残存ギャップ:**

1. **UI表示の未確認**: `ai_disclosure`フィールドはAPIレスポンスに含まれるが、フロントエンド/クライアント側で確実に表示される保証がない。

---

## 4. 総合リスク評価マトリクス

### 残存ギャップ（対応が必要）

| ギャップID | 条文 | 説明 | 重大度 | 対応優先度 |
|-----------|------|------|--------|-----------|
| GAP-01 | Art.5 | Article 5禁止慣行のセマンティック検出未対応（キーワードベースは大幅強化済） | 🟡 High | P2 |
| GAP-02 | Art.6 | リスク分類の法務承認・CEマーキング未整備 | 🔴 Critical | P1 |

### 対応済みギャップ

| ギャップID | 条文 | 説明 | 対応内容 |
|-----------|------|------|---------|
| GAP-01a | Art.5 | 入力プロンプト検査なし | `validate_article_5_input()` 実装、`eu_compliance_pipeline` に統合（P1-1） |
| GAP-01b | Art.5 | バイオメトリクスパターン不足 | 30+パターンに拡充（多言語5言語対応） |
| GAP-01c | Art.5 | 文字列操作による回避 | NFKC正規化・ホモグリフ変換・ハイフン/ゼロ幅文字除去・スペース挿入検出 |
| GAP-01d | Art.9 | リスク分類の回避耐性なし | `classify_annex_iii_risk()` にNFKC/ホモグリフ/ハイフン正規化を適用 |
| GAP-03 | Art.14 | 人間レビューの実際のルーティング機構なし | `HumanReviewQueue`（キュー・Webhook通知・SLA追跡・fail-close）実装 |
| GAP-04 | Art.50 | 生成コンテンツのウォーターマークなし | `build_ai_content_watermark()`（C2PA互換メタデータ）実装・パイプライン統合 |
| GAP-05 | Art.10 | 訓練データ品質管理・リネージュなし | `validate_data_quality()` を `memory.py` の `add()` に統合、`memory.py` にデータリネージュ自動記録を追加 |
| GAP-06 | Art.9 | デフォルトリスクスコア0.2の過小評価 | デフォルトを0.4/MEDIUMに引き上げ |
| GAP-07 | Art.9 | 残留リスク文書化なし | `docs/eu_ai_act/risk_assessment.md` に残留リスク台帳を作成 |
| GAP-08 | Art.11 | 附属書IV準拠の技術文書なし | `docs/eu_ai_act/` に附属書IV準拠文書テンプレート4種を作成 |
| GAP-09 | Art.13 | エンドユーザー向け法定開示なし | `ai_disclosure`フィールド追加・ユーザーガイド作成 |
| GAP-10 | Art.15 | 精度ベンチマーク結果なし | `analyze_accuracy_benchmarks()` 実装・`performance_metrics.md` 作成 |
| GAP-11 | Art.15 | bench_modeでPII無効化リスク | bench_mode安全制限強化（PII有効化・合成データ限定） |
| GAP-12 | Art.12 | 暗号化なしデフォルト保存 | `logging/encryption.py` にFernetベース暗号化サポート追加 |
| GAP-13 | Art.12 | 90日保持がEU要件を満たすか未確認 | 保持期間を180日/365日（高リスク）に更新 |
| GAP-13b | Art.13 | UI/フロントエンド側での`ai_disclosure`表示 | `EUAIActDisclosure` コンポーネント実装、`console/page.tsx` に統合済み |
| GAP-14 | Art.14 | 人間レビューのタイムアウト管理なし | `HumanReviewQueue.check_expired_entries()` 実装（SLA超過検出・自動失効） |
| GAP-14b | Art.14 | Art.14(4)システム停止機能なし | `SystemHaltController`（halt/resume/status）実装、APIエンドポイント追加 |
| GAP-15 | Art.9 | 継続的リスクモニタリングプロセスなし | `RISK_MONITORING_SCHEDULE`・`assess_continuous_risk_monitoring()` 実装 |
| GAP-16 | Art.15 | LLM不可時の縮退モード未定義 | `build_degraded_response()` 実装（安全な縮退応答・人間エスカレーション推奨） |
| GAP-17 | Art.13 | 影響を受ける第三者への通知なし | `ThirdPartyNotificationService`・`affected_parties_notice` 実装 |
| P1-5 | Art.10/11 | デプロイ前コンプライアンス成果物鮮度チェックなし | `validate_deployment_readiness()` 実装、APIエンドポイント追加 |

---

## 5. 重大ギャップ詳細分析

### GAP-01: Article 5禁止慣行の検出精度（大幅改善済・セマンティック検出は未対応）

**該当コード**: `eu_ai_act_compliance_module.py:75-200`

~~現在の実装は5パターンの単純なsubstring検索のみ。~~ → ✅ **大幅改善**: 30+パターンに拡充（5言語対応）、以下の回避対策を実装：
- ✅ 多言語パターン（日本語・フランス語・ドイツ語・スペイン語）
- ✅ 同義語・婉曲表現の追加（social credit, citizen score, psychological manipulation等）
- ✅ ハイフン/ゼロ幅文字除去（`mani-pulate` → `manipulate`）
- ✅ NFKC Unicode正規化（全角文字→半角、合字分解等）
- ✅ Unicode同形異体文字（ホモグリフ）変換（キリル文字 `а`→`a`、ギリシャ文字 `Α`→`a` 等）
- ✅ スペース挿入回避検出（`m a n i p u l a t e` → `manipulate`）
- ✅ 入力プロンプト検査（`validate_article_5_input()`）
- ✅ 外部分類モデル統合インターフェース（`external_classifier`パラメータ）

**残存課題**: セマンティック類似度ベースの検出（embedding-based）は未実装。高度な迂回手法（間接表現・比喩・暗号化表現）には対応できない。

**技術的推奨（残り）**:
```python
# 残りの強化項目:
# 1. セマンティック類似度検索（embedding-based）の統合
# 2. 法務レビューを組み合わせた多層防御の運用化
# 3. 定期的なred-teamテストによる迂回手法の検出
# 4. external_classifierインターフェースを活用した専用分類モデル接続
```

### GAP-02: システムリスク自己分類の法務承認（Critical）

VERITAS OSは附属書Ⅲキーワード（biometric: 0.95、hiring: 0.90、healthcare: 0.91等）を検出・処理できるようになり、`docs/eu_ai_act/risk_classification_matrix.md` にリスク分類マトリクスを作成済みだが、法務部門による正式承認プロセスが未確立。高リスクAIシステムとして分類された場合、第Ⅲ章の義務（第9〜15条）の完全実施が法的に義務付けられる。

### GAP-03: 人間レビューの実装 ✅ 対応済

```python
# 実装済み（eu_ai_act_compliance_module.py）:
# - HumanReviewQueue: スレッドセーフなキューシステム
# - Webhook通知（VERITAS_HUMAN_REVIEW_WEBHOOK_URL）
# - SLAタイムアウト管理（デフォルト4時間）
# - check_expired_entries(): 期限切れエントリの自動検出
# - fail_close: オーバーライド防止
# - 承認/拒否ワークフロー（review()メソッド）
```

### GAP-04: AI生成コンテンツのウォーターマーク ✅ 対応済

`build_ai_content_watermark()` により、C2PA互換の機械可読ウォーターマークメタデータをAI生成コンテンツに付与。`eu_compliance_pipeline` デコレータにより全レスポンスに自動統合。SHA-256署名付きでコンテンツの出所を証明。

### GAP-05: データガバナンスの残存課題（対応済）

モデルカード（`docs/eu_ai_act/model_card_gpt41_mini.md`）・バイアス評価レポート（`docs/eu_ai_act/bias_assessment_report.md`）・DPAチェックリスト（`docs/eu_ai_act/third_party_model_dpa_checklist.md`）は作成済み。
- ✅ メモリシステム（`memory.py`）にデータリネージュ自動記録を追加（`doc["lineage"]`フィールド）
- ✅ `validate_data_quality()` を `memory.py` の `add()` メソッドに統合し、品質不合格データの取り込みを自動拒否（GAP-05対応済）
- バイアス評価の定期実行体制（四半期評価）が未確立

---

## 6. 推奨改善アクション

### P1（直ちに対応）

**[P1-1] Article 5禁止慣行の多層検出強化** ✅ 大幅対応済
- ✅ `ARTICLE_5_PROHIBITED_PATTERNS` を30+パターンに拡充（5言語対応、同義語・婉曲表現含む）
- ✅ 外部の専用禁止慣行分類モデルとの統合インターフェース追加（`external_classifier`パラメータ）
- ✅ NFKC Unicode正規化・ホモグリフ変換・ハイフン/ゼロ幅文字除去・スペース挿入回避検出を実装
- ✅ 入力プロンプト検査（`validate_article_5_input()`）を実装し、`eu_compliance_pipeline` に統合
- ✅ `classify_annex_iii_risk()` にも同等の正規化を適用（GAP-01d）
- 🔄 四半期毎のred-teamテスト実施を義務化（運用プロセス — 未確立）
- 🔄 セマンティック類似度検索（embedding-based）の統合（未実装）

**[P1-2] EU AI法リスク分類の法務承認プロセス確立**
- `docs/eu_ai_act/risk_classification_matrix.md` は作成済み ✅
- 法務部門による正式承認フロー（署名・バージョン管理）の確立が必要
- CEマーキングプロセスの設計・実装

**[P1-3] 人間レビューワークフローの実装**
```
# fuji_default.yaml コメントの実装を優先:
# "将来的には UI / Slack / CLI にフックして人間承認フローに使う"
# → 具体的には:
# - human_review キューへの書き込みAPI
# - Webhook通知エンドポイント
# - レビューSLA管理（例: 4時間以内）
```

**[P1-4] AI相互作用の法定開示フィールド追加** ✅ 対応済
```python
# schemas.pyのDecideResponseに追加済み:
ai_disclosure: str = "This response was generated by an AI system (VERITAS OS)."
regulation_notice: str = "Subject to EU AI Act Regulation (EU) 2024/1689."
```

**[P1-5] モデルカードとバイアス評価レポートの作成** ✅ 対応済
- `docs/eu_ai_act/model_card_gpt41_mini.md` を新設済み（附属書IV対応）✅：
  - モデル識別情報（提供者、バージョン、更新日、利用エンドポイント）
  - 意図された用途 / 禁止用途 / 既知の制約（幻覚、非決定性、領域外質問）
  - 安全制御の依存関係（FUJI設定、human_review閾値、fallback条件）
  - 評価プロトコル（評価データ、評価頻度、再現手順、責任者）
- `docs/eu_ai_act/bias_assessment_report.md` を新設済み ✅：
  - 最低評価軸: 性別、年齢層、言語、地域（適用可能な範囲で民族・障害を追加）
  - 指標: 誤拒否率 / 誤受理率 / しきい値近傍の判定安定性
  - 判定基準: 群間差分の許容幅を事前定義し、逸脱時の是正計画を必須化
- `docs/eu_ai_act/third_party_model_dpa_checklist.md` を新設済み ✅：
  - DPA締結状況、データ越境移転、サブプロセッサ一覧、保存期間、削除要件
  - OpenAI公開資料への参照（モデルカード / セキュリティ文書）の更新監視担当者
- **残課題**: ~~以下の運用ゲート（リリースブロッカー）のCI/CD統合が未実装：~~
  - ✅ `validate_deployment_readiness()` 関数を追加し、モデルカード・バイアス評価・DPAチェックリストの鮮度を自動検証
  - ✅ `GET /v1/compliance/deployment-readiness` APIエンドポイントを追加
  - モデルカード未更新（最終更新から90日超）→ ✅ 自動検出
  - バイアス評価未実施（四半期評価なし）→ ✅ 自動検出（90日）
  - DPA証跡未確認（契約ステータス不明）→ ✅ 自動検出（180日）
  - 上記のいずれか該当時は高リスク用途へのデプロイを禁止 → CI/CD統合は別途対応

**[P1-6] セキュリティ即時是正（最優先）**
- human_review判定時に「自動実行停止」を強制するフェイルクローズ制御を追加（✅ `apply_human_oversight_hook()` で `fail_close=True` 時に `decision_blocked=True` を設定し、`decision_status="hold"` でブロック）
- bench_modeでのPII保護無効化を禁止（✅ P2-3で合成データ限定を強制済み）
- TrustLogおよびMemory保存データの暗号化を既定ONへ変更（✅ P3-2でオプトイン暗号化を実装済み。✅ 高リスクデプロイ時に暗号化未設定を検出・拒否する仕組みを `validate_audit_readiness_for_high_risk()` および `validate_deployment_readiness()` に追加）
- 監査不備がある環境（ログ保存期間不足・通知フロー未整備）では高リスク用途を明示的に拒否（✅ `validate_audit_readiness_for_high_risk()` が `governance.json` からログ保持期間を自動読み取り、Webhook設定・暗号化キー設定を環境変数から自動検出し、不備がある場合は高リスク決定を拒否）

### P2（3ヶ月以内に対応）

**[P2-1] 附属書IV準拠の技術文書テンプレート作成** ✅ 対応済

EU AI法附属書IVの要求に合わせた技術文書テンプレートを`docs/eu_ai_act/`配下に作成：
- `technical_documentation.md`（一般的技術情報） ✅
- `intended_purpose.md`（意図された用途と制限） ✅
- `risk_assessment.md`（リスク評価と残留リスク） ✅
- `performance_metrics.md`（精度・堅牢性指標） ✅

**[P2-2] 精度ベンチマーク基盤の確立** ✅ 対応済
- `doctor.py`に`analyze_accuracy_benchmarks()`関数を追加し、継続的な精度モニタリングダッシュボードを実装 ✅
- ベンチマーク結果の統計分析（平均・最小・最大）とドリフト検出（直近5回の精度が全体平均から5%以上低下した場合にアラート） ✅
- `doctor_report.json`に`accuracy`セクションを追加 ✅

**[P2-3] bench_modeの安全制限強化** ✅ 対応済
```yaml
# fuji_default.yaml の bench_mode:
bench_mode:
  when_mode_in: ["bench", "internal_eval"]
  pii:
    enabled: true           # P1-6: PII protection MUST remain enabled
  synthetic_data_only: true  # P1-6: bench_mode requires synthetic data
  reject_real_pii_markers: true  # P2-3: Runtime validation enforced
```
- `validate_bench_mode_synthetic_data()`関数を追加し、実PIIマーカー（メールドメイン・SSN・クレジットカード・マイナンバー等）を検出して拒否 ✅
- `eu_compliance_pipeline`デコレータにP2-3チェックを統合 ✅

**[P2-4] エンドユーザー向け使用説明書の作成** ✅ 対応済
- `docs/user_guide_eu_ai_act.md`として作成 ✅:
  - システムの意図された用途と限界 ✅
  - 人間監視の方法と責任者 ✅
  - 異議申し立て（コンテスト）の方法 ✅

### P3（6ヶ月以内に対応）

**[P3-1] ログ保持期間のEU AI Act要件確認・調整** ✅ 対応済
- `governance.json` の `retention_days` を 90日 → 180日（最低6ヶ月）に更新 ✅
- 高リスク展開向けに `retention_days_high_risk: 365` を追加 ✅
- `eu_ai_act_compliance_module.py` に `get_retention_config()` 関数を追加し、リスクレベル別の保持期間を返す ✅

**[P3-2] 静止暗号化の標準化** ✅ 対応済
- `veritas_os/logging/encryption.py` に Fernet ベースの暗号化/復号ユーティリティを追加 ✅
- `trust_log.py` の JSONL 書き込み時にオプショナル暗号化サポートを追加 ✅
- 環境変数 `VERITAS_ENCRYPTION_KEY` で暗号化キーを指定可能 ✅
- `get_encryption_status()` で監査向けの暗号化状態確認が可能 ✅

**[P3-3] 継続的リスクモニタリングプロセスの確立** ✅ 対応済
- `eu_ai_act_compliance_module.py` に `RISK_MONITORING_SCHEDULE`（日次〜年次のモニタリング活動定義）を追加 ✅
- `assess_continuous_risk_monitoring()` 関数でモニタリング完了状況の評価が可能 ✅
- `docs/eu_ai_act/continuous_risk_monitoring.md` に運用手順書を作成 ✅

**[P3-4] 影響を受ける第三者への通知メカニズム** ✅ 対応済
- `eu_ai_act_compliance_module.py` に `ThirdPartyNotificationService` クラスを追加 ✅
- 高リスク決定（雇用・与信等）時の第三者通知レコード生成 ✅
- 影響を受ける者の権利（説明を求める権利、異議申立権、人間レビュー権）を通知に含める ✅
- `DecideResponse` に `affected_parties_notice` フィールドを追加 ✅
- Webhook 連携（`VERITAS_THIRD_PARTY_NOTIFICATION_WEBHOOK_URL`）対応 ✅

---

## 7. 30/60/90日実行ロードマップ（追加）

| 期間 | 到達目標 | 完了条件（DoD） | 進捗 |
|------|----------|-----------------|------|
| 0-30日 | P1項目の設計確定と実装着手 | Art.50開示フィールド追加、human_reviewキュー設計、法務レビュー体制の責任者割当 | ✅ Art.50対応済 / 🔄 human_review・法務承認は未完 |
| 31-60日 | P1実装完了 + P2文書化開始 | 人間レビュー実運用、モデルカード初版、附属書IVテンプレート公開 | ✅ モデルカード・附属書IV完了 / 🔄 人間レビュー実運用は未完 |
| 61-90日 | P2主要項目を運用に接続 | 精度ベンチ結果の定期更新、残留リスク台帳、ユーザー向け説明書の配布開始 | ✅ すべて完了 |

### KPI（運用監査向け）

- `human_review_required`案件の**100%が人間承認済み**になるまで自動実行しない。
- AI開示ラベル（Art.50）を**ユーザー向け出力の100%**に付与。
- 監査ログ欠損率を**0%**に維持。
- 高リスク用途の判定漏れ（事後検知）を四半期ごとに低減。

---

## 8. 付録：コード参照インデックス

| 条文 | ファイル | 行 | 説明 |
|------|---------|-----|------|
| Art.5 | `core/eu_ai_act_compliance_module.py` | 75-87 | 禁止慣行パターン定義 |
| Art.5 | `core/eu_ai_act_compliance_module.py` | 166-249 | `EUAIActSafetyGateLayer4` |
| Art.5 | `policies/fuji_default.yaml` | 100-131 | ハードブロックキーワード |
| Art.6 | `docs/eu_ai_act/risk_classification_matrix.md` | (全体) | リスク分類マトリクス |
| Art.9 | `core/eu_ai_act_compliance_module.py` | 252-274 | `classify_annex_iii_risk()` |
| Art.9 | `core/eu_ai_act_compliance_module.py` | 56-69 | `ANNEX_III_RISK_KEYWORDS` |
| Art.9 | `policies/fuji_default.yaml` | 23-45 | リスクしきい値設定 |
| Art.9 | `core/fuji.py` | (全体) | FUJIゲートリスクスコアリング |
| Art.9 | `core/eu_ai_act_compliance_module.py` | 799-824 | `RISK_MONITORING_SCHEDULE` |
| Art.9 | `core/eu_ai_act_compliance_module.py` | 827-870 | `assess_continuous_risk_monitoring()` |
| Art.9 | `docs/eu_ai_act/risk_assessment.md` | (全体) | リスク評価・残留リスク台帳 |
| Art.9 | `docs/eu_ai_act/continuous_risk_monitoring.md` | (全体) | 継続的リスクモニタリング運用手順書 |
| Art.10 | `docs/eu_ai_act/model_card_gpt41_mini.md` | (全体) | GPT-4.1-miniモデルカード |
| Art.10 | `docs/eu_ai_act/bias_assessment_report.md` | (全体) | バイアス評価レポート |
| Art.10 | `docs/eu_ai_act/third_party_model_dpa_checklist.md` | (全体) | DPA証跡チェックリスト |
| Art.11 | `docs/eu_ai_act/technical_documentation.md` | (全体) | 附属書IV準拠技術文書 |
| Art.11 | `docs/eu_ai_act/intended_purpose.md` | (全体) | 意図された用途と制限 |
| Art.11 | `docs/eu_ai_act/performance_metrics.md` | (全体) | 精度・堅牢性指標 |
| Art.11/12 | `core/eu_ai_act_compliance_module.py` | 277-307 | `build_tamper_evident_trustlog_package()` |
| Art.11/12 | `logging/trust_log.py` | (全体) | SHA-256ハッシュチェーン |
| Art.11/12 | `audit/trustlog_signed.py` | (全体) | Ed25519署名 |
| Art.12 | `api/governance.json` | (全体) | ログ保持期間設定（180日/365日） |
| Art.12 | `core/eu_ai_act_compliance_module.py` | 764-793 | `get_retention_config()` |
| Art.12 | `logging/encryption.py` | (全体) | 静止暗号化ユーティリティ |
| Art.13 | `api/schemas.py` | 430+ | `DecideResponse`構造（`ai_disclosure`・`regulation_notice`・`affected_parties_notice`含む） |
| Art.13 | `docs/user_guide_eu_ai_act.md` | (全体) | エンドユーザー向け使用説明書 |
| Art.13 | `core/eu_ai_act_compliance_module.py` | 876+ | `ThirdPartyNotificationService` |
| Art.14 | `core/eu_ai_act_compliance_module.py` | 310-347 | `apply_human_oversight_hook()` |
| Art.14 | `core/eu_ai_act_compliance_module.py` | 353-520 | `HumanReviewQueue`（キュー・Webhook・SLA・期限切れ検出） |
| Art.14 | `core/eu_ai_act_compliance_module.py` | 134-140 | 基本権役割定義 |
| Art.14 | `core/self_healing.py` | (全体) | 人間レビュー要請追跡 |
| Art.15 | `core/sanitize.py` | (全体) | PIIマスク・DoS対策 |
| Art.15 | `policies/fuji_default.yaml` | 220-242 | プロンプトインジェクション検出 |
| Art.15 | `policies/fuji_default.yaml` | 243-268 | Unicode正規化 |
| Art.15 | `compliance/report_engine.py` | (全体) | コンプライアンスレポート生成 |
| Art.15 | `scripts/doctor.py` | 226+ | `analyze_accuracy_benchmarks()` |
| Art.15 | `core/eu_ai_act_compliance_module.py` | 544-588 | `validate_bench_mode_synthetic_data()` |
| Art.15 | `core/eu_ai_act_compliance_module.py` | 850+ | `build_degraded_response()` |
| Art.15 | `policies/fuji_default.yaml` | 193-202 | bench_mode安全制限設定 |
| Art.50 | `core/eu_ai_act_compliance_module.py` | 800+ | `build_ai_content_watermark()` |
| Art.10 | `core/memory.py` | 253+ | `add()` データリネージュ自動記録 |
| Art.10 | `core/memory.py` | 282+ | `add()` データ品質検証統合 (GAP-05) |
| Art.10/11 | `core/eu_ai_act_compliance_module.py` | 1383+ | `validate_deployment_readiness()` デプロイ前鮮度チェック (P1-5) |
| Art.9/12 | `core/eu_ai_act_compliance_module.py` | 668+ | `_read_governance_log_retention()` governance.json からの保持期間自動読み取り (P1-6) |
| Art.9/12 | `core/eu_ai_act_compliance_module.py` | 685+ | `validate_audit_readiness_for_high_risk()` 暗号化・Webhook・保持期間の自動検出 (P1-6) |
| Art.14(4) | `api/server.py` | 2910+ | `/v1/system/halt`・`/v1/system/resume`・`/v1/system/halt-status` API |
| Art.5 | `core/eu_ai_act_compliance_module.py` | 175-203 | `_CONFUSABLE_ASCII_MAP`・`_SPACED_EVASION_RE` (GAP-01) |
| Art.5 | `core/eu_ai_act_compliance_module.py` | 262-280 | `_normalise_text()` NFKC/ホモグリフ/スペース挿入正規化 (GAP-01) |
| Art.5 | `core/eu_ai_act_compliance_module.py` | 310-337 | `validate_article_5_input()` 入力プロンプト検査 (P1-1) |
| Art.9 | `core/eu_ai_act_compliance_module.py` | 340-368 | `classify_annex_iii_risk()` NFKC/ホモグリフ正規化 (GAP-01d) |

---

## まとめ

VERITAS OSはEU AI法準拠を真剣に取り組む姿勢を示しており、特に**第12条（記録保持）**においては業界最高水準の実装（ハッシュチェーン・Ed25519署名・WORM対応・暗号化サポート・180日/365日保持）を提供している。

初回レビューで特定した17件のギャップのうち **16件を解消済み** であり、附属書IV準拠文書、モデルカード、バイアス評価、ユーザーガイド、第三者通知メカニズム、AI開示フィールド、AIコンテンツウォーターマーク、データリネージュ追跡、データ品質検証統合、人間レビューキュー・タイムアウト管理、システム停止/再開API、デプロイ前鮮度チェック、LLM縮退モード等の整備が完了した。Art.5禁止慣行検出はNFKC正規化・ホモグリフ変換・入力検査・外部分類モデルIF等の大幅強化により、CriticalからHighに引き下げた。

一方、**1件のCriticalギャップ**（GAP-02: リスク分類の法務承認）および**1件のHighギャップ**（GAP-01: セマンティック検出の未対応）は引き続き対応が必要であり、本番環境での高リスクAIとしての展開前に解決する必要がある。

法的リスクの観点からは、文書化・透明性・人間監視の面で大幅な改善が見られるものの、**運用面のギャップ（法務承認フロー）が残存しており、現時点ではシステムを高リスクAIとして規制当局へ届け出るには追加対応が必要**である。推奨された改善アクションの実施後、独立した第三者による適合性評価を受けることを強く推奨する。

---

*本レビューは技術コードレビューに基づく予備的分析であり、法的アドバイスを構成するものではない。EU AI法の最終的な準拠判定は、EU法の資格ある法律専門家によるレビューが必要である。*
