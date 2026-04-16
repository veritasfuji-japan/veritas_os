# 金融向け PoC パック（1日クイックスタート）

## 目的

この PoC パックは、**VERITAS OS を監査/ガバナンス製品として短時間で評価する**ための実行パスです。
営業資料ではなく、リポジトリ内の既存機能だけを使って以下を実証します。

1. **意思決定が fail-closed に統制されること**
2. **判断根拠が UI / API / Evidence Bundle で追跡できること**
3. **再現可能な検証手順で PoC 担当者が1日で触れること**

---

## PoC で何を証明できるか

### 1) Governance correctness（統治の正しさ）
- `gate_decision` と `business_decision` を分離した判断が返る。
- 高リスク・証拠不足・承認境界未定義のケースで自動実行に倒れない。

### 2) Auditability（監査可能性）
- `/v1/decide` 応答でガバナンス関連フィールドを確認できる。
- TrustLog/Evidence Bundle により判断履歴の検証可能性を提示できる。

### 3) Operational reproducibility（運用再現性）
- 同一サンプル質問セットを使って PoC 環境ごとの比較ができる。
- 成功/失敗判定を「期待セマンティクス」と照合して定義できる。

---

## 事前準備（30〜45分）

### 前提
- Docker + Docker Compose
- `.env` に最低限の鍵設定

手順は README の Quick Start を基準にします。
- [README.md](../../../README.md)
- [3-Minute Demo Script](../../en/guides/demo-script.md)

---

## 1日クイックスタート

### Step 1: 起動（60分以内）

```bash
git clone https://github.com/veritasfuji-japan/veritas_os.git
cd veritas_os
cp .env.example .env
# 必須値を設定: OPENAI_API_KEY / VERITAS_API_KEY / VERITAS_API_SECRET
docker compose up --build
```

確認:
- Backend: `http://localhost:8000/docs`
- Frontend (Mission Control): `http://localhost:3000`

### Step 2: PoC サンプル質問を投入（90分）

質問セット:
- `veritas_os/sample_data/governance/financial_poc_questions.json`
- 既存テンプレート: `veritas_os/sample_data/governance/financial_regulatory_templates.json`

役割分担:
- `financial_poc_questions.json`: PoC 実行用の軽量質問セット（期待セマンティクス確認向け）
- `financial_regulatory_templates.json`: 回帰検証用の canonical industry pack（`context` と完全期待値を保持）
- PoC 質問は `template_id` を持てるため、`fixture_contexts` の逆引きなしで canonical template に接続できます。

最低 5 件（推奨 8 件）を `/v1/decide` に投入し、各ケースで期待セマンティクスを照合します。

### Step 3: UI / API / Bundle の3点確認（120分）

#### UI（Mission Control）で見るべき点
- リスク高・証拠不足ケースで `hold` / `human_review_required` / `block` が可視化される。
- 承認境界未定義ケースでレビュー要求が出る。

#### API（/v1/decide）で見るべき点
- `gate_decision`
- `business_decision`
- `next_action`
- `required_evidence`
- `human_review_required`
- `governance_identity`（環境で有効な場合）

#### Bundle（監査成果物）で見るべき点
- 判断イベントに対応する Bundle を生成・検証できる。
- 参照: [External Audit Readiness](../../en/validation/external-audit-readiness.md)
- 参照サンプル: `veritas_os/benchmarks/evidence/fixtures/financial_template_bundle_sample.json`

### Step 4: 成功/失敗判定（60分）

後述の「成功条件」と「失敗時の見方」で判定します。

---

## expected decision semantics（期待セマンティクス）

PoC では以下を**成功ライン**として評価します。

- 証拠不足: `gate_decision=hold` かつ `business_decision=EVIDENCE_REQUIRED`
- 高リスクだが即断不可: `gate_decision=human_review_required` かつ `business_decision=REVIEW_REQUIRED`
- 不可逆・重大リスク: `gate_decision=block` かつ `business_decision=DENY`
- `next_action` が証拠収集/レビュー導線を示す
- `required_evidence` が空でない（統治理由が具体化される）

補足:
- これは「法的結論」ではなく、VERITAS の統治意思決定セマンティクスです。
- 既存の公開スキーマ互換性は `veritas_os/tests/test_financial_regulatory_templates.py` で検証されています。

---

## 成功条件（PoC 合格ライン）

1. **再現性**
   - 同じ質問セットで、同系統のセマンティクスが安定して得られる。
2. **監査可能性**
   - UI / API / Bundle の3系統で同一意思決定を追跡できる。
3. **安全側挙動**
   - 高リスク・証拠不足・権限未定義時に fail-open しない。
4. **説明可能性**
   - `required_evidence` と判断理由が、次の業務アクションに接続できる。

---

## 失敗時の見方（デバッグ観点）

### ケースA: 期待より緩い判定（例: hold 期待で proceed）
- 入力コンテキストに `required_evidence` が不足していないか
- ポリシー設定が PoC 期待と一致しているか
- FUJI / Value Core の評価文脈が意図どおりか

### ケースB: `required_evidence` が弱い / 空
- サンプル質問の曖昧度が高すぎないか
- ケース文脈に必要属性（KYC/制裁/承認境界）が含まれているか

### ケースC: Bundle が追跡しづらい
- TrustLog パスと namespace（dev/test/demo/prod）を確認
- 生成/検証コマンドを [External Audit Readiness](../../en/validation/external-audit-readiness.md) に合わせる

---

## 監査 / ガバナンス製品としての見せ方

PoC レビュー会では、次の順序で示すと伝わりやすいです。

1. **統治境界**: 「モデル出力を即実行しない」設計
2. **判断セマンティクス**: `gate_decision` と `business_decision` の分離
3. **監査証跡**: TrustLog / Bundle / 検証手順
4. **運用実装性**: 1日で再現できる実行手順と成功判定

関連ドキュメント:
- [PostgreSQL Production Guide](../../en/operations/postgresql-production-guide.md)
- [Production Validation Strategy](../../en/validation/production-validation.md)
- [Governance Artifact Lifecycle](../../en/governance/governance-artifact-lifecycle.md)
- [Financial Governance Templates](../../en/guides/financial-governance-templates.md)

---

## セキュリティ警告（PoC 実施時）

- **実データ禁止**: 顧客情報・口座番号・実在個人データは投入しない。
- **鍵管理**: `.env` の API secret/鍵は共有しない。PoC 用にローテーション前提の値を使う。
- **外部連携**: 本番の承認系/送金系への接続は PoC で行わない（read-only 参照に限定）。
