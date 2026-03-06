# VERITAS OS — EU AI Act 準拠レビュー

**レビュー日**: 2026-03-06
**対象バージョン**: VERITAS OS v2.0
**ブランチ**: `claude/eu-ai-act-compliance-jY2sE`
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

VERITAS OSはEU AI法への準拠を明示的に設計目標として掲げており、技術的な基盤の多くが規制要件を先取りしている。しかし、**本レビューにより17件の準拠ギャップ（うち5件が重大）**を特定した。

| 評価カテゴリ | 状態 |
|-------------|------|
| **第5条**（禁止慣行） | ⚠️ 部分準拠 |
| **第6条/附属書Ⅲ**（高リスク分類） | ❌ 未準拠 |
| **第9条**（リスク管理） | ⚠️ 部分準拠 |
| **第10条**（データガバナンス） | ❌ 未準拠 |
| **第11条**（技術文書） | ⚠️ 部分準拠 |
| **第12条**（記録保持） | ✅ 準拠 |
| **第13条**（透明性） | ⚠️ 部分準拠 |
| **第14条**（人間監視） | ⚠️ 部分準拠 |
| **第15条**（精度・堅牢性） | ⚠️ 部分準拠 |
| **第50条**（透明性義務） | ❌ 未準拠 |

**凡例**: ✅ 準拠 | ⚠️ 部分準拠 | ❌ 未準拠

### 重要な注意事項（法務・運用）

- 本レビューは**法的助言ではなく**、技術実装と公開ドキュメントに基づくコンプライアンス評価である。
- 高リスク用途（雇用・教育・医療・金融・重要インフラ等）で展開する場合は、法務・DPO・セキュリティ責任者を含む正式レビューを必須とする。
- **セキュリティ警告**: 現状のギャップ（とくにArt.5/Art.10/Art.14/Art.50）は、規制違反だけでなく、不正利用・情報漏えい・説明責任不履行につながるリスクが高い。

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
# veritas_os/core/eu_ai_act_compliance_module.py:50-56
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
- FUJI Gateのキーワードブロックリスト（`fuji_default.yaml:100-131`）でハードブロックを実施
- 自己言及的な警告「heuristic keyword-based」という誠実な免責事項を文書内に記載

**重大ギャップ:**

1. **偽陰性リスク（Critical）**: 5パターンのみの単純なsubstring検索は、迂回が容易。例えば `"mani-pulate"` や多言語表現、暗号化表現による禁止慣行が検出されない。モジュール自身が `"In production, replace or augment with policy models and legal review"` と明言（L10-12）している。

2. **出力のみ検査**: 現在の実装はLLM生成テキスト（output）のみを検査しており、入力プロンプトが禁止慣行を誘発するよう設計されていても検出できない。

3. **バイオメトリクス禁止**: 第5条(1)(a)で明示的に禁止されているリアルタイムバイオメトリクス識別への対応コードが存在しない。

**推奨**: 専用の分類モデルまたは法務レビューと組み合わせた多層防御が必要。

---

### 第6条・附属書Ⅲ：高リスクAIシステムの分類

**要件**: システムが高リスクAIシステムに該当するかどうかを判断し、該当する場合は第Ⅲ章の義務（第9〜15条）を遵守。

#### 準拠評価: ❌ 未準拠

**重大ギャップ:**

1. **自己分類の欠如（Critical）**: VERITAS OS自体がEU AI法の適用リスクカテゴリ（許容不可能・高リスク・限定リスク・最小リスク）のいずれに分類されるかを明示した文書が存在しない。

2. **用途別の分類マトリクスなし**: 雇用支援・医療・金融等、附属書Ⅲに列挙された高リスク分野でシステムが使用される場合の分類基準が未定義。

3. **CEマーキングプロセス未実装**: 高リスクAIシステムとして認定された場合に必要なCEマーキングのプロセスが存在しない。

**推奨**: 「想定用途別リスク分類マトリクス」を作成し、各展開シナリオでのEU AI法適用区分を明記する。

---

### 第9条：リスク管理システム

**要件**: ライフサイクル全体にわたる継続的なリスク管理システムの確立・文書化・維持。

#### 実装状況

