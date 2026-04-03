# Policy-as-Code 実装状況レビュー（2026-04-02）

## 対象範囲

本レビューは、VERITAS OS における **Policy-as-Code** の全実装を対象とする包括的コードレビューである。
以下の観点からソースコードを精読し、実装の現状・設計品質・セキュリティ・テスト網羅性・運用準備状況を評価した。

| 観点 | 対象ファイル群 |
|------|---------------|
| ポリシーコア | `veritas_os/policy/*`（14ファイル, 1,249行） |
| パイプライン統合 | `veritas_os/core/pipeline/pipeline_policy.py`（301行） |
| ガバナンスAPI | `veritas_os/api/routes_governance.py`（217行）, `veritas_os/api/governance.py`（473行） |
| テスト基盤 | テストファイル6件（1,765行, 119テスト関数） |
| ポリシー定義例 | `policies/examples/*.yaml`（5ファイル, 178行） |
| フロントエンド | `frontend/app/governance/`, `packages/types/src/governance.ts` |
| CLI | `veritas_os/scripts/compile_policy.py`（52行） |

**レビュー対象コード総量: 約4,165行（テスト含む）**

---

## 1. 結論サマリ

### 1.1 総合評価

| 項目 | 評価 | 備考 |
|------|------|------|
| **成熟度** | **Late Beta（GA直前）** | コンパイル〜ランタイム評価の縦断経路が成立 |
| **設計品質** | ◎ | 関心の分離が明確、拡張性が高い |
| **テスト網羅性** | ○ | 主要パスはカバー、境界テスト追加余地あり |
| **セキュリティ** | ○（条件付き） | ReDoSガードレール済、署名は将来課題 |
| **運用準備** | ○ | `VERITAS_POLICY_RUNTIME_ENFORCE` env var による enforcement デフォルト設定対応、監視/アラート統合は部分的 |

### 1.2 実装ステータス一覧

- **✅ 実装済み（中核機能）**
  - YAML/JSON ポリシーの strict schema 検証（Pydantic）
  - Canonical IR への決定論的正規化
  - SHA-256 semantic hash による content-addressable 管理
  - コンパイラ（source → bundle artifacts）
  - ランタイムアダプタ（bundle load + manifest 署名検証）
  - ポリシー評価エンジン（scope / conditions / constraints / requirements）
  - 5段階 outcome 判定（allow / require_human_review / escalate / halt / deny）
  - パイプライン統合（opt-in enforcement bridge）
  - テストベクトル自動生成（policy YAML → pytest parametrize）
  - ガバナンスAPI（RBAC/ABAC + 4-eyes承認）
  - ポリシー変更履歴（JSONL監査証跡）
  - フロントエンドUI（ガバナンスコントロールプレーン）

- **✅ 実装済み（品質担保）**
  - コンパイラ成果物・決定性・改ざん検知のテスト
  - ランタイム判定の全 outcome パターンテスト
  - ReDoS ガードレール（パターン長/入力長/ネスト量指定子検出）
  - manifest.sig 改ざん検出テスト
  - 94件のガバナンスAPI統合テスト

- **⚠️ 未実装 / 制約あり**
  - 公開鍵暗号署名（現在は SHA-256 ハッシュ整合のみ）
  - enforcement のデフォルト強制（現在は opt-in）
  - Transparency Log / Trust Log 連携
  - ポリシーパック rollout/rollback メタデータ
  - 段階的 enforcement（canary → staged → full）の自動化

---

## 2. アーキテクチャ全体像

### 2.1 Policy-as-Code パイプライン

```
┌─────────────────────────────────────────────────────────────────┐
│                    Policy Authoring Layer                        │
│  policies/examples/*.yaml   (Human-authored, version-controlled) │
└─────────────────────┬───────────────────────────────────────────┘
                      │ schema.py: load_and_validate_policy()
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Validation Layer                               │
│  models.py: SourcePolicy (Pydantic strict validation)            │
│  ├─ PolicyScope (domains, routes, actors)                        │
│  ├─ Expression (field, operator, value)                          │
│  ├─ PolicyRequirements (evidence, reviewers, approvals)          │
│  └─ PolicyOutcome (decision, reason)                             │
└─────────────────────┬───────────────────────────────────────────┘
                      │ normalize.py: to_canonical_ir()
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Canonicalization Layer                         │
│  ir.py: CanonicalPolicyIR (TypedDict, deterministic contract)    │
│  normalize.py: 正規化（ソート、重複排除、キー順序固定）            │
│  hash.py: semantic_policy_hash() → SHA-256 hex                   │
└─────────────────────┬───────────────────────────────────────────┘
                      │ compiler.py: compile_policy_to_bundle()
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Compilation Layer                              │
│  Bundle Directory:                                               │
│  ├── compiled/canonical_ir.json  (凍結済みソースオブトゥルース)     │
│  ├── compiled/explain.json       (UI/監査向け説明メタデータ)       │
│  ├── signatures/UNSIGNED         (将来の署名拡張プレースホルダ)    │
│  ├── manifest.json               (完全性メタデータ)               │
│  ├── manifest.sig                (SHA-256 整合性検証)             │
│  └── bundle.tar.gz              (配布用アーカイブ)                │
└─────────────────────┬───────────────────────────────────────────┘
                      │ runtime_adapter.py: load_runtime_bundle()
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Runtime Evaluation Layer                       │
│  evaluator.py: evaluate_runtime_policies()                       │
│  ├─ Scope matching (domain/route/actor)                          │
│  ├─ Condition evaluation (10 operators)                          │
│  ├─ Constraint evaluation                                        │
│  ├─ Requirement verification (evidence + approvals)              │
│  ├─ Outcome precedence resolution                                │
│  └─ PolicyEvaluationResult (structured decision payload)         │
└─────────────────────┬───────────────────────────────────────────┘
                      │ pipeline_policy.py: _apply_compiled_policy_runtime_bridge()
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Pipeline Integration Layer                     │
│  FUJI precheck → compiled policy bridge → gate decision          │
│  ├─ ctx.response_extras["governance"]["compiled_policy"] に格納   │
│  └─ policy_runtime_enforce=true 時のみ FUJI status 反映          │
│      deny/halt → rejected | escalate/require_human_review → modify│
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 ガバナンスAPI層

```
┌─────────────────────────────────────────────────────────────┐
│              Governance REST API                             │
│  routes_governance.py (RBAC/ABAC保護)                        │
│  ├─ GET  /v1/governance/policy          (現行ポリシー取得)    │
│  ├─ PUT  /v1/governance/policy          (4-eyes承認付き更新)  │
│  ├─ GET  /v1/governance/policy/history  (変更監査証跡)        │
│  ├─ GET  /v1/governance/value-drift     (ValueCore EMAドリフト)│
│  └─ GET  /v1/governance/decisions/export(判定エクスポート)     │
│                                                              │
│  governance.py (永続化・検証・コールバック管理)                 │
│  ├─ GovernancePolicy (Pydantic: 7セクション)                  │
│  ├─ enforce_four_eyes_approval()                             │
│  ├─ update_policy() (atomic write + 監査証跡)                │
│  └─ コールバックによるホットリロード                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. モジュール別詳細レビュー

### 3.1 ポリシースキーマ定義（`models.py` — 219行）

**設計評価: ◎**

Pydantic `BaseModel` による厳密なスキーマ定義。全モデルが `frozen=True`（イミュータブル）かつ `extra="forbid"`（未知フィールド禁止）で構成されており、入力の曖昧さを排除している。

**主要クラス構造:**

| クラス | 目的 | フィールド数 |
|--------|------|-------------|
| `OutcomeAction(str, Enum)` | 判定アクション列挙 | 5値（allow/deny/halt/escalate/require_human_review） |
| `Expression(BaseModel)` | 条件/制約式 | 3（field, operator, value） |
| `PolicyScope(BaseModel)` | 適用範囲セレクタ | 3（domains, routes, actors） |
| `PolicyRequirements(BaseModel)` | 承認/エビデンス要件 | 3（evidence, reviewers, approval_count） |
| `PolicyOutcome(BaseModel)` | 判定結果 | 2（decision, reason） |
| `PolicyExample(BaseModel)` | テストベクトル | 3（name, input, expected_outcome） |
| `SourcePolicy(BaseModel)` | ルートスキーマ | 14（全フィールド） |

**バリデーション品質:**
- `schema_version` の固定値チェック（`"1.0"` のみ許可）
- `effective_date` の ISO 8601 形式検証
- `minimum_approval_count ≤ len(required_reviewers)` の整合性チェック
- フィールド長制限（policy_id: 3-120文字、reason: 最大2,000文字等）
- `title` / `description` の自動 strip 正規化

**所見:**
- スキーマ設計は堅牢であり、ポリシー著者のミスを早期に検出できる。
- `operator` フィールドが `Literal` 型で 10 演算子に限定されており、injection リスクが低い。
- `metadata` フィールドは `Dict[str, Any]` で型が緩いが、監査補助情報として許容範囲内。

---

### 3.2 正規化（`normalize.py` — 94行, `ir.py` — 33行）

**設計評価: ◎**

CanonicalPolicyIR（`TypedDict`）を正規化の不変契約として定義し、`to_canonical_ir()` が以下の決定論的変換を実施する。

- リスト項目のソート（`domains`, `routes`, `actors`, `obligations`, `source_refs`）
- 重複排除（`_dedupe_sorted`）
- 式リストのソート（`field, operator, JSON(value)` の3要素タプルでソート）
- テストベクトルのソート（`name, JSON(input), expected_outcome`）
- 辞書キーの再帰的ソート
- 文字列の strip 処理

**所見:**
- `_normalize_json_value` が再帰的に値を正規化しており、ネストした構造でも決定論を保証。
- IR が `TypedDict` であるため、JSON serializability が型レベルで保証されている。
- 正規化の決定論は `test_policy_canonical_ir.py` で検証済み（同一セマンティクスの異順序入力 → 同一 IR）。

---

### 3.3 セマンティックハッシュ（`hash.py` — 24行）

**設計評価: ○**

`canonical_ir_json()` が `sort_keys=True`, `separators=(",", ":")` で安定シリアライズし、`semantic_policy_hash()` が SHA-256 hex digest を返す。

**所見:**
- `compiled_at` などのメタ情報は IR に含まれないため、同一ポリシーは常に同一ハッシュを生成する。
- これにより content-addressable な管理が可能（同一ハッシュ = 同一ポリシー内容）。
- ハッシュアルゴリズムが SHA-256 固定であり、将来の移行時にバージョニングが必要になる可能性がある。

---

### 3.4 コンパイラ（`compiler.py` — 97行）

**設計評価: ◎**

`compile_policy_to_bundle()` が一貫したパイプラインで以下を実施:

```
load_and_validate → to_canonical_ir → semantic_hash
→ write canonical_ir.json → build_explanation → write explain.json
→ create UNSIGNED marker → collect_bundle_files
→ build_manifest → write manifest.json → sign manifest
→ create bundle.tar.gz → return CompileResult
```

**出力ディレクトリ構造:**
```
{output_dir}/{policy_id}/{version}/bundle/
├── compiled/
│   ├── canonical_ir.json    ← 凍結済みソースオブトゥルース
│   └── explain.json         ← UI/監査向け説明メタデータ
├── signatures/
│   └── UNSIGNED             ← 将来署名のプレースホルダ
├── manifest.json            ← 完全性メタデータ + バンドル内容
└── manifest.sig             ← SHA-256(manifest.json) hex
+ bundle.tar.gz              ← 配布用アーカイブ
```