```python
# veritas_os/core/eu_ai_act_compliance_module.py:105-124
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

**重大ギャップ:**

1. **ヒューリスティック依存（High）**: `classify_annex_iii_risk()` はキーワードマッチングのみ。附属書Ⅲの文脈（例：「medical」という単語が含まれても医療AIでない場合）を正確に判定できない。

2. **デフォルトスコア0.2が過小評価（High）**: キーワード未一致時に常にLOW/0.2を返すが、新規ユースケースへの適用など未知リスクが過小評価される。

3. **継続的リスクモニタリング不在**: ライフサイクル全体でのリスク評価プロセス（開発・テスト・デプロイ・監視・廃止）の文書化がない。

4. **残留リスク文書化なし**: 第9条(2)(c)が要求する「残留リスクの見積もりと評価」文書がない。

---

### 第10条：データ・データガバナンス

**要件**: 高リスクAIの場合、訓練・検証・テストデータセットの品質基準、バイアス評価、データ収集・処理の方針等。

#### 準拠評価: ❌ 未準拠

**重大ギャップ:**

1. **LLMモデルのデータカードなし（Critical）**: 使用するOpenAI GPT-4.1-miniのトレーニングデータに関するデータカード・モデルカードが存在しない。第三者モデルを使用する場合でも、このリスクを文書化する義務がある。

2. **バイアス評価なし**: 性別・民族・年齢等の保護属性に関するバイアス評価が実施・文書化されていない。

3. **データリネージュなし**: メモリシステム（`memory.py`）に格納されるデータの出所・変換履歴を追跡する機能がない。

4. **訓練データの品質管理なし**: `datasets/dataset.jsonl` への書き込み時に、データ品質・代表性の検証ステップが存在しない。

---

### 第11条：技術文書

**要件**: 高リスクAIの場合、開発前から規制当局への技術文書の提出義務（附属書IV参照）。

#### 準拠評価: ⚠️ 部分準拠

**良い点:**
- `README.md`（14,767行）・`README_JP.md`（16,399行）の充実した技術文書
- `docs/notes/`配下の各種レポート（TRUSTLOG_VERIFICATION, CODE_REVIEW_PRINCIPLESなど）
- SBOMによる依存関係文書化（`security/sbom/`）

**重大ギャップ:**

1. **附属書IV準拠文書の欠如（High）**: EU AI法附属書IVが規定する以下の項目が体系的に文書化されていない：
   - 意図された目的の詳細説明
   - 開発に使用された方法論
   - システムの能力と限界
   - パフォーマンス指標とテスト結果
   - 既知リスクと緩和措置
   - 変更管理プロセス

2. **モデルカードの不在**: 使用するAIモデルの能力・制限・バイアス情報のモデルカードがない。

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
- 90日デフォルト保持設定（`governance.json`）
- WORMミラーオプション（`VERITAS_TRUSTLOG_WORM_MIRROR_PATH`）
- スレッドセーフな書き込みロック
- 完全なリプレイ検証機能（`POST /v1/replay/{decision_id}`）
- アトミックI/O（`atomic_io.py`）による整合性保証

**軽微な課題:**
- デフォルトが平文JSONL（暗号化なし）。高リスク展開では静止暗号化が望ましい。
- 保持期間90日がEU AI法の要件（高リスクAIは少なくとも6ヶ月）を満たすか確認が必要。

---

### 第13条：透明性・情報提供

**要件**: ユーザーと影響を受ける人々への情報提供。高リスクAIの指示・使用法の明示。

#### 実装状況

```python
# veritas_os/api/schemas.py
# DecideResponse には以下が含まれる:
# - reasoning_trace（思考プロセス）
# - evidence（証拠と出所）
# - critique（批評）
# - debate（多角的議論）
# - telos_score（価値整合スコア）
# - fuji（セーフティゲート詳細）
```

#### 準拠評価: ⚠️ 部分準拠

**良い点:**
- `DecideResponse`の詳細な説明可能性フィールド
- `reasoning_trace`による思考プロセスの開示
- 証拠ソース・信頼度の明示
- FUJI Gate判定理由の開示

**重大ギャップ:**

1. **エンドユーザー向け透明性の欠如（High）**: API技術出力は開発者向けであり、一般ユーザーへの「このシステムはAIです」という法定開示メカニズムが存在しない。

2. **使用説明書の不整備**: 第13条(3)が要求するユーザー向け使用説明書（意図された用途・制限事項・人間監視方法を含む）が専用文書として存在しない。

3. **影響を受ける者への通知なし**: AIシステムによる決定が影響する第三者（雇用決定・信用評価等）への通知メカニズムがない。

---

### 第14条：人間による監視

**要件**: 高リスクAIは、自然人による効果的な監視を可能にする設計でなければならない。

#### 実装状況

```python
# veritas_os/core/eu_ai_act_compliance_module.py:160-176
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