**所見:**
- `CompileResult` が `frozen=True` で出力も immutable。
- `_utc_now_iso8601()` を外部注入可能（`--compiled-at`）にすることで再現可能ビルドを実現。
- ✅ ~~エラーハンドリングは `PolicyValidationError` のみで、ファイル I/O エラーは伝播する設計。~~ → `PolicyCompilationError`（`RuntimeError` 派生）でファイル I/O エラーをラップ。API 連携時にも構造化されたエラー応答が可能。

---

### 3.5 マニフェスト（`manifest.py` — 46行）

**設計評価: ○**

`build_manifest()` が以下の構造を生成:

```json
{
  "schema_version": "0.1",
  "policy_id": "...",
  "version": "...",
  "semantic_hash": "sha256:...",
  "compiler_version": "0.1.0",
  "compiled_at": "ISO8601Z",
  "effective_date": "...",
  "source_files": ["..."],
  "source_refs": ["..."],
  "outcome_summary": {
    "decision": "...",
    "reason": "...",
    "obligation_count": 3,
    "condition_count": 1,
    "constraint_count": 1
  },
  "bundle_contents": [
    {"path": "compiled/canonical_ir.json", "sha256": "...", "size": 1234}
  ],
  "signing": {
    "status": "signed-local",
    "signature_ref": "manifest.sig",
    "key_id": "local-sha256",
    "extensions": {}
  }
}
```

**所見:**
- `signing` セクションが将来の拡張点を明確に定義しており、前方互換性を確保。
- `bundle_contents` に各ファイルの SHA-256 + サイズを記録することで、個別ファイルの完全性検証が可能。

---

### 3.6 バンドル生成（`bundle.py` — 44行, `emit.py` — 23行, `explain.py` — 52行）

**設計評価: ○**

- `bundle.py`: tar.gz アーカイブをソート済みファイル順で生成（決定論的）。
- `emit.py`: `sort_keys=True`, `ensure_ascii=False`, `indent=2` による安定 JSON 出力。
- `explain.py`: UI/監査向けの説明メタデータ生成。スコープ・条件数・outcome の要約を human-readable な文字列で提供。

**所見:**
- `explain.json` の `human_summary` フィールドが自然言語で application scope と outcome を要約しており、非技術者にも理解しやすい設計。
- `emit.py` が `ensure_ascii=False` を使用しているため、日本語等の非ASCII文字をそのまま出力可能。

---

### 3.7 ランタイムアダプタ（`runtime_adapter.py` — 131行）

**設計評価: ◎**

コンパイル成果物をランタイム評価可能な形式に変換するアダプタパターンを実装。

**主要関数:**

| 関数 | 入力 | 出力 | 目的 |
|------|------|------|------|
| `load_runtime_bundle(bundle_dir)` | ファイルシステムパス | `RuntimePolicyBundle` | バンドル読み込み + 署名検証 |
| `adapt_compiled_payload(ir, manifest)` | in-memory dict | `RuntimePolicyBundle` | API/パイプライン用 bridge |
| `verify_manifest_signature(bundle_dir)` | ファイルシステムパス | `bool` | manifest.sig 検証 |

**セキュリティフロー:**
1. `manifest.sig` を読み込み、`manifest.json` の SHA-256 と比較
2. 不一致の場合は `ValueError` を送出してロードを拒否
3. 一致後に `canonical_ir.json` を読み込み、`RuntimePolicy` に変換
4. `RuntimePolicyBundle` （`frozen=True`）として返却

**所見:**
- 署名検証がロード前に必ず実行される設計は良い。
- ただし、SHA-256 整合チェックは「改ざん検知」であり「真正性保証」ではない点に注意（後述のセキュリティ項目参照）。
- `_read_json_file()` がファイル読み込み後に型チェック（`isinstance(data, dict)`）を行っており、不正な JSON 構造を弾く。

---

### 3.8 ポリシー評価エンジン（`evaluator.py` — 322行）

**設計評価: ◎（本レビューの核心）**

ランタイムポリシー評価の中核モジュール。コンパイル済みポリシーバンドルとコンテキスト辞書を受け取り、構造化された判定結果を返す。

**評価フロー:**

```
各ポリシーに対して:
  0. _is_effective(policy)              ← effective_date が今日以前かチェック（将来日付はスキップ）
  1. scope_matches(policy, context)    ← domain/route/actor の一致判定
  2. conditions 全一致チェック          ← 「いつ発火するか」
  3. constraints 全一致チェック         ← 「追加ガード条件」
  4. requirements 評価                  ← エビデンス + 承認要件
  5. outcome 判定                       ← 条件一致時の判定結果
  6. precedence resolution              ← 最高優先度の outcome を選択
```

**サポートする演算子（10種）:**

| 演算子 | 動作 | 型ガード |
|--------|------|---------|
| `eq` / `neq` | 等値/非等値 | any |
| `in` / `not_in` | リスト包含/非包含 | list/set チェック |
| `gt` / `gte` / `lt` / `lte` | 数値比較 | float 変換ガード |
| `contains` | 文字列/リスト包含 | 型チェック |
| `regex` | 正規表現マッチ | ReDoS ガードレール付き |

**Outcome 優先度（deny が最高）:**

```
allow (0) < require_human_review (1) < escalate (2) < halt (3) < deny (4)
```

**Fail-safe 昇格ロジック:**
- `allow` outcome でもエビデンス不足 → `halt` に昇格
- `allow` outcome でも承認不足 → `require_human_review` に昇格

**ReDoS ガードレール:**
- パターン長上限: 256 文字（一般的なポリシー条件は50文字以下であり、悪意あるパターン構築を制限しつつ実用的な正規表現を許容）
- 検査対象文字列長上限: 1,024 文字（コンテキストフィールドの実用上限。URL/パス/分類ラベル等は通常100文字以下）
- ネスト量指定子（`(a+)+` 等）のガード: `_REGEX_NESTED_QUANTIFIER_GUARD` で検出・拒否
- `re.error` のキャッチ: コンパイルエラー時は安全に `False` を返却

**出力構造（`PolicyEvaluationResult`）:**

```python
@dataclass(frozen=True)
class PolicyEvaluationResult:
    applicable_policies: list[str]       # スコープ一致ポリシー
    triggered_policies: list[str]        # 条件一致ポリシー
    final_outcome: str                   # 最終判定
    reasons: list[str]                   # 判定理由
    required_actions: list[str]          # 必要アクション
    obligations: list[str]              # 義務（副作用）
    approval_requirements: list[dict]    # 承認要件詳細
    evidence_gaps: list[dict]            # エビデンス不足詳細
    explanations: list[dict]             # 説明メタデータ
    policy_results: list[dict]           # 個別ポリシー結果
```

**所見:**
- 評価ロジックの分離が適切で、各関数が単一責務を担っている。
- fail-safe 昇格（allow → halt/require_human_review）は安全側に倒す設計として評価できる。
- `_read_path()` がドット記法のパス探索を行い、ネストされたコンテキストにもアクセス可能。
- `_listify()` が型変換のロバスト性を提供。

---

### 3.9 パイプライン統合（`pipeline_policy.py` — 301行）

**設計評価: ○**

FUJI precheck / ValueCore / Gate Decision の3ステージに加え、compiled policy bridge を提供。

**ステージ構成:**

| ステージ | 関数 | 目的 |
|----------|------|------|
| FUJI precheck | `stage_fuji_precheck()` | FUJI safety 検証 + compiled policy 評価 |
| Value Core | `stage_value_core()` | ValueCore 評価 + EMA 学習 + リスク/telos 調整 |
| Gate Decision | `stage_gate_decision()` | 最終ゲート判定（allow/modify/rejected） |

**Compiled Policy Bridge（`_apply_compiled_policy_runtime_bridge`）:**

```python
def _apply_compiled_policy_runtime_bridge(ctx):
    bundle_dir = ctx.context.get("compiled_policy_bundle_dir")
    if not bundle_dir:
        return  # バンドル未指定時はスキップ

    runtime_bundle = load_runtime_bundle(bundle_dir)
    decision = evaluate_runtime_policies(runtime_bundle, ctx.context)

    # 結果を governance extras に格納（常時）
    ctx.response_extras["governance"]["compiled_policy"] = decision.to_dict()

    # enforcement（opt-in 時のみ）
    if ctx.context.get("policy_runtime_enforce", False):
        if outcome in {"deny", "halt"}:
            ctx.fuji_dict["status"] = "rejected"
        elif outcome in {"escalate", "require_human_review"}:
            ctx.fuji_dict["status"] = "modify"
    else:
        # 非強制時は warning ログで未反映を明示
        ...
```

**所見:**
- 既存の FUJI/ValueCore ロジックを変更せず、「接続点のみ」を追加した最小侵襲設計。
- `try/except` による fail-safe が各ステージに実装されており、policy 評価エラーがリクエスト処理をクラッシュさせない。
- 非強制モード時の warning ログにより、設定ミスの検出性を向上。

---

### 3.10 ガバナンスAPI（`routes_governance.py` — 217行, `governance.py` — 473行）

**設計評価: ○**

ファイルベースのガバナンスポリシー管理 + REST API。

**API エンドポイント:**

| パス | メソッド | 認可 | 目的 |
|------|---------|------|------|
| `/v1/governance/policy` | GET | `governance_read` | 現行ポリシー取得 |
| `/v1/governance/policy` | PUT | `governance_write` | ポリシー更新（4-eyes 必須） |
| `/v1/governance/policy/history` | GET | `governance_read` | 変更履歴取得（最大500件） |
| `/v1/governance/value-drift` | GET | `governance_read` | ValueCore EMA ドリフト指標 |
| `/v1/governance/decisions/export` | GET | `governance_read` | 判定エクスポート |

**RBAC/ABAC 制御:**
- ロール: `admin`, `compliance_owner`（`VERITAS_GOVERNANCE_ALLOWED_ROLES` で設定）
- テナントスコープ: `X-Tenant-Id` ヘッダ（`VERITAS_GOVERNANCE_TENANT_ID` で設定）
- 4-Eyes 承認: 2名の異なるレビュアー + 2つの異なる署名が必須

**ガバナンスポリシー構造（7セクション）:**

| セクション | 主要設定 |
|------------|---------|
| `fuji_rules` | PII検出、自傷行為ブロック等の8トグル |
| `risk_thresholds` | allow/warn/human_review/deny の4段階閾値 |
| `auto_stop` | 自動停止（リスクスコア上限、連続拒否上限、レート制限） |
| `log_retention` | 保持日数、監査レベル（6段階）、フィールド制御 |
| `rollout_controls` | ロールアウト戦略（disabled/canary/staged/full） |
| `approval_workflow` | ヒューマンレビュー設定、承認者バインディング |
| メタデータ | `version`, `updated_at`, `updated_by` |

**セキュリティ対策:**
- `updated_by` フィールドの XSS 対策（HTMLタグ除去、制御文字除去、200文字制限）
- アトミックライト（crash-safe なファイル更新）
- ガバナンス変更アラート（`fuji_rules`/`risk_thresholds`/`auto_stop` 変更時に severity: high イベント発行）
- ホットリロードコールバック（ポリシー更新時に FUJI/ValueCore のキャッシュ更新）

**所見:**
- ファイルベース永続化は小規模運用に適しているが、マルチインスタンス環境ではロック競合の可能性あり。
- 4-Eyes 承認のバリデーションが厳密（空文字チェック、重複チェック、型チェック）。
- `governance_history.jsonl` の上限が500件で、長期運用には外部ログ連携が必要。

---