**重大ギャップ:**

1. **実際のルーティング機構なし（Critical）**: `apply_human_oversight_hook()`はフラグをセットするだけで、実際に人間のレビュアーにルーティングするシステム（UI・Slack・メール等）が存在しない。`fuji_default.yaml`のコメント「将来的には UI / Slack / CLI にフックして人間承認フローに使う」がその証左。

2. **オーバーライド防止なし**: 人間レビューが必要とマークされた決定を、後続の自動プロセスがオーバーライドできるかどうかの制御機構がない。

3. **人間レビューのタイムアウト管理なし**: レビュー期限・エスカレーションポリシーが未定義。

4. **第14条(4)の中止機能**: 人間が必要と判断した場合にシステムを中断できる機能の明示的な実装がない。

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

**重大ギャップ:**

1. **精度ベンチマークなし（High）**: 第15条(1)の「適切な精度レベル」を定量化したベンチマーク結果がない。`AGI_BENCH_INTEGRATION_GUIDE.md`が存在するが、実際のベンチマーク結果の文書化がない。

2. **連続精度モニタリングなし**: 本番環境でのモデル性能劣化（ドリフト）を検出する継続的モニタリングシステムがない。

3. **フォールバック機能**: LLMが利用不可の場合の縮退動作（degraded mode）が未定義。

4. **Bench_modeのPII無効化はリスク（High）**: `fuji_default.yaml:194-198`でbench_modeではPIIチェックが無効化される。ベンチマークデータが実PII含む場合に規制違反となりうる。

---

### 第50条：特定AIシステムの透明性義務

**要件**: AIが生成したコンテンツの開示（ディープフェイク等）。チャットボットの場合「AI操作中」を通知。

#### 準拠評価: ❌ 未準拠

**重大ギャップ:**

1. **AI相互作用通知なし（Critical）**: `/v1/decide`エンドポイントのレスポンスにユーザー向けの「このレスポンスはAIが生成しました」という法定開示フィールドがない。

2. **生成コンテンツのウォーターマークなし**: AI生成コンテンツの機械可読なマーキング（第50条(2)）が未実装。

---

## 4. 総合リスク評価マトリクス

| ギャップID | 条文 | 説明 | 重大度 | 対応優先度 |
|-----------|------|------|--------|-----------|
| GAP-01 | Art.5 | Article 5禁止慣行の単純keyword検出 | 🔴 Critical | P1 |
| GAP-02 | Art.6 | 自己リスク分類文書の欠如 | 🔴 Critical | P1 |
| GAP-03 | Art.14 | 人間レビューの実際のルーティング機構なし | 🔴 Critical | P1 |
| GAP-04 | Art.50 | AI相互作用の法定開示なし | 🔴 Critical | P1 |
| GAP-05 | Art.10 | LLMモデルのデータカード・バイアス評価なし | 🔴 Critical | P1 |
| GAP-06 | Art.9 | デフォルトリスクスコア0.2の過小評価 | 🟠 High | P2 |
| GAP-07 | Art.9 | 残留リスク文書化なし | 🟠 High | ~~P2~~ ✅ 対応済 |
| GAP-08 | Art.11 | 附属書IV準拠の技術文書なし | 🟠 High | ~~P2~~ ✅ 対応済 |
| GAP-09 | Art.13 | エンドユーザー向け法定開示なし | 🟠 High | ~~P2~~ ✅ 対応済 |
| GAP-10 | Art.15 | 精度ベンチマーク結果なし | 🟠 High | ~~P2~~ ✅ 対応済 |
| GAP-11 | Art.15 | bench_modeでPII無効化リスク | 🟠 High | ~~P2~~ ✅ 対応済 |
| GAP-12 | Art.12 | 暗号化なしデフォルト保存 | 🟡 Medium | ~~P3~~ ✅ 対応済 |
| GAP-13 | Art.12 | 90日保持がEU要件を満たすか未確認 | 🟡 Medium | ~~P3~~ ✅ 対応済 |
| GAP-14 | Art.14 | 人間レビューのタイムアウト管理なし | 🟡 Medium | P3 |
| GAP-15 | Art.9 | 継続的リスクモニタリングプロセスなし | 🟡 Medium | ~~P3~~ ✅ 対応済 |
| GAP-16 | Art.15 | LLM不可時の縮退モード未定義 | 🟡 Medium | P3 |
| GAP-17 | Art.13 | 影響を受ける第三者への通知なし | 🟡 Medium | ~~P3~~ ✅ 対応済 |