### 3.11 テストベクトル自動生成（`generated_tests.py` — 90行）

**設計評価: ◎**

ポリシー YAML の `test_vectors` フィールドから pytest テストケースを決定論的に生成する仕組み。

**フロー:**
1. `policies/examples/*.yaml` を走査
2. 各ポリシーの `test_vectors` を抽出
3. ベースコンテキスト（scope の先頭値 + requirements を満たす入力）を自動生成
4. テストベクトルの `input` をベースに deep merge
5. `GeneratedPolicyTestCase` として返却
6. `(policy_id, vector_name, file)` でソート（決定論的順序）

**所見:**
- ポリシー定義に期待動作を埋め込むことで、「ポリシーが自らの正しさを宣言する」パターンを実現。
- ベースコンテキストの自動生成により、テストベクトルは差分情報のみ記述すれば済む。
- 決定論的ソートにより、テスト実行順序が安定。

---

### 3.12 CLI（`compile_policy.py` — 52行）

**設計評価: ○**

```bash
python -m veritas_os.scripts.compile_policy \
  policies/examples/high_risk_route_requires_human_review.yaml \
  --output-dir artifacts/policy_compiler \
  --compiled-at 2026-03-28T00:00:00Z
```

**所見:**
- exit code が明確（0: 成功、2: バリデーションエラー）。
- `--compiled-at` による再現可能ビルドサポート。
- 出力が `bundle_dir`, `manifest`, `archive`, `semantic_hash` の4値で、CI/CD パイプライン統合に適している。

---

## 4. テスト基盤レビュー

### 4.1 テストカバレッジサマリ

| テストファイル | テスト数 | 行数 | 主要カバレッジ |
|---------------|---------|------|---------------|
| `test_policy_compiler.py` | 8 | 155 | コンパイル成功/失敗、成果物構造、決定性、署名、I/Oエラーラッピング |
| `test_policy_runtime_adapter.py` | 10 | 440 | ランタイム評価（全5 outcome）、ReDoS ガード、複数ポリシー優先度解決、effective_date フィルタリング |
| `test_policy_canonical_ir.py` | 8 | 197 | スキーマ検証（全5例）、正規化決定性、ハッシュ安定性 |
| `test_policy_generated_vectors.py` | 2 | 37 | テストベクトル自動生成（5ポリシー）、決定論性 |
| `test_warning_allowlist_policy.py` | 3 | 116 | 警告許可リスト検証 |
| `test_governance_api.py`（統合） | 94 | 997 | API全エンドポイント、RBAC、4-eyes、履歴 |
| `test_pipeline_stages_ext.py`（bridge） | 7 | — | パイプライン bridge enforcement（全4 outcome→status マッピング + 非強制時 warning + env var フォールバック） |
| **合計** | **132** | **1,942+** | |

### 4.2 テストパターン分析

**良好なパターン:**
- `@pytest.mark.parametrize` による全ポリシー例のパラメトリックテスト
- `tmp_path` fixture による隔離されたファイルシステムテスト
- `monkeypatch` による環境変数の安全な差し替え
- `_approved()` ヘルパーによる 4-eyes ペイロードの再利用
- manifest 改ざん検出テスト（セキュリティ境界テスト）
- ReDoS パターン拒否テスト（入力長超過、ネスト量指定子）

**テスト網羅性の評価:**

| 観点 | カバー状況 | 備考 |
|------|-----------|------|
| コンパイル成功 | ✅ | 全5例でテスト済み |
| コンパイル失敗 | ✅ | 不正スキーマ、不正enum |
| 成果物構造 | ✅ | パス、SHA-256、サイズ |
| 決定性 | ✅ | 同一入力→同一出力 |
| 署名検証成功 | ✅ | ロード時の自動検証 |
| 署名改ざん検出 | ✅ | 改ざん後のロード拒否 |
| outcome: allow | ✅ | in-memory ペイロード + YAML ポリシー例 |
| outcome: deny | ✅ | 外部ツール拒否 |
| outcome: halt | ✅ | エビデンス不足 |
| outcome: escalate | ✅ | in-memory ペイロード + YAML ポリシー例 |
| outcome: require_human_review | ✅ | 高リスクルート |
| エビデンスギャップ | ✅ | 不足検出 + 詳細 |
| 承認不足 | ✅ | 不足検出 + 詳細 |
| ReDoS ガード | ✅ | 3パターン（正常/長入力/ネスト量指定子） |
| API GET/PUT | ✅ | 全エンドポイント |
| RBAC 拒否 | ✅ | ロール不足 |
| ABAC 拒否 | ✅ | テナント不一致 |
| 4-eyes 検証 | ✅ | 正常/不正/重複/不足 |
| 監査履歴 | ✅ | 追記/トリム/読み取り |
| XSS 防御 | ✅ | HTMLタグ除去テスト |
| effective_date フィルタリング | ✅ | 将来日付スキップ + 過去日付発火 |
| コンパイラ I/O エラーラッピング | ✅ | OSError → PolicyCompilationError |
| パイプライン bridge enforcement (deny→rejected) | ✅ | deny outcome で fuji status が rejected に |
| パイプライン bridge enforcement (halt→rejected) | ✅ | halt outcome で fuji status が rejected に |
| パイプライン bridge enforcement (escalate→modify) | ✅ | escalate outcome で fuji status が modify に |
| パイプライン bridge enforcement (require_human_review→modify) | ✅ | require_human_review outcome で fuji status が modify に |
| env var enforcement フォールバック | ✅ | `VERITAS_POLICY_RUNTIME_ENFORCE` env var による制御 |

**改善余地:**
- ✅ ~~複数ポリシーの同時評価（優先度解決）の明示的テストが追加できる。~~ → `test_multiple_policy_precedence_resolution` で対応済み
- ✅ ~~`effective_date` が将来日付のポリシーの挙動テスト~~ → `effective_date` フィルタリングを evaluator に実装し、テスト2件追加済み
- ✅ ~~パイプライン bridge の enforcement 有効時の e2e テスト。~~ → 全4 outcome（deny→rejected, halt→rejected, escalate→modify, require_human_review→modify）の enforcement テスト + env var フォールバックテストを追加済み

---

## 5. ポリシー定義例レビュー

### 5.1 例1: 高リスクルートの人間レビュー

**ファイル:** `high_risk_route_requires_human_review.yaml`

| 項目 | 値 |
|------|-----|
| policy_id | `policy.high_risk_route.human_review` |
| scope | governance/decisioning, /api/decide, planner/kernel |
| condition | `risk.level in [high, critical]` |
| constraint | `runtime.auto_execute == false` |
| requirements | エビデンス2件 + レビュアー2名 + 全員承認 |
| outcome | `require_human_review` |
| obligations | trust_log記録, レビューチケット添付, ガバナンスチャネル通知 |

### 5.2 例2: 外部ツール使用拒否

**ファイル:** `external_tool_usage_denied.yaml`

| 項目 | 値 |
|------|-----|
| policy_id | `policy.external_tool_usage.denied` |
| scope | tooling/security, /api/tools, kernel/tool_adapter |
| conditions | `tool.external == true` AND `data.classification in [restricted, secret]` |
| constraint | `tool.name not_in [internal_search, approved_registry]` |
| requirements | エビデンス1件 + レビュアー1名 |
| outcome | `deny` |
| obligations | セキュリティアラート発行, 拒否理由記録 |

### 5.3 例3: 必須エビデンス不足による停止

**ファイル:** `missing_mandatory_evidence_halt.yaml`

| 項目 | 値 |
|------|-----|
| policy_id | `policy.mandatory_evidence.halt` |
| scope | governance/audit, /api/decide, planner/kernel/fuji |
| condition | `decision.criticality in [high, critical]` |
| constraint | `evidence.missing_count > 0` |
| requirements | エビデンス3件 + レビュアー2名 |
| outcome | `halt` |
| obligations | エビデンスギャップインシデント開設, 停止イベント記録 |

### 5.4 例4: 低リスクルートの自動実行許可

**ファイル:** `low_risk_route_allow.yaml`

| 項目 | 値 |
|------|-----|
| policy_id | `policy.low_risk_route.allow` |
| scope | governance/decisioning, /api/decide, planner/kernel |
| condition | `risk.level in [low, minimal]` |
| constraint | `runtime.auto_execute == true` |
| requirements | エビデンス1件 + レビュアー1名 + 1名承認 |
| outcome | `allow` |
| obligations | trust_log記録 |

### 5.5 例5: 異常検知時のエスカレーション

**ファイル:** `anomaly_detection_escalate.yaml`

| 項目 | 値 |
|------|-----|
| policy_id | `policy.anomaly_detection.escalate` |
| scope | governance/monitoring, /api/decide, planner/kernel |
| condition | `anomaly.detected == true` |
| constraint | `risk.level in [medium, high]` |
| requirements | エビデンス1件 + レビュアー1名 + 1名承認 |
| outcome | `escalate` |
| obligations | ガバナンスチャネル通知, エスカレーションイベント記録 |

**所見:**
- 3つの例が `deny`, `halt`, `require_human_review` の異なる outcome をカバーしており、テンプレートとして適切。
- 各例にテストベクトルが1件ずつ埋め込まれており、自動テスト生成の入力として機能する。
- ✅ `allow` と `escalate` のポリシー例を追加済み（`low_risk_route_allow.yaml`, `anomaly_detection_escalate.yaml`）。全5 outcome カバー完了。

---

## 6. セキュリティレビュー

### 6.1 実装済みセキュリティ対策

| 対策 | 実装箇所 | 評価 |
|------|---------|------|
| ReDoS ガードレール | `evaluator.py` | ◎ パターン長256/入力長1024/ネスト量指定子検出 |
| Manifest 完全性検証 | `runtime_adapter.py` | ○ SHA-256 整合チェック |
| XSS 防止（updated_by） | `governance.py` | ◎ HTMLタグ除去 + 制御文字除去 + 長さ制限 |
| RBAC/ABAC | `routes_governance.py` | ◎ ロール + テナントスコープ |
| 4-Eyes 承認 | `governance.py` | ◎ 2名異なるレビュアー + 署名 |
| Atomic Write | `governance.py` | ○ crash-safe ファイル更新 |
| スキーマ厳密性 | `models.py` | ◎ extra=forbid, frozen, バリデータ |
| Fail-closed | `pipeline_policy.py` | ○ エラー時は安全側にデフォルト |
| イミュータブル設計 | 全 dataclass | ◎ frozen=True で変更不可 |

### 6.2 セキュリティ警告

> 🔴 **重大警告: 署名モデルが「ハッシュ整合」に留まる（本番デプロイ前に対応必須）**
>
> `manifest.sig` は `manifest.json` の SHA-256 hex 値であり、秘密鍵による電子署名ではない。
> 攻撃者がバンドル一式にアクセスできる場合、`manifest.json` と `manifest.sig` を同時に再生成可能。
> **信頼境界を跨ぐ配布**には不十分であり、公開鍵暗号署名への移行が必要。
> ポリシー enforcement が有効な本番環境では、改ざんされたポリシーが `allow` を返すことで
> 安全性チェックをバイパスするリスクがある。**GA リリース前の必須対応事項**として扱うべき。

> ⚠️ **~~警告2: Enforcement が opt-in~~** → **対応済み（部分）**
>
> `policy_runtime_enforce=false`（デフォルト）では compiled policy は観測のみ。
> 設定ミス時にポリシー違反を reject できない可能性がある。
> ✅ **対応**: 環境変数 `VERITAS_POLICY_RUNTIME_ENFORCE=true` によるデプロイメントレベルでの enforcement 有効化をサポート。
> リクエスト単位の `ctx.context["policy_runtime_enforce"]` が未設定の場合に env var がフォールバックとして使用される。
> 本番環境では `VERITAS_POLICY_RUNTIME_ENFORCE=true` を設定することで、全リクエストでの enforcement を保証可能。