---

## 5. 重大ギャップ詳細分析

### GAP-01: Article 5禁止慣行の検出精度（Critical）

**該当コード**: `eu_ai_act_compliance_module.py:50-102`

現在の実装は5パターンの単純なsubstring検索のみ。悪意ある行為者は以下の手法で容易に回避できる：
- 多言語表現（日本語・フランス語等）での禁止慣行記述
- 同義語・婉曲表現の使用
- 文字列分割（`mani-pulate` → `manipulate`）

**技術的推奨**:
```python
# 必要な強化:
# 1. 多言語対応の禁止慣行分類モデル（fine-tuned classifier）
# 2. セマンティック類似度検索（embedding-based）
# 3. 法務レビューを組み合わせた多層防御
# 4. 定期的なred-teamテストによる迂回手法の検出
```

### GAP-02: システムリスク自己分類の欠如（Critical）

VERITAS OSは附属書Ⅲキーワード（biometric: 0.95、hiring: 0.90、healthcare: 0.91等）を検出・処理できるが、システム自体がどのリスクカテゴリに属するかの公式文書がない。高リスクAIシステムとして分類された場合、第Ⅲ章の義務（第9〜15条）の完全実施が法的に義務付けられる。

### GAP-03: 人間レビューの実装不完全（Critical）

```python
# 現状: フラグのみ（eu_ai_act_compliance_module.py:172-174）
response_payload["status"] = "PENDING_HUMAN_REVIEW"
response_payload["paused_by"] = "Art.14_human_oversight_hook"

# 必要な実装:
# - 実際のキューシステム（Redis/SQS等）
# - レビュアーへの通知（Slack/Email/Webhook）
# - レビュー期限管理
# - 承認/拒否ワークフロー
# - オーバーライド防止ロック
```

### GAP-04: AI相互作用の法定開示（Critical）

EU AI法第50条により、一般市民向けに使用されるAIシステムは「AI操作中であること」を開示する義務がある。現在のAPIレスポンスにこの開示フィールドが存在しない。

### GAP-05: データガバナンスの不備（Critical）

使用するOpenAI GPT-4.1-miniは第三者モデルだが、EU AI法はプロバイダー（VERITAS OS開発者）に対してもデータガバナンス要件を課す。特に：
- GPT-4.1-miniの訓練データに関する情報の文書化
- バイアス評価（対象ユーザー・地域での公平性検証）
- OpenAIとのデータ処理契約（DPA）の締結確認

---

## 6. 推奨改善アクション

### P1（直ちに対応）

**[P1-1] Article 5禁止慣行の多層検出強化**
- `eu_ai_act_compliance_module.py`の`ARTICLE_5_PROHIBITED_PATTERNS`を多言語・語義的検出に拡張
- 外部の専用禁止慣行分類モデルとの統合インターフェースを追加
- 四半期毎のred-teamテスト実施を義務化

**[P1-2] EU AI法リスク分類文書の作成**
- 想定展開シナリオ別（一般用・雇用支援・医療補助等）の分類マトリクス文書を作成
- 各シナリオでの適用条文と遵守義務を明示

**[P1-3] 人間レビューワークフローの実装**
```
# fuji_default.yaml コメントの実装を優先:
# "将来的には UI / Slack / CLI にフックして人間承認フローに使う"
# → 具体的には:
# - human_review キューへの書き込みAPI
# - Webhook通知エンドポイント
# - レビューSLA管理（例: 4時間以内）
```