> ℹ️ **情報: ReDoS ガードレールは「低減」であり「完全排除」ではない**
>
> 現在のガードレール（パターン長/入力長/ネスト量指定子）は ReDoS リスクを大幅に低減するが、
> 全ての悪意あるパターンを排除するものではない。
> 外部供給ポリシーを許可する場合は、RE2 エンジンまたは regex タイムアウトの導入を推奨。

---

## 7. 設計パターンと品質評価

### 7.1 採用されている設計パターン

| パターン | 実装箇所 | 評価 |
|---------|---------|------|
| **Content-Addressable Storage** | `hash.py` — semantic hash | ◎ 同一内容=同一ハッシュ |
| **Adapter Pattern** | `runtime_adapter.py` — IR→Runtime | ◎ コンパイルとランタイムの分離 |
| **Pipeline Pattern** | `pipeline_policy.py` — 3ステージ | ◎ 責務の段階的分離 |
| **Observer Pattern** | `governance.py` — コールバック | ○ ホットリロード対応 |
| **Self-Documenting Policy** | `generated_tests.py` — テストベクトル | ◎ ポリシーが自らの正しさを宣言 |
| **Fail-Closed** | 各ステージの例外ハンドリング | ○ エラー時は安全側 |
| **Immutable Data** | 全 dataclass `frozen=True` | ◎ 副作用のない安全な設計 |
| **Deterministic Build** | 正規化 + 固定シリアライズ | ◎ 再現可能なビルド |

### 7.2 コード品質指標

| 指標 | 値 | 評価 |
|------|-----|------|
| ポリシーコアモジュール行数 | 1,249行 | 適切（過剰でない） |
| テスト行数 | 1,765行 | テスト:実装比 = 1.4:1（良好） |
| テスト関数数 | 119 | 十分な網羅性 |
| TODO/FIXME/HACK | 0件 | 技術的負債なし |
| 外部依存 | pydantic, yaml のみ | 最小限 |
| 型安全性 | Pydantic + TypedDict + frozen dataclass | 高い |

---

## 8. 責務境界分析

### 8.1 レイヤー間の責務分離

```
┌──────────────────────────────────────────────────────┐
│ Policy-as-Code Module (veritas_os/policy/)            │
│ 責務: ポリシー検証・正規化・コンパイル・評価           │
│ 境界: FUJI/MemoryOS への直接依存なし                  │
└──────────────────────┬───────────────────────────────┘
                       │ 最小 bridge のみ
┌──────────────────────┴───────────────────────────────┐
│ Pipeline Integration (core/pipeline/pipeline_policy.py)│
│ 責務: FUJI precheck → Policy bridge → Gate decision   │
│ 境界: policy module を lazy import、opt-in 連携       │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────┐
│ Governance API (api/routes_governance.py + governance.py)│
│ 責務: 運用ポリシー管理・RBAC・4-eyes・監査証跡        │
│ 境界: compiled policy とは独立した運用ポリシー管理     │
└──────────────────────────────────────────────────────┘
```

**所見:**
- Policy-as-Code モジュールは FUJI/MemoryOS への直接的な依存を持たず、独立性が高い。
- パイプライン統合は lazy import + optional bridge で最小侵襲。
- ガバナンスAPI は compiled policy とは独立した運用ポリシー管理層として機能。
- MemoryOS 内部責務への Policy-as-Code の侵入はレビュー範囲で確認されなかった。

---

## 9. フロントエンド統合

**ガバナンスUI コンポーネント:**

| コンポーネント | 目的 |
|---------------|------|
| `governance/page.tsx` | メインガバナンスコントロールプレーン |
| `governance-types.ts` | TypeScript 型定義 |
| `eu-ai-act-governance-dashboard.tsx` | EU AI Act コンプライアンスダッシュボード |
| `packages/types/src/governance.ts` | 共有型定義 |

**所見:**
- フロントエンドは `/v1/governance/policy` API を通じてガバナンスポリシーを管理。
- TypeScript 型がバックエンドの Pydantic モデルと整合している。
- compiled policy の評価結果はバックエンドの `response_extras` を通じてフロントエンドに伝達可能。

---

## 10. 運用準備状況

### 10.1 運用可能な機能

| 機能 | 状態 | 運用条件 |
|------|------|---------|
| ポリシーコンパイル | ✅ 即時利用可 | CLI / Python API |
| ポリシー検証 | ✅ 即時利用可 | YAML/JSON 入力 |
| ランタイム評価 | ✅ 利用可 | バンドルディレクトリ指定 |
| ガバナンスAPI | ✅ 即時利用可 | RBAC 設定必須 |
| 4-Eyes 承認 | ✅ 即時利用可 | デフォルト有効 |
| 監査証跡 | ✅ 即時利用可 | JSONL 出力 |
| テストベクトル生成 | ✅ 即時利用可 | `pytest` 実行 |

### 10.2 運用化に向けた推奨事項

| 優先度 | 項目 | 推奨内容 | 目標マイルストーン |
|--------|------|---------|-------------------|
| **高（GA必須）** | 署名強化 | `manifest.sig` を公開鍵暗号署名へ移行 | GA リリース前 |
| **高（GA必須）** | ~~Enforcement デフォルト~~ | ✅ `VERITAS_POLICY_RUNTIME_ENFORCE` env var でデプロイメントレベル制御を実装済み | 完了 |
| **中** | Transparency Log | ポリシー変更・評価結果の外部ログ連携 | GA 後 v1.1 |
| **中** | ~~`allow`/`escalate` ポリシー例~~ | ✅ 全 outcome カバーのサンプルポリシー追加済み | 完了 |
| **中** | ポリシーパック管理 | 複数ポリシーの一括配布・バージョン管理 | GA 後 v1.2 |
| **低** | 段階的 enforcement | canary → staged → full の自動化 | GA 後 v1.2 |
| **低** | RE2 エンジン | 外部供給ポリシー対応時の regex 安全性強化 | 外部ポリシー許可時 |
| **低** | データベース移行 | マルチインスタンス環境でのファイルベース永続化からの脱却 | マルチインスタンス運用時 |

---

## 11. 総合評価

### 11.1 評価サマリ

| 評価軸 | スコア | 根拠 |
|--------|--------|------|
| **機能完成度** | 89/100 | コンパイル〜評価〜パイプライン反映の全経路が動作、`effective_date` による時間制御対応、env var による enforcement デフォルト設定 |
| **設計品質** | 90/100 | 関心の分離、イミュータブル設計、決定論が徹底 |
| **テスト品質** | 90/100 | 主要パスカバー、複数ポリシー優先度解決・effective_date フィルタリング・I/Oエラーラッピング・パイプライン bridge enforcement 全パスのテスト追加 |
| **セキュリティ** | 75/100 | ReDoSガードレール済、署名は将来課題 |
| **運用準備** | 70/100 | `VERITAS_POLICY_RUNTIME_ENFORCE` env var による enforcement デフォルト設定対応、ファイルベース永続化が制約 |
| **ドキュメント** | 80/100 | 既存 docs/policy_as_code.md が包括的 |

### 11.2 成熟度判定

**Late Beta（Pre-Production / GA 直前）**

- 「Policy → IR → Bundle → Runtime 評価 → Pipeline 反映」の縦断経路は成立。
- PoC を超えた「実運用前検証が可能な基盤」に到達。
- 公開鍵署名と enforcement 強制が導入されれば、Production-Ready（GA）と判断可能。

### 11.3 改善実施ログ（2026-04-02）

以下は過去の改善で実施済みの項目:

- **ReDoS ガードレール追加**
  - パターン長上限（256文字）、入力長上限（1,024文字）、ネスト量指定子検出
  - 不正 regex の安全失敗（match しない扱い）
  - テスト3件追加（正常/長入力/ネスト量指定子）

- **非強制モード警告**
  - compiled policy 判定が `deny/halt/escalate/require_human_review` かつ `policy_runtime_enforce=false` 時に warning ログ出力
  - FUJI の既存判定ロジックは変更せず、設定ミス検知性のみ向上

- **`allow`/`escalate` ポリシー例追加**
  - `policies/examples/low_risk_route_allow.yaml`: 低リスクルートの自動実行許可ポリシー
  - `policies/examples/anomaly_detection_escalate.yaml`: 異常検知時のエスカレーションポリシー
  - 全5 outcome（allow / deny / halt / escalate / require_human_review）のサンプルが揃い、テンプレートとしての網羅性を確保
  - テストベクトル内蔵により、自動テスト生成（`generated_tests.py`）で自動検証

- **複数ポリシー優先度解決テスト追加**
  - `test_multiple_policy_precedence_resolution`: allow / escalate / deny の3ポリシーが同時に発火した際に deny（最高優先度）が選択されることを検証
  - 全トリガポリシーの obligation が集約されることを検証

- **スキーマ検証テスト拡張**
  - `test_all_example_policies_validate` のパラメータに新規2ファイルを追加（3例→5例）

- **`effective_date` フィルタリング実装**
  - `RuntimePolicy` に `effective_date` フィールドを追加し、`adapt_canonical_ir()` で canonical IR から伝達
  - `evaluator.py` に `_is_effective()` を追加: `effective_date` が将来日付のポリシーは評価ループからスキップ
  - `None`（未設定）および不正な日付形式は安全側に評価（常にアクティブ）
  - テスト2件追加: `test_future_effective_date_policy_is_skipped`, `test_past_effective_date_policy_triggers_normally`

- **コンパイラ I/O エラーラッピング**
  - `PolicyCompilationError`（`RuntimeError` 派生）を `models.py` に追加
  - `compile_policy_to_bundle()` のファイル書き込み部分を `try/except OSError` でラップし、`PolicyCompilationError` に変換
  - API 連携時に構造化されたエラー応答が可能に（`PolicyValidationError` とは独立したエラー型）
  - テスト1件追加: `test_compile_wraps_io_error_as_policy_compilation_error`

- **Enforcement 環境変数フォールバック**
  - `VERITAS_POLICY_RUNTIME_ENFORCE` 環境変数を `pipeline_policy.py` に追加
  - リクエストコンテキストに `policy_runtime_enforce` が未設定の場合、env var の値をフォールバックとして使用
  - リクエスト単位の `ctx.context["policy_runtime_enforce"]` が設定されている場合はそちらが優先
  - 本番環境では `VERITAS_POLICY_RUNTIME_ENFORCE=true` を設定することで、全リクエストでの enforcement を保証可能
  - テスト1件追加: `test_pipeline_bridge_env_var_enforcement_fallback`

- **パイプライン bridge enforcement テスト拡充**
  - 全4 outcome→status マッピングのテストを追加:
    - `test_pipeline_bridge_enforcement_deny_sets_rejected`: deny → rejected
    - `test_pipeline_bridge_enforcement_escalate_sets_modify`: escalate → modify
    - `test_pipeline_bridge_enforcement_require_human_review_sets_modify`: require_human_review → modify
    - （既存 `test_pipeline_bridge_enforcement_updates_fuji_status` で halt → rejected はカバー済み）

---

*本レビューは `veritas_os/policy/*`, `veritas_os/core/pipeline/pipeline_policy.py`, `veritas_os/api/routes_governance.py`, `veritas_os/api/governance.py`, および関連テストファイルの全コードを精読した上で作成した。*