**[P1-4] AI相互作用の法定開示フィールド追加**
```python
# schemas.pyのDecideResponseに追加:
ai_disclosure: str = "This response was generated by an AI system (VERITAS OS)."
regulation_notice: str = "Subject to EU AI Act Regulation (EU) 2024/1689."
```

**[P1-5] モデルカードとバイアス評価レポートの作成**
- `docs/eu_ai_act/model_card_gpt41_mini.md` を新設し、最低限以下を明記する（附属書IV対応）：
  - モデル識別情報（提供者、バージョン、更新日、利用エンドポイント）
  - 意図された用途 / 禁止用途 / 既知の制約（幻覚、非決定性、領域外質問）
  - 安全制御の依存関係（FUJI設定、human_review閾値、fallback条件）
  - 評価プロトコル（評価データ、評価頻度、再現手順、責任者）
- `docs/eu_ai_act/bias_assessment_report.md` を新設し、保護属性別の公平性評価を記録する：
  - 最低評価軸: 性別、年齢層、言語、地域（適用可能な範囲で民族・障害を追加）
  - 指標: 誤拒否率 / 誤受理率 / しきい値近傍の判定安定性
  - 判定基準: 群間差分の許容幅を事前定義し、逸脱時の是正計画を必須化
- 第三者モデル利用に関する法務・契約証跡を `docs/eu_ai_act/third_party_model_dpa_checklist.md` に集約する：
  - DPA締結状況、データ越境移転、サブプロセッサ一覧、保存期間、削除要件
  - OpenAI公開資料への参照（モデルカード / セキュリティ文書）の更新監視担当者
- 運用ゲート（リリースブロッカー）を定義する：
  - モデルカード未更新（最終更新から90日超）
  - バイアス評価未実施（四半期評価なし）
  - DPA証跡未確認（契約ステータス不明）
  - 上記のいずれか該当時は高リスク用途へのデプロイを禁止
- **セキュリティ警告**: モデルカード・バイアス評価・DPA証跡が欠落した状態で本番利用すると、規制違反に加えて説明責任不能・差別的出力見逃し・越境データ処理不備のリスクが顕在化する。

**[P1-6] セキュリティ即時是正（最優先）**
- human_review判定時に「自動実行停止」を強制するフェイルクローズ制御を追加
- bench_modeでのPII保護無効化を禁止（または合成データ限定を強制）
- TrustLogおよびMemory保存データの暗号化を既定ONへ変更
- 監査不備がある環境（ログ保存期間不足・通知フロー未整備）では高リスク用途を明示的に拒否

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

| 期間 | 到達目標 | 完了条件（DoD） |
|------|----------|-----------------|
| 0-30日 | P1項目の設計確定と実装着手 | Art.50開示フィールド追加、human_reviewキュー設計、法務レビュー体制の責任者割当 |
| 31-60日 | P1実装完了 + P2文書化開始 | 人間レビュー実運用、モデルカード初版、附属書IVテンプレート公開 |
| 61-90日 | P2主要項目を運用に接続 | 精度ベンチ結果の定期更新、残留リスク台帳、ユーザー向け説明書の配布開始 |

### KPI（運用監査向け）

- `human_review_required`案件の**100%が人間承認済み**になるまで自動実行しない。
- AI開示ラベル（Art.50）を**ユーザー向け出力の100%**に付与。
- 監査ログ欠損率を**0%**に維持。
- 高リスク用途の判定漏れ（事後検知）を四半期ごとに低減。

---

## 8. 付録：コード参照インデックス

| 条文 | ファイル | 行 | 説明 |
|------|---------|-----|------|
| Art.5 | `core/eu_ai_act_compliance_module.py` | 50-56 | 禁止慣行パターン定義 |
| Art.5 | `core/eu_ai_act_compliance_module.py` | 81-102 | `EUAIActSafetyGateLayer4` |
| Art.5 | `policies/fuji_default.yaml` | 100-131 | ハードブロックキーワード |
| Art.9 | `core/eu_ai_act_compliance_module.py` | 105-124 | `classify_annex_iii_risk()` |
| Art.9 | `core/eu_ai_act_compliance_module.py` | 35-48 | `ANNEX_III_RISK_KEYWORDS` |
| Art.9 | `policies/fuji_default.yaml` | 23-46 | リスクしきい値設定 |
| Art.9 | `core/fuji.py` | (全体) | FUJIゲートリスクスコアリング |
| Art.11/12 | `core/eu_ai_act_compliance_module.py` | 127-157 | `build_tamper_evident_trustlog_package()` |
| Art.11/12 | `logging/trust_log.py` | (全体) | SHA-256ハッシュチェーン |
| Art.11/12 | `audit/trustlog_signed.py` | (全体) | Ed25519署名 |
| Art.13 | `api/schemas.py` | (全体) | `DecideResponse`構造 |
| Art.14 | `core/eu_ai_act_compliance_module.py` | 160-176 | `apply_human_oversight_hook()` |
| Art.14 | `core/eu_ai_act_compliance_module.py` | 58-64 | 基本権役割定義 |
| Art.14 | `core/self_healing.py` | (全体) | 人間レビュー要請追跡 |
| Art.15 | `core/sanitize.py` | (全体) | PIIマスク・DoS対策 |
| Art.15 | `policies/fuji_default.yaml` | 219-237 | プロンプトインジェクション検出 |
| Art.15 | `policies/fuji_default.yaml` | 243-264 | Unicode正規化 |
| Art.15 | `compliance/report_engine.py` | (全体) | コンプライアンスレポート生成 |
| Art.9 (P2-1) | `docs/eu_ai_act/risk_assessment.md` | (全体) | リスク評価・残留リスク台帳 |
| Art.11 (P2-1) | `docs/eu_ai_act/technical_documentation.md` | (全体) | 附属書IV準拠技術文書 |
| Art.13 (P2-1) | `docs/eu_ai_act/intended_purpose.md` | (全体) | 意図された用途と制限 |
| Art.15 (P2-1) | `docs/eu_ai_act/performance_metrics.md` | (全体) | 精度・堅牢性指標 |
| Art.15 (P2-2) | `scripts/doctor.py` | (全体) | 精度モニタリングダッシュボード |
| Art.15 (P2-3) | `core/eu_ai_act_compliance_module.py` | (全体) | `validate_bench_mode_synthetic_data()` |
| Art.15 (P2-3) | `policies/fuji_default.yaml` | 193-201 | bench_mode安全制限設定 |
| Art.13 (P2-4) | `docs/user_guide_eu_ai_act.md` | (全体) | エンドユーザー向け使用説明書 |
| Art.12 (P3-1) | `api/governance.json` | 25-31 | ログ保持期間設定（180日/365日） |
| Art.12 (P3-1) | `core/eu_ai_act_compliance_module.py` | (全体) | `get_retention_config()` |
| Art.12 (P3-2) | `logging/encryption.py` | (全体) | 静止暗号化ユーティリティ |
| Art.12 (P3-2) | `logging/trust_log.py` | (全体) | JSONL書き込み時の暗号化統合 |
| Art.9 (P3-3) | `core/eu_ai_act_compliance_module.py` | (全体) | `RISK_MONITORING_SCHEDULE`, `assess_continuous_risk_monitoring()` |
| Art.9 (P3-3) | `docs/eu_ai_act/continuous_risk_monitoring.md` | (全体) | 継続的リスクモニタリング運用手順書 |
| Art.13 (P3-4) | `core/eu_ai_act_compliance_module.py` | (全体) | `ThirdPartyNotificationService` |
| Art.13 (P3-4) | `api/schemas.py` | (全体) | `affected_parties_notice` フィールド |

---

## まとめ

VERITAS OSはEU AI法準拠を真剣に取り組む姿勢を示しており、特に**第12条（記録保持）**においては業界最高水準の実装（ハッシュチェーン・Ed25519署名・WORM対応）を提供している。

しかし、**5件のCriticalギャップ**（禁止慣行の検出精度・自己分類文書・人間レビューワークフロー・AI開示・データガバナンス）は、本番環境での高リスクAIとしての展開前に必ず解決する必要がある。

法的リスクの観点からは、**現時点ではシステムを高リスクAIとして規制当局へ届け出ることはできない**。推奨された改善アクションの実施後、独立した第三者による適合性評価を受けることを強く推奨する。

---

*本レビューは技術コードレビューに基づく予備的分析であり、法的アドバイスを構成するものではない。EU AI法の最終的な準拠判定は、EU法の資格ある法律専門家によるレビューが必要である。*
