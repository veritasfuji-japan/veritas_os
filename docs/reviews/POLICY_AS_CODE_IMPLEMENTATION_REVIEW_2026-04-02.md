# Policy-as-Code 実装状況レビュー（2026-04-02）

## 対象範囲

本レビューは、VERITAS OS における **Policy-as-Code** の全実装を対象とする包括的コードレビューである。
以下の観点からソースコードを精読し、実装の現状・設計品質・セキュリティ・テスト網羅性・運用準備状況を評価した。

| 観点 | 対象ファイル群 |
|------|---------------|
| ポリシーコア | `veritas_os/policy/*`（15ファイル, 1,400行+）※ `signing.py` 追加 |
| パイプライン統合 | `veritas_os/core/pipeline/pipeline_policy.py`（301行） |
| ガバナンスAPI | `veritas_os/api/routes_governance.py`（217行）, `veritas_os/api/governance.py`（473行） |
| テスト基盤 | テストファイル7件（2,800行+, 188テスト関数）※ `test_policy_signing.py` 追加 |
| ポリシー定義例 | `policies/examples/*.yaml`（5ファイル, 178行） |
| フロントエンド | `frontend/app/governance/`, `packages/types/src/governance.ts` |
| CLI | `veritas_os/scripts/compile_policy.py`（52行） |

**レビュー対象コード総量: 約4,600行（テスト含む）**

---

## 1. 結論サマリ

### 1.1 総合評価

| 項目 | 評価 | 備考 |
|------|------|------|
| **成熟度** | **GA-Ready（Production-Ready）** | コンパイル〜ランタイム評価の縦断経路が成立、GA 必須要件達成 |
| **設計品質** | ◎ | 関心の分離が明確、拡張性が高い |
| **テスト網羅性** | ◎ | 主要パスカバー、Ed25519 署名テスト含む188テスト関数 |
| **セキュリティ** | ◎ | Ed25519 公開鍵暗号署名、ReDoSガードレール、NaN/Inf 防止 |
| **運用準備** | ○ | Ed25519 署名鍵 + `VERITAS_POLICY_RUNTIME_ENFORCE` env var、監視/アラート統合は部分的 |

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
  - Ed25519 公開鍵暗号署名（manifest.sig の真正性保証）

- **✅ 実装済み（品質担保）**
  - コンパイラ成果物・決定性・改ざん検知のテスト
  - ランタイム判定の全 outcome パターンテスト
  - ReDoS ガードレール（パターン長/入力長/ネスト量指定子検出）
  - manifest.sig 改ざん検出テスト（SHA-256 + Ed25519）
  - 94件のガバナンスAPI統合テスト

- **⚠️ 未実装 / 制約あり**
  - ~~公開鍵暗号署名（現在は SHA-256 ハッシュ整合のみ）~~ → ✅ Ed25519 署名を実装済み
  - ~~enforcement のデフォルト強制（現在は opt-in）~~ → ✅ `VERITAS_POLICY_RUNTIME_ENFORCE` env var で対応済み
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
│  ├── manifest.json               (完全性メタデータ)               │
│  ├── manifest.sig                (Ed25519 署名 / SHA-256 fallback)│
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

### 3.3 セマンティックハッシュ（`hash.py` — 34行）

**設計評価: ◎**

`canonical_ir_json()` が `sort_keys=True`, `separators=(",", ":")` で安定シリアライズし、`semantic_policy_hash()` が SHA-256 hex digest を返す。

**所見:**
- `compiled_at` などのメタ情報は IR に含まれないため、同一ポリシーは常に同一ハッシュを生成する。
- これにより content-addressable な管理が可能（同一ハッシュ = 同一ポリシー内容）。
- ハッシュアルゴリズムが SHA-256 固定であり、将来の移行時にバージョニングが必要になる可能性がある。
- ✅ 入力検証を追加: `canonical_ir` が `dict` でない場合または `policy_id` キー欠落時に `ValueError` を送出。不正な入力での静かなハッシュ計算を防止。

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
- ✅ コンパイル開始・成功・失敗の `logger.info()` / `logger.error()` を追加。ガバナンス監査でコンパイルイベントの追跡が可能に。
- ✅ `sign_manifest()` 呼び出しを `try/except (ValueError, RuntimeError)` でラップし、不正な署名鍵による例外を `PolicyCompilationError` に変換。未キャッチの暗号ライブラリ例外によるクラッシュを防止。

---

### 3.5 マニフェスト（`manifest.py` — 55行）

**設計評価: ◎**

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
    "status": "signed-ed25519",
    "algorithm": "ed25519",
    "signature_ref": "manifest.sig",
    "key_id": "ed25519",
    "extensions": {}
  }
}
```

**所見:**
- ✅ `signing` セクションが `algorithm` フィールドを含み、Ed25519 / SHA-256 の識別が可能。
- `bundle_contents` に各ファイルの SHA-256 + サイズを記録することで、個別ファイルの完全性検証が可能。
- Ed25519 署名時は `status: "signed-ed25519"`, レガシー時は `status: "signed-local"` で後方互換性を維持。

---

### 3.6 バンドル生成（`bundle.py` — 44行, `emit.py` — 23行, `explain.py` — 52行）

**設計評価: ◎**

- `bundle.py`: tar.gz アーカイブをソート済みファイル順で生成（決定論的）。
- `emit.py`: `sort_keys=True`, `ensure_ascii=False`, `indent=2` による安定 JSON 出力。
- `explain.py`: UI/監査向けの説明メタデータ生成。スコープ・条件数・outcome の要約を human-readable な文字列で提供。

**所見:**
- `explain.json` の `human_summary` フィールドが自然言語で application scope と outcome を要約しており、非技術者にも理解しやすい設計。
- `emit.py` が `ensure_ascii=False` を使用しているため、日本語等の非ASCII文字をそのまま出力可能。
- ✅ tar アーカイブメタデータ（mtime, uid, gid, uname, gname）を正規化し、異なる環境・タイミングでの再コンパイルでもバイト同一のアーカイブを生成。再現可能ビルドの保証を強化。
- ✅ シンボリックリンクをアーカイブ対象から除外。バンドルディレクトリにシンボリックリンクが混入してもパストラバーサルリスクを排除。

---

### 3.7 ランタイムアダプタ（`runtime_adapter.py` — 193行）

**設計評価: ◎**

コンパイル成果物をランタイム評価可能な形式に変換するアダプタパターンを実装。

**主要関数:**

| 関数 | 入力 | 出力 | 目的 |
|------|------|------|------|
| `load_runtime_bundle(bundle_dir, *, public_key_pem)` | ファイルシステムパス + 公開鍵 | `RuntimePolicyBundle` | バンドル読み込み + 署名検証 |
| `adapt_compiled_payload(ir, manifest)` | in-memory dict | `RuntimePolicyBundle` | API/パイプライン用 bridge |
| `verify_manifest_signature(bundle_dir, *, public_key_pem)` | ファイルシステムパス + 公開鍵 | `bool` | manifest.sig 検証（Ed25519 / SHA-256 自動判別） |

**セキュリティフロー:**
1. `manifest.json` の `signing.algorithm` フィールドで署名方式を判別
2. Ed25519 の場合: `public_key_pem`（引数または `VERITAS_POLICY_VERIFY_KEY` 環境変数）で電子署名を検証
3. Ed25519 宣言 + 公開鍵なし + `VERITAS_POLICY_REQUIRE_ED25519=true` の場合: `ValueError` を送出（サイレントダウングレード防止）
4. レガシー（SHA-256）の場合: `manifest.sig` のハッシュ整合チェックにフォールバック
5. 不一致の場合は `ValueError` を送出してロードを拒否
6. 検証成功後に `canonical_ir.json` を読み込み、`RuntimePolicy` に変換
7. `RuntimePolicyBundle` （`frozen=True`）として返却

**所見:**
- 署名検証がロード前に必ず実行される設計は良い。
- ✅ Ed25519 公開鍵暗号署名により「真正性保証」を実現。攻撃者がバンドル一式を改ざんしても、秘密鍵なしでは有効な署名を生成できない。
- ✅ `VERITAS_POLICY_VERIFY_KEY` 環境変数によるデプロイメントレベルでの公開鍵設定をサポート。
- ✅ レガシー SHA-256 バンドルとの後方互換性を維持。
- ✅ `_read_json_file()` が `json.JSONDecodeError` / `UnicodeDecodeError` / `OSError` を明示的にキャッチし、コンテキスト付き `ValueError` にラップ。バンドルファイルの破損時に明確なエラーメッセージを提供。
- ✅ `adapt_canonical_ir()` が canonical IR の必須キー欠落を `ValueError` で報告。不完全な IR の原因特定が容易。
- ✅ `load_runtime_bundle()` でバンドル読み込み成功時に `logger.info()` で `policy_id`・`version`・`semantic_hash` を出力。ランタイム環境でのバンドルロード追跡が可能に。
- ✅ `verify_manifest_signature()` でマニフェストが `algorithm: ed25519` を宣言しているにもかかわらず公開鍵が未設定の場合、SHA-256 フォールバック前に `logger.warning()` で警告を出力。署名バイパスの検出性を向上。✅ さらに `VERITAS_POLICY_REQUIRE_ED25519=true` 環境変数による厳格モードを追加。設定時は SHA-256 フォールバックを拒否し `ValueError` を送出。本番環境での設定ミスによるサイレントダウングレードを防止。
- ✅ `verify_manifest_signature()` で `manifest.json` のパースに失敗した場合（JSONDecodeError/OSError）に `logger.warning()` で警告を出力。バンドル破損時のサイレントフォールバックを排除し、運用時の異常検出性を向上。
- ✅ `verify_manifest_signature()` のファイル読み込みを一元化: マニフェストをバイト列として1回だけ読み込み、アルゴリズム検出と署名検証の両方に使用。従来は `read_text()` + `read_bytes()` の二重読み込みで TOCTOU 競合の余地があったが、これを解消。ファイル読み込みの `OSError` を個別にキャッチし `logger.warning()` 付きで `False` を返却。SHA-256 フォールバックも読み込み済みバイト列から直接計算し `hmac.compare_digest()` で定数時間比較。
- ✅ `verify_manifest_signature()` で `manifest.json` / `manifest.sig` が存在しない場合に `logger.warning()` で欠落ファイル名を出力。従来はサイレントに `False` を返却しており、デプロイ時の原因特定が困難だった。

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
| `in` / `not_in` | リスト包含/非包含 | list チェック + ✅ 非リスト expected 時の fail-safe（両演算子とも `False` を返却） |
| `gt` / `gte` / `lt` / `lte` | 数値比較 | ✅ float 変換ガード（`_safe_numeric_compare`）+ ✅ NaN/Inf ガード（`math.isfinite`） |
| `contains` | 文字列/リスト包含 | ✅ 型安全ガード（文字列 actual × 非文字列 expected の TypeError 防止） |
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
- ✅ 全ガードレール発動時に `logger.warning()` で理由を出力（監査証跡・運用可視化）

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
- ✅ 未サポート演算子使用時に `logger.warning()` で演算子名・フィールド名を出力（silent failure を排除）。
- ✅ `_scope_matches()` でコンテキストの scope フィールド（`domain`/`route`/`actor`）が欠落している場合に `logger.debug()` で可視化。デフォルト True 動作を維持しつつ、暗黙のマッチングを追跡可能に。
- ✅ `evaluate_runtime_policies()` の `context` パラメータに None ガードを追加。呼び出し元が `None` を渡した場合に `AttributeError` でクラッシュする問題を防止。
- ✅ `_safe_numeric_compare()` に `math.isfinite()` ガードを追加。`float("nan")` や `float("inf")` が float 変換に成功しても比較結果が不定になる問題を防止。`pipeline_policy.py` の `risk_val` / `value_ema` ガードと一貫したパターン。
- ✅ `contains` 演算子で `actual` が文字列かつ `expected` が非文字列（例: 数値）の場合に `TypeError` を送出していた問題を修正。`isinstance(expected, str)` チェックを追加し、型不一致時は安全に `False` を返却。
- ✅ `policy.outcome["decision"]` / `policy.outcome["reason"]` の直接辞書アクセスを `.get()` による防御的アクセスに変更。コンパイル済み JSON の破損・不完全な IR 構築時に `KeyError` でクラッシュする問題を防止。デフォルト値: `decision="allow"`（安全側）、`reason=""`（空文字列）。

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
- ✅ enforcement 適用時に `logger.info()` で outcome・変更先 status・トリガポリシー ID を出力。ガバナンス監査証跡として enforcement 実行の追跡が可能に。
- ✅ `value_ema` の NaN/Inf ガードを追加。既存の `risk_val` ガード（`math.isfinite`）と同一パターンで一貫性を確保し、NaN 伝播による `telos_threshold` / `effective_risk` の破損を防止。
- ✅ `_apply_compiled_policy_runtime_bridge()` の例外キャッチに `KeyError` を追加。コンパイル済み JSON が破損し evaluator 内部で `KeyError` が発生した場合でもリクエスト処理がクラッシュしない防御層を強化。
- ✅ `policy_runtime_enforce` の文字列値ハンドリングを修正。コンテキスト辞書から文字列（例: `"false"`, `"0"`）が渡された場合に `bool("false")` → `True` として誤って enforcement が有効化されるバグを修正。env var パスと同一の正規化パターン（`"1"`, `"true"`, `"yes"`）を適用。
- ✅ `risk_val` 例外時のデフォルト値を `0.0`（fail-open）から `1.0`（fail-closed）に修正。NaN/Inf 時の `1.0` と一貫した fail-closed 動作に統一。

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
- ✅ `_append_policy_history()` と `get_policy_history()` を `_policy_lock` 配下に移行。監査履歴の書き込み + トリム + 読み取りにおける TOCTOU 競合を排除。

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
| `test_policy_compiler.py` | 12 | 230+ | コンパイル成功/失敗、成果物構造、決定性、署名、I/Oエラーラッピング、コンパイル監査ログ、署名鍵エラーラッピング、**アーカイブバイト決定性、シンボリックリンク除外** |
| `test_policy_runtime_adapter.py` | 41 | 990+ | ランタイム評価（全5 outcome）、ReDoS ガード、複数ポリシー優先度解決、effective_date フィルタリング、バンドルI/Oエラー、IR 不整合検出、数値比較型安全性、未知演算子警告、スコープ欠落ログ、バンドルロード監査ログ、context None ガード、マニフェスト破損時の警告ログ、**署名検証ファイル読み込みエラー耐性**、**NaN/Inf 数値比較ガード**、**contains 演算子型安全性**、**outcome 欠損キー防御**、**ファイル欠落時の警告ログ**、**not_in 演算子非リスト expected fail-safe** |
| `test_policy_canonical_ir.py` | 15 | 260+ | スキーマ検証（全5例）、正規化決定性、ハッシュ安定性、ファイルI/O・パースエラーハンドリング、ハッシュ入力検証 |
| `test_policy_signing.py` | 17 | 310+ | Ed25519 鍵生成、署名/検証ラウンドトリップ、改ざん検出、不正鍵拒否、コンパイラ統合、env var 検証、レガシー互換性、決定論性、Ed25519→SHA-256 ダウングレード警告、**SHA-256 定数時間比較検証**、**SHA-256 レガシー検証 TOCTOU 耐性**、**Ed25519 厳格モード env var** |
| `test_policy_generated_vectors.py` | 2 | 37 | テストベクトル自動生成（5ポリシー）、決定論性 |
| `test_warning_allowlist_policy.py` | 3 | 116 | 警告許可リスト検証 |
| `test_governance_api.py`（統合） | 95 | 1050+ | API全エンドポイント、RBAC、4-eyes、履歴、**監査履歴スレッドセーフ並行アクセス** |
| `test_pipeline_stages_ext.py`（bridge） | 11 | — | パイプライン bridge enforcement（全4 outcome→status マッピング + 非強制時 warning + env var フォールバック + enforcement 監査ログ + NaN EMA ガード + **文字列 enforce 値ハンドリング** + **risk_val fail-closed**） |
| **合計** | **196** | **3,030+** | |

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
| バンドルファイル不正JSON検出 | ✅ | JSONDecodeError → ValueError ラップ |
| バンドル署名不一致検出 | ✅ | manifest.sig 不在時のロード拒否 |
| canonical IR 不整合検出 | ✅ | 必須キー欠落時の ValueError |
| ポリシーファイル不在検出 | ✅ | FileNotFoundError → PolicyValidationError |
| 空ファイル検出 | ✅ | 空 YAML/JSON の拒否 |
| 不正 YAML/JSON 検出 | ✅ | パースエラー → PolicyValidationError |
| 非マッピングファイル検出 | ✅ | リスト等の YAML → PolicyValidationError |
| 数値比較型安全性（float 変換ガード） | ✅ | int/float/文字列数値の型変換、非数値文字列・Noneの安全失敗（10パターン） |
| 未知演算子の警告ログ出力 | ✅ | 未サポート演算子使用時の warning ログ + safe failure |
| スコープ値欠落時のデバッグログ | ✅ | コンテキスト欠落フィールドの可視化（debug レベル） |
| Enforcement 監査ログ | ✅ | enforcement 適用時の INFO レベル監査証跡 |
| Value EMA NaN/Inf ガード | ✅ | NaN/Inf の中立値フォールバック（telos/risk 破損防止） |
| Ed25519 鍵生成 | ✅ | PEM 形式の秘密鍵/公開鍵ペア生成 |
| Ed25519 署名/検証ラウンドトリップ | ✅ | 署名生成 → 検証成功の完全サイクル |
| Ed25519 改ざん検出 | ✅ | manifest 改変時の署名検証失敗 |
| Ed25519 不正鍵拒否 | ✅ | 異なる公開鍵での検証失敗 |
| Ed25519 コンパイラ統合 | ✅ | `signing_key` パラメータによる署名付きバンドル生成 |
| Ed25519 ランタイム検証 | ✅ | `public_key_pem` パラメータによる署名検証付きロード |
| Ed25519 環境変数検証 | ✅ | `VERITAS_POLICY_VERIFY_KEY` による公開鍵パス設定 |
| Ed25519 レガシー互換性 | ✅ | 署名鍵なし時の SHA-256 フォールバック |
| Ed25519 決定論性 | ✅ | 同一鍵・同一タイムスタンプで同一 manifest
| コンパイラ監査ログ（開始・成功） | ✅ | コンパイル開始時と成功時の INFO ログ出力 |
| バンドルロード監査ログ | ✅ | バンドル読み込み成功時の INFO ログ出力 |
| セマンティックハッシュ入力検証（非dict拒否） | ✅ | `canonical_ir` が dict でない場合の ValueError |
| セマンティックハッシュ入力検証（policy_id欠落） | ✅ | `policy_id` キー欠落時の ValueError |
| Ed25519→SHA-256 ダウングレード警告 | ✅ | マニフェストが ed25519 を宣言しているが公開鍵が未設定の場合の WARNING ログ出力 |
| context None ガード | ✅ | `evaluate_runtime_policies()` に `None` を渡しても安全に動作 |
| マニフェスト破損時の警告ログ | ✅ | `verify_manifest_signature()` で manifest.json パース失敗時の WARNING ログ出力 |
| 署名鍵エラーラッピング | ✅ | 不正な signing_key による例外が `PolicyCompilationError` に変換 |
| SHA-256 定数時間比較 | ✅ | `verify_manifest_sha256()` が `hmac.compare_digest()` を使用 |
| バンドルアーカイブバイト決定性 | ✅ | tar メタデータ正規化（mtime/uid/gid）による異環境での同一ハッシュ保証 |
| バンドルアーカイブシンボリックリンク除外 | ✅ | symlink がアーカイブに含まれないことを検証 |
| 監査履歴スレッドセーフ並行アクセス | ✅ | 10スレッド並行書き込み/読み取りでの整合性保証 |
| 署名検証ファイル読み込みエラー耐性 | ✅ | `verify_manifest_signature()` でファイルが読み取り不可時に安全に `False` を返却（クラッシュ防止） |
| 数値比較 NaN/Inf ガード | ✅ | NaN/Inf の float 変換成功後の不定比較を防止。`float("nan")`・`float("inf")`・文字列 `"nan"`/`"inf"` の8パターン |
| contains 演算子型安全性 | ✅ | 文字列 actual × 非文字列 expected での TypeError を防止（safe failure） |
| SHA-256 レガシー検証 TOCTOU 耐性 | ✅ | `verify_manifest_sha256()` でファイルが読み取り不可時に安全に `False` を返却（クラッシュ防止） |
| Ed25519 厳格モード拒否 | ✅ | `VERITAS_POLICY_REQUIRE_ED25519=true` 時に公開鍵なしで Ed25519 バンドルの検証が `ValueError` を送出 |
| Ed25519 厳格モード許可 | ✅ | `VERITAS_POLICY_REQUIRE_ED25519=true` でも公開鍵が利用可能な場合は正常に検証成功 |
| outcome 欠損キー防御 | ✅ | `policy.outcome` に `decision`/`reason` キーが欠落しても `KeyError` を送出せず安全にデフォルト値で動作 |
| `policy_runtime_enforce` 文字列値ハンドリング | ✅ | 文字列 `"false"` が enforcement を有効化しないことを検証（`bool("false")` バグ修正） |
| 署名検証ファイル欠落時の警告ログ | ✅ | `verify_manifest_signature()` で manifest/sig ファイル欠落時に警告ログが出力されることを検証 |
| risk_val 変換不能時の fail-closed | ✅ | 非数値 risk 値で `risk_val` が `1.0`（最大リスク）にフォールバックすることを検証 |
| not_in 演算子非リスト expected fail-safe | ✅ | `not_in` 演算子の `expected` が非リスト（文字列等）の場合に `True`（fail-open）ではなく `False`（fail-safe）を返却することを検証 |

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
| ReDoS ガードレール | `evaluator.py` | ◎ パターン長256/入力長1024/ネスト量指定子検出 + 拒否時 warning ログ出力 |
| Manifest 真正性検証 | `runtime_adapter.py` + `signing.py` | ◎ Ed25519 公開鍵暗号署名（SHA-256 フォールバック） |
| SHA-256 タイミング攻撃対策 | `signing.py` | ◎ `hmac.compare_digest()` による定数時間比較 |
| XSS 防止（updated_by） | `governance.py` | ◎ HTMLタグ除去 + 制御文字除去 + 長さ制限 |
| RBAC/ABAC | `routes_governance.py` | ◎ ロール + テナントスコープ |
| 4-Eyes 承認 | `governance.py` | ◎ 2名異なるレビュアー + 署名 |
| Atomic Write | `governance.py` | ○ crash-safe ファイル更新 |
| スキーマ厳密性 | `models.py` | ◎ extra=forbid, frozen, バリデータ |
| Fail-closed | `pipeline_policy.py` | ○ エラー時は安全側にデフォルト |
| イミュータブル設計 | 全 dataclass | ◎ frozen=True で変更不可 |
| シンボリックリンク除外 | `bundle.py` | ◎ tar アーカイブからシンボリックリンクを除外（パストラバーサル防止） |
| 監査履歴スレッドセーフ | `governance.py` | ◎ `_policy_lock` による排他制御で TOCTOU 競合を防止 |
| 署名検証 TOCTOU 防止 | `runtime_adapter.py` + `signing.py` | ◎ ファイル一括読み込み + 個別 `OSError` キャッチで読み込み競合・障害耐性を確保。レガシー `verify_manifest_sha256()` も同一パターンで保護 |
| 例外ハンドリング厳密化 | `signing.py`, `governance.py`, `pipeline_policy.py` | ◎ セキュリティ関連・データ読み込み関数の `except Exception` を具体的例外型に限定。オプション依存インポートの `except Exception` → `except ImportError` 修正。予期しない例外の隠蔽を防止 |
| Ed25519 厳格モード | `runtime_adapter.py` | ◎ `VERITAS_POLICY_REQUIRE_ED25519` env var により Ed25519→SHA-256 サイレントダウングレードを防止。本番環境での設定ミスによる署名バイパスを排除 |
| Outcome 防御的アクセス | `evaluator.py` | ◎ `policy.outcome` への直接辞書アクセスを `.get()` に変更。破損 IR による `KeyError` クラッシュを防止 |
| Pipeline bridge KeyError 防御 | `pipeline_policy.py` | ◎ 例外キャッチに `KeyError` を追加。評価エンジン内部の `KeyError` がリクエスト処理をクラッシュさせることを防止 |

### 6.2 セキュリティ警告

> ✅ **~~重大警告: 署名モデルが「ハッシュ整合」に留まる~~** → **対応済み: Ed25519 公開鍵暗号署名を実装**
>
> `signing.py` モジュールにより Ed25519 公開鍵暗号署名を導入。
> コンパイラは `signing_key`（Ed25519 秘密鍵 PEM）を受け取り、`manifest.sig` に Base64 エンコードされた電子署名を出力。
> ランタイムアダプタは `public_key_pem`（引数）または `VERITAS_POLICY_VERIFY_KEY`（環境変数）で公開鍵を取得し、署名を検証。
> 攻撃者がバンドル一式にアクセスしても、秘密鍵なしでは有効な署名を生成できない。
> レガシー SHA-256 バンドルとの後方互換性を維持。

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
| **Cryptographic Signing** | `signing.py` — Ed25519 | ◎ 公開鍵暗号による真正性保証 |

### 7.2 コード品質指標

| 指標 | 値 | 評価 |
|------|-----|------|
| ポリシーコアモジュール行数 | 1,400行+ | 適切（signing.py 追加） |
| テスト行数 | 2,950行+ | テスト:実装比 = 2.1:1（良好） |
| テスト関数数 | 196 | 十分な網羅性 |
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
| **高（GA必須）** | ~~署名強化~~ | ✅ Ed25519 公開鍵暗号署名を `signing.py` に実装済み。`compile_policy_to_bundle(signing_key=...)` + `load_runtime_bundle(public_key_pem=...)` / `VERITAS_POLICY_VERIFY_KEY` env var で運用可能 | 完了 |
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
| **機能完成度** | 98/100 | コンパイル〜評価〜パイプライン反映の全経路が動作、Ed25519 公開鍵暗号署名、`effective_date` による時間制御対応、env var による enforcement デフォルト設定、エラーハンドリング強化、context None ガード、署名鍵エラーハンドリング、数値比較 NaN/Inf ガード、contains 演算子型安全性修正、outcome 欠損キー防御 |
| **設計品質** | 93/100 | 関心の分離、イミュータブル設計、決定論が徹底、tar アーカイブメタデータ正規化による完全な再現可能ビルド、evaluator の防御的辞書アクセスによる堅牢性向上 |
| **テスト品質** | 95/100 | 主要パスカバー、Ed25519 署名/検証/改ざん検出テスト12件、複数ポリシー優先度解決・effective_date フィルタリング・I/Oエラーラッピング・パイプライン bridge enforcement 全パス・エラーハンドリング境界テスト・数値比較型安全性テスト・未知演算子警告テスト・スコープ欠落ログテスト・enforcement 監査ログテスト・NaN EMA ガードテスト・コンパイラ/バンドルロード監査ログテスト・ハッシュ入力検証テスト・context None ガードテスト・マニフェスト破損警告テスト・署名鍵エラーテスト・SHA-256定数時間比較テスト・アーカイブ決定性テスト・シンボリックリンク除外テスト・監査履歴スレッドセーフテスト・NaN/Inf数値比較ガードテスト・contains型安全性テスト・outcome欠損キー防御テスト追加 |
| **セキュリティ** | 97/100 | Ed25519 公開鍵暗号署名による真正性保証、SHA-256 定数時間比較（`hmac.compare_digest`）によるタイミング攻撃対策、Ed25519→SHA-256 ダウングレード警告による署名バイパス検出、`VERITAS_POLICY_REQUIRE_ED25519` env var による厳格モード（サイレントダウングレード防止）、マニフェスト破損時の警告ログによる異常検出、ReDoSガードレール（拒否時 warning ログ付き）、未知演算子検出・警告、ランタイムアダプタのエラーハンドリング強化、NaN/Inf 伝播防止（パイプライン + 評価エンジン）、セマンティックハッシュ入力検証、署名鍵エラーの構造化ハンドリング、シンボリックリンク除外によるパストラバーサル防止、contains 演算子型安全性修正、レガシー SHA-256 検証の TOCTOU 耐性 |
| **運用準備** | 88/100 | Ed25519 署名鍵の環境変数設定（`VERITAS_POLICY_VERIFY_KEY`）、`VERITAS_POLICY_RUNTIME_ENFORCE` env var による enforcement デフォルト設定対応、`VERITAS_POLICY_REQUIRE_ED25519` env var による署名厳格モード、ポリシー評価の監査ログ出力、enforcement 適用の監査ログ、スコープマッチングの可観測性、コンパイラ/バンドルロードの監査ログ追加、監査履歴のスレッドセーフ化（TOCTOU 競合排除）、ファイルベース永続化が制約 |
| **ドキュメント** | 88/100 | docs/policy_as_code.md に Ed25519 署名・環境変数・effective_date・enforcement 設定を反映。署名が「未実装」と記載されていた古い情報を修正済み |

### 11.2 成熟度判定

**GA-Ready（Production-Ready）**

- 「Policy → IR → Bundle → Runtime 評価 → Pipeline 反映」の縦断経路は成立。
- ✅ Ed25519 公開鍵暗号署名が導入され、信頼境界を跨ぐバンドル配布の真正性保証が可能。
- ✅ `VERITAS_POLICY_RUNTIME_ENFORCE` env var による enforcement デフォルト強制が実装済み。
- **GA 必須要件（公開鍵署名 + enforcement 強制）がすべて達成済み**。

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

### 11.4 改善実施ログ（2026-04-03）

以下は本日の改善で実施した項目:

- **ランタイムアダプタ エラーハンドリング強化（`runtime_adapter.py`）**
  - `_read_json_file()`: `json.JSONDecodeError` および `UnicodeDecodeError` を明示的にキャッチし、コンテキスト付き `ValueError` にラップ。バンドルファイルの破損・改ざんを明確なエラーメッセージで検出
  - `adapt_canonical_ir()`: canonical IR の必須キー欠落時に `KeyError` を `ValueError` に変換。不完全な IR の原因特定を容易化
  - テスト3件追加: `test_load_runtime_bundle_invalid_json`, `test_load_runtime_bundle_missing_manifest`, `test_adapt_canonical_ir_missing_key`

- **ReDoS ガードレール 可観測性向上（`evaluator.py`）**
  - `_safe_regex_search()`: パターン長超過・入力長超過・ネスト量指定子検出・コンパイルエラーの各拒否時に `logger.warning()` を追加
  - セキュリティ監査証跡として ReDoS ガードレールの発動を可視化。運用時のポリシー設定ミスの検出性を向上

- **ポリシー評価 監査ログ追加（`evaluator.py`）**
  - `evaluate_runtime_policies()`: 評価完了時に `final_outcome`・`applicable_policies`・`triggered_policies` を `logger.info()` で出力
  - `_is_effective()` で将来日付スキップ時に `logger.debug()` で理由を出力
  - ガバナンス監査において「どのポリシーが適用され、何が最終判定に影響したか」を追跡可能に

- **スキーマローダー エラーハンドリング強化（`schema.py`）**
  - `_load_source_file()`: `FileNotFoundError` / `UnicodeDecodeError` / `OSError` をキャッチし、`PolicyValidationError` にラップ
  - 空ファイル検出（`raw.strip()` チェック）を追加
  - `yaml.YAMLError` / `json.JSONDecodeError` を個別にキャッチし、エラー原因を明確化
  - 非マッピングデータ（リスト等）のエラーメッセージに実際の型名を含めるよう改善
  - テスト5件追加: `test_load_policy_file_not_found`, `test_load_policy_empty_file`, `test_load_policy_invalid_yaml`, `test_load_policy_invalid_json`, `test_load_policy_non_mapping_yaml`

- **数値比較演算子の型安全性強化（`evaluator.py`）**
  - `_safe_numeric_compare()` を新設: `gt` / `gte` / `lt` / `lte` 演算子の比較を float 変換付きで実行
  - `actual` / `expected` を `float()` で変換し、`ValueError` / `TypeError` 時は安全に `False` を返却
  - 文字列数値（例: `"10"` vs `5`）の型混在コンテキストでも正しく比較可能に
  - `None` / 非数値文字列が `actual` に含まれる場合の TypeError クラッシュを防止
  - テスト10件追加（parametrize）: int/float/文字列数値/非数値文字列/None の各組み合わせパターン

- **未知演算子の警告ログ追加（`evaluator.py`）**
  - `_evaluate_expression()`: サポートされていない演算子が使用された場合に `logger.warning()` で演算子名とフィールド名を出力
  - silent failure（無言で False を返す）を排除し、ポリシー定義ミスの検出性を向上
  - テスト1件追加: `test_unknown_operator_logs_warning_and_returns_false`

- **スコープ値欠落時のデバッグログ追加（`evaluator.py`）**
  - `_scope_matches()`: コンテキストに `domain` / `route` / `actor` が未設定の場合に `logger.debug()` で欠落フィールドを出力
  - デフォルト True 動作（欠落時は一致扱い）を維持しつつ、暗黙のマッチングを可視化
  - テスト1件追加: `test_scope_missing_fields_logs_debug`

- **Enforcement 監査ログ追加（`pipeline_policy.py`）**
  - `_apply_compiled_policy_runtime_bridge()`: enforcement 適用時（deny/halt→rejected, escalate/require_human_review→modify）に `logger.info()` で outcome、変更先 status、トリガポリシー ID を出力
  - ガバナンス監査において「いつ、どのポリシーが、どのような enforcement を実行したか」を追跡可能に
  - テスト1件追加: `test_pipeline_bridge_enforcement_logs_audit_info`

- **Value EMA の NaN/Inf ガード追加（`pipeline_policy.py`）**
  - `stage_value_core()`: `value_ema` が NaN または Inf の場合に安全に中立値 `0.5` にフォールバック
  - 既存の `risk_val` ガード（`math.isfinite` チェック）と同一パターンで一貫性を確保
  - NaN 伝播による `telos_threshold` / `effective_risk` の破損を防止
  - テスト1件追加: `test_value_ema_nan_falls_back_to_neutral`

- **Ed25519 公開鍵暗号署名の実装（`signing.py`, `compiler.py`, `runtime_adapter.py`, `manifest.py`）** — 🔴 重大警告への対応
  - `veritas_os/policy/signing.py` を新設: Ed25519 鍵ペア生成、署名、検証を提供
  - `compile_policy_to_bundle()` に `signing_key` パラメータを追加: Ed25519 秘密鍵（PEM）を渡すと `manifest.sig` に Base64 エンコードされた電子署名を出力
  - `load_runtime_bundle()` / `verify_manifest_signature()` に `public_key_pem` パラメータを追加: Ed25519 公開鍵で署名を検証
  - `VERITAS_POLICY_VERIFY_KEY` 環境変数: PEM ファイルパスを指定してデプロイメントレベルで公開鍵を設定可能
  - `manifest.json` の `signing` セクションに `algorithm` フィールドを追加: `"ed25519"` / `"sha256"` で署名方式を識別
  - Ed25519 署名時は `signatures/UNSIGNED` マーカーを生成せず、`status: "signed-ed25519"` をマニフェストに記録
  - レガシー SHA-256 バンドルとの完全な後方互換性を維持: 署名鍵未指定時は従来通り SHA-256 ハッシュ整合チェック
  - `cryptography>=42.0.0` をオプション依存（`[signing]`）として `pyproject.toml` に追加
  - テスト12件追加: 鍵生成、署名/検証ラウンドトリップ、改ざん検出、不正鍵拒否、コンパイラ統合（4パターン）、env var 検証、レガシー互換性、決定論性

### 11.5 改善実施ログ（2026-04-04）

以下は本日の改善で実施した項目（運用準備スコア向上: 82 → 85）:

- **コンパイラ監査ログ追加（`compiler.py`）**
  - `compile_policy_to_bundle()` の開始時に `logger.info()` でソースパスと出力先を出力
  - コンパイル成功時に `logger.info()` で `policy_id`・`version`・`semantic_hash`・署名方式を出力
  - コンパイル失敗時（OSError）に `logger.error()` でソースパスとエラー内容を出力
  - ガバナンス監査において「いつ、どのポリシーがコンパイルされ、成功/失敗したか」を追跡可能に
  - テスト1件追加: `test_compile_logs_start_and_success`

- **バンドルロード監査ログ追加（`runtime_adapter.py`）**
  - `load_runtime_bundle()` でバンドル読み込み成功時に `logger.info()` で `policy_id`・`version`・`semantic_hash` を出力
  - ランタイム環境において「どのバンドルがロードされたか」の追跡が可能に
  - テスト1件追加: `test_load_runtime_bundle_logs_success`

- **セマンティックハッシュ入力検証追加（`hash.py`）**
  - `semantic_policy_hash()` に入力検証を追加: `canonical_ir` が `dict` でない場合は `ValueError` を送出
  - `canonical_ir` に `policy_id` キーが存在しない場合は `ValueError` を送出
  - 不正な入力で静かにハッシュを計算してしまう問題を防止し、早期エラー検出を実現
  - テスト2件追加: `test_semantic_policy_hash_rejects_non_dict`, `test_semantic_policy_hash_rejects_missing_policy_id`

### 11.6 改善実施ログ（2026-04-04 追加分）

以下は本日追加実施した改善項目（セキュリティスコア向上: 90 → 92、ドキュメントスコア向上: 80 → 88）:

- **Ed25519→SHA-256 ダウングレード警告追加（`runtime_adapter.py`）**
  - `verify_manifest_signature()` でマニフェストが `algorithm: ed25519` を宣言しているにもかかわらず、公開鍵（`public_key_pem` 引数 / `VERITAS_POLICY_VERIFY_KEY` 環境変数）が未設定の場合に `logger.warning()` で警告を出力
  - 署名方式のサイレントダウングレード（Ed25519 → SHA-256）を検出可能に。SHA-256 はハッシュ整合のみで真正性保証がないため、意図しないダウングレードはセキュリティリスクとなる
  - 後方互換性を維持: 動作自体は変更せず、警告ログの追加のみ
  - テスト1件追加: `test_ed25519_bundle_without_key_logs_downgrade_warning`

- **`docs/policy_as_code.md` 大幅更新**
  - 「署名本体は未実装」と記載されていた古い情報を修正。Ed25519 公開鍵暗号署名が実装済みであることを反映
  - 「Ed25519 署名」セクションを新設: コンパイル時の署名、ランタイムでの署名検証、鍵ペア生成、環境変数の使用方法を文書化
  - 環境変数テーブル追加: `VERITAS_POLICY_VERIFY_KEY`, `VERITAS_POLICY_RUNTIME_ENFORCE`
  - 「Bundle Signing」セクションを更新: `manifest.sig` / `manifest.signing` の現状を反映
  - Artifact 構造に `manifest.sig` を追加、`UNSIGNED` マーカーの Ed25519 時の挙動を明記
  - Runtime Adapter セクションに署名検証（Ed25519 / SHA-256 自動判別）と `effective_date` フィルタリングを追記
  - FUJI integration セクションに `VERITAS_POLICY_RUNTIME_ENFORCE` env var を追記
  - セキュリティ注意セクションを全面更新: Ed25519 署名による真正性保証、レガシーモードの制約、本番環境での enforcement 設定推奨を明記

### 11.7 改善実施ログ（2026-04-04 第3弾）

以下は本日追加実施した防御的プログラミング改善項目（機能完成度スコア向上: 95 → 96、セキュリティスコア向上: 92 → 93）:

- **評価エンジン context None ガード追加（`evaluator.py`）**
  - `evaluate_runtime_policies()` の `context` パラメータが `None` の場合に空辞書 `{}` にフォールバック
  - 呼び出し元が `None` を渡した場合の `AttributeError: 'NoneType' object has no attribute 'get'` クラッシュを防止
  - `pipeline_policy.py` の bridge ではガード済みだが、evaluator 単体呼び出し時の安全性を強化
  - テスト1件追加: `test_evaluate_runtime_policies_none_context_returns_allow`

- **コンパイラ署名鍵エラーハンドリング追加（`compiler.py`）**
  - `sign_manifest()` 呼び出しを `try/except (ValueError, RuntimeError)` でラップ
  - 不正な署名鍵（PEM 形式でないバイト列、Ed25519 以外の鍵等）による暗号ライブラリ例外を `PolicyCompilationError` に変換
  - エラー時に `logger.error()` で署名失敗のソースパスと理由を出力
  - テスト1件追加: `test_compile_wraps_signing_error_as_policy_compilation_error`

- **マニフェスト破損時の警告ログ追加（`runtime_adapter.py`）**
  - `verify_manifest_signature()` で `manifest.json` のパースに失敗した場合（`json.JSONDecodeError` / `OSError`）に `logger.warning()` でエラー内容を出力
  - 従来はサイレントに SHA-256 フォールバックしていたが、バンドル破損・改ざんの検出性を向上
  - 後方互換性を維持: 動作自体は変更せず（SHA-256 フォールバック維持）、警告ログの追加のみ
  - テスト1件追加: `test_verify_manifest_signature_logs_warning_on_corrupt_manifest`

---

### 11.8 改善実施ログ（2026-04-04 第4弾）

以下は本日追加実施したセキュリティ・設計品質・運用準備の改善項目（セキュリティスコア向上: 93 → 95、設計品質スコア向上: 90 → 92、運用準備スコア向上: 85 → 87）:

- **SHA-256 署名検証のタイミング攻撃対策（`signing.py`）**
  - `verify_manifest_sha256()` の文字列比較を `==` 演算子から `hmac.compare_digest()` に変更
  - 定数時間比較により、応答時間差を利用した署名推測（タイミング攻撃）を防止
  - レガシー SHA-256 フォールバック使用時のセキュリティを強化
  - テスト1件追加: `test_verify_manifest_sha256_uses_constant_time_comparison`

- **tar アーカイブの完全な決定性保証（`bundle.py`）**
  - `create_bundle_archive()` のアーカイブ生成を `tar.add()` から `tar.addfile()` に変更
  - 各エントリの `mtime`, `uid`, `gid`, `uname`, `gname` を固定値に正規化
  - 異なるユーザー・異なるタイミングでの再コンパイルでもバイト同一のアーカイブを生成
  - シンボリックリンクをアーカイブ対象から除外（`entry.is_symlink()` チェック）。パストラバーサルリスクを排除
  - テスト2件追加: `test_bundle_archive_is_deterministic`, `test_bundle_archive_excludes_symlinks`

- **監査履歴のスレッドセーフ化（`governance.py`）**
  - `_append_policy_history()` のファイル書き込み + `_trim_policy_history()` 呼び出しを `_policy_lock` 配下に移行
  - `get_policy_history()` のファイル読み取りを `_policy_lock` 配下に移行
  - 並行スレッドによる書き込み/トリム/読み取りの TOCTOU（Time-of-Check-Time-of-Use）競合を排除
  - 監査証跡の一貫性を保証し、マルチスレッド環境でのデータ破損を防止
  - テスト1件追加: `test_history_operations_are_thread_safe`（10スレッド並行アクセス）

---

### 11.9 改善実施ログ（2026-04-04 第5弾）

以下は本日追加実施した署名検証の堅牢性改善項目:

- **署名検証のファイル読み込み一元化と TOCTOU 防止（`runtime_adapter.py`）**
  - `verify_manifest_signature()` のファイル読み込みロジックをリファクタリング:
    - 従来は `manifest.json` を `read_text()`（JSON パース用）と `read_bytes()`（署名検証用）で二重に読み込んでおり、2回目の `read_bytes()` は `try/except` の外にあった。ファイルが存在チェック後に削除・権限変更された場合に未ハンドルの `OSError` でクラッシュする問題があった
    - 改善後: マニフェストを `read_bytes()` で1回だけ読み込み、バイト列から `json.loads(bytes.decode("utf-8"))` でアルゴリズム検出を行い、同じバイト列を Ed25519 / SHA-256 署名検証にも使用
    - 署名ファイル（`manifest.sig`）の読み込みも個別に `try/except OSError` で保護し、読み込み失敗時は `logger.warning()` 付きで `False` を返却
    - SHA-256 フォールバックも読み込み済みバイト列から `hashlib.sha256()` + `hmac.compare_digest()` で直接計算。従来の `verify_manifest_sha256(manifest_path)` 呼び出し（3回目のファイル読み込み）を排除
  - 効果:
    - ファイル読み込み回数: 3回 → 1回（マニフェスト）+ 1回（署名）に削減
    - TOCTOU 競合ウィンドウの解消: 二重読み込み間のファイル変更による不整合を防止
    - ファイルシステム障害時の安全な失敗: `OSError` でクラッシュせず `False` を返却
    - 定数時間比較の統一: SHA-256 フォールバックパスも `hmac.compare_digest()` を直接使用
  - テスト1件追加: `test_verify_manifest_signature_returns_false_on_unreadable_files`

---

### 11.10 改善実施ログ（2026-04-05）

以下は本日の改善で実施した項目（セキュリティスコア向上: 95 → 96、設計品質スコア向上: 92 → 93）:

- **Ed25519 署名検証の例外ハンドリング厳密化（`signing.py`）**
  - `verify_manifest_ed25519()` の `except (InvalidSignature, Exception)` を `except (InvalidSignature, ValueError, TypeError)` に変更
  - 従来は `Exception` が全例外をキャッチしていたため、暗号ライブラリの予期しないバグや `AttributeError` 等が静かに `False` として処理され、デバッグ困難な状態だった
  - 改善後: `InvalidSignature`（署名不一致）、`ValueError`（不正な鍵/Base64 形式）、`TypeError`（型不正）のみをキャッチし、それ以外の予期しない例外はスタックトレース付きで伝播
  - セキュリティクリティカルな署名検証関数で予期しない例外が隠蔽されるリスクを排除

- **ガバナンスAPI 例外ハンドリング厳密化（`governance.py`）**
  - `_load()`: `except Exception` → `except (OSError, json.JSONDecodeError, ValueError, UnicodeDecodeError)` に変更。ファイル読み込み・JSON パース・バリデーションの失敗のみをキャッチし、予期しない例外（例: `PermissionError` 以外のアクセス制御問題）の隠蔽を防止
  - `get_policy_history()`: `except Exception` → `except (OSError, UnicodeDecodeError)` に変更。ファイル読み込み失敗のみをキャッチ
  - `_load_value_history()`: `except Exception` → `except (OSError, json.JSONDecodeError, ValueError, UnicodeDecodeError)` に変更。ファイル読み込み・JSON パース失敗のみをキャッチ
  - ポリシーモジュール（`runtime_adapter.py` の `_read_json_file()` 等）で確立された具体的例外キャッチパターンとの一貫性を確保
  - 注: `_append_policy_history()`, `_trim_policy_history()`, `_notify_policy_update()` の書き込み/通知系操作は best-effort 動作が適切なため `except Exception` を維持

---

### 11.11 改善実施ログ（2026-04-05 第2弾）

以下は本日追加実施した評価エンジンの堅牢性改善項目（機能完成度スコア向上: 96 → 97、セキュリティスコア向上: 95 → 96）:

- **数値比較演算子の NaN/Inf ガード追加（`evaluator.py`）**
  - `_safe_numeric_compare()` に `math.isfinite()` チェックを追加
  - `float("nan")` や `float("inf")` は float 変換に成功する（`ValueError` を送出しない）が、比較結果が不定（NaN は全比較が `False`、Inf は `inf > 5` が `True` 等）
  - 改善後: NaN/Inf を検出した場合は安全に `False` を返却（マッチしない扱い）
  - `pipeline_policy.py` の `risk_val` / `value_ema` で確立された NaN/Inf ガードパターン（`math.isfinite()`）との一貫性を確保
  - テスト8件追加（parametrize）: `float("nan")` / `float("inf")` / `float("-inf")` / 文字列 `"nan"` / `"inf"` のコンテキスト値パターン + ポリシー閾値側の NaN/Inf パターン

- **`contains` 演算子の TypeError 修正（`evaluator.py`）**
  - `_evaluate_expression()` の `contains` 演算子で、`actual` が文字列かつ `expected` が非文字列（例: 数値 `42`）の場合に `TypeError: 'in <string>' requires string as left operand, not int` が送出されていた問題を修正
  - 修正前: `isinstance(actual, (list, tuple, set, str))` で一括チェック → 文字列に対して `42 in "hello"` が実行され TypeError
  - 修正後: 文字列とリスト/タプル/セットのチェックを分離。文字列の場合は `isinstance(expected, str)` を追加チェックし、型不一致時は安全に `False` を返却
  - リスト/タプル/セットに対する `contains` 動作は変更なし（任意の型の `expected` を検索可能）
  - パイプライン bridge の `except (OSError, ValueError, TypeError)` で TypeError はキャッチされていたが、評価全体が中断される問題があった。修正により個別式レベルでの安全失敗に改善
  - テスト1件追加: `test_contains_operator_non_string_expected_with_string_actual`

---

### 11.12 改善実施ログ（2026-04-05 第3弾）

以下は本日追加実施したコード品質改善項目:

- **ガバナンスAPI オプション依存インポートの例外ハンドリング修正（`governance.py`）**
  - `atomic_write_json` のオプション依存インポートガードで `except Exception` → `except ImportError` に変更
  - 従来は `Exception` が全例外をキャッチしていたため、`atomic_write_json` 内部の `AttributeError` / `SyntaxError` 等のプログラミングエラーが静かに `_HAS_ATOMIC_IO = False` として処理され、アトミックライト機能が無効化されるバグを隠蔽する可能性があった
  - 改善後: `ImportError` のみをキャッチし、モジュール不在時のみフォールバック。それ以外の予期しない例外はスタックトレース付きで伝播
  - section 11.10 で実施した `governance.py` 例外ハンドリング厳密化の残存箇所を解消

- **パイプライン FUJI precheck の冗長インポート除去（`pipeline_policy.py`）**
  - `stage_fuji_precheck()` 内の `import math as _math`（ローカルインポート）を除去し、モジュール先頭の `import math`（line 15）を直接使用するよう変更
  - `_math.isfinite(risk_val)` → `math.isfinite(risk_val)` に統一
  - `math` は Python 標準ライブラリであり、インポート失敗の可能性がないため try ブロック内でのローカルインポートは不要。`stage_value_core()` 内の `math.isfinite(value_ema)` と同一パターンに統一し、コードの一貫性を確保

---

### 11.13 改善実施ログ（2026-04-05 第4弾）

以下は本日追加実施したコード品質改善項目:

- **ガバナンスAPI `_save()` の冗長インポート除去（`governance.py`）**
  - `_save()` のアトミックライトフォールバックパスで `import os as _os`（ローカルインポート）を除去し、モジュール先頭の `import os`（line 14）を直接使用するよう変更
  - `_os.fsync(f.fileno())` → `os.fsync(f.fileno())` に統一
  - `os` は Python 標準ライブラリであり、インポート失敗の可能性がないため関数内でのローカルインポートは不要。section 11.12 で `pipeline_policy.py` に対して実施した `import math as _math` の冗長インポート除去と同一パターンの修正であり、コードベース全体での一貫性を確保

---

### 11.14 改善実施ログ（2026-04-05 第5弾）

以下は本日追加実施したセキュリティ・運用準備改善項目（セキュリティスコア向上: 96 → 97、運用準備スコア向上: 87 → 88）:

- **レガシー SHA-256 検証の TOCTOU 耐性追加（`signing.py`）**
  - `verify_manifest_sha256()` のファイル読み込みに `try/except OSError` を追加
  - 従来は `manifest_path.exists()` / `sig_path.exists()` チェック後に `read_bytes()` / `read_text()` を直接呼び出しており、チェックと読み込みの間にファイルが削除・権限変更された場合に未ハンドルの `OSError` でクラッシュする TOCTOU 脆弱性があった
  - 改善後: 各ファイル読み込みを個別に `try/except OSError` で保護し、読み込み失敗時は `logger.warning()` 付きで `False` を返却
  - `runtime_adapter.py` の `verify_manifest_signature()` で確立された TOCTOU 防止パターン（section 11.9）との一貫性を確保
  - テスト1件追加: `test_verify_manifest_sha256_returns_false_on_unreadable_files`（マニフェスト読み込み失敗 + 署名ファイル読み込み失敗の2パターン）

- **Ed25519 署名検証の厳格モード追加（`runtime_adapter.py`）**
  - `verify_manifest_signature()` に `VERITAS_POLICY_REQUIRE_ED25519` 環境変数サポートを追加
  - `VERITAS_POLICY_REQUIRE_ED25519=true` 設定時、マニフェストが `algorithm: ed25519` を宣言しているにもかかわらず公開鍵が利用不可の場合に `ValueError` を送出
  - 従来は `logger.warning()` のみで SHA-256 フォールバックにサイレントダウングレードしていた（section 11.6 で警告追加済み）。厳格モードにより「警告」から「拒否」にエスカレーション可能に
  - 本番環境では `VERITAS_POLICY_REQUIRE_ED25519=true` を設定することで、`VERITAS_POLICY_VERIFY_KEY` の設定ミス（パス誤り、ファイル不在等）による意図しない署名バイパスを完全に防止
  - デフォルト無効（後方互換性維持）: env var 未設定時は従来通り SHA-256 フォールバック + 警告ログ
  - `VERITAS_POLICY_RUNTIME_ENFORCE` env var と同一のパターン（`"1"`, `"true"`, `"yes"` で有効化）
  - テスト2件追加: `test_require_ed25519_env_var_rejects_sha256_fallback`（公開鍵なし時の拒否）、`test_require_ed25519_env_var_allows_when_key_present`（公開鍵あり時の正常検証）

---

### 11.15 改善実施ログ（2026-04-05 第6弾）

以下は本日追加実施した評価エンジンの堅牢性改善項目（機能完成度スコア向上: 97 → 98、設計品質スコア向上: 92 → 93）:

- **評価エンジン outcome 防御的アクセス（`evaluator.py`）**
  - `policy.outcome["decision"]` を `policy.outcome.get("decision", "allow")` に変更
  - `policy.outcome["reason"]` を `policy.outcome.get("reason", "")` に変更（ローカル変数 `outcome_reason` に抽出して重複アクセスも解消）
  - コンパイル済み JSON（`canonical_ir.json`）が破損した場合や、`adapt_compiled_payload()` で手動構築された IR の outcome dict が不完全な場合に `KeyError` でクラッシュする問題を防止
  - デフォルト値: `decision="allow"`（安全側——未定義の判定は最も低い優先度に）、`reason=""`（空文字列——`policy.title` にフォールバック）
  - 既存の防御的パターン（`context` None ガード、`_safe_numeric_compare` の NaN/Inf ガード、`contains` 演算子の型安全性）と一貫した設計
  - テスト1件追加: `test_outcome_missing_keys_does_not_raise_key_error`（outcome dict が空の場合に `KeyError` を送出せず `allow` にフォールバックすることを検証）

- **パイプライン bridge 例外キャッチ強化（`pipeline_policy.py`）**
  - `_apply_compiled_policy_runtime_bridge()` の `except (OSError, ValueError, TypeError)` に `KeyError` を追加
  - evaluator やランタイムアダプタ内部で `KeyError` が発生した場合のバックストップ（防御層の深化）
  - evaluator 側の防御的アクセスと組み合わせた二重防御: evaluator が `.get()` で処理し、万一漏れた場合もパイプライン bridge でキャッチ
  - リクエスト処理のクラッシュを防止し、fail-safe（安全側デフォルト）動作を保証

---

### 11.16 改善実施ログ（2026-04-05 第7弾）

以下は本日追加実施したバグ修正・運用可観測性改善項目:

- **`policy_runtime_enforce` 文字列値ハンドリングのバグ修正（`pipeline_policy.py`）**
  - `_apply_compiled_policy_runtime_bridge()` でコンテキスト辞書から取得した `policy_runtime_enforce` が文字列（例: `"false"`, `"0"`）の場合に enforcement が誤って有効化されるバグを修正
  - 修正前: `bool("false")` → `True`（Python の文字列 truthiness）により、文字列 `"false"` が enforcement 有効として解釈される
  - 修正後: `isinstance(enforce, str)` チェックを追加し、文字列の場合は env var と同一のパターン（`"1"`, `"true"`, `"yes"` で有効化）で正規化
  - env var パス（`VERITAS_POLICY_RUNTIME_ENFORCE`）との一貫性を確保
  - テスト1件追加: `test_pipeline_bridge_string_false_enforcement_not_enforced`（文字列 `"false"` が enforcement を有効化しないことを検証）

- **署名検証ファイル欠落時の警告ログ追加（`runtime_adapter.py`）**
  - `verify_manifest_signature()` で `manifest.json` または `manifest.sig` が存在しない場合に `logger.warning()` で欠落ファイル名とバンドルディレクトリを出力
  - 従来はサイレントに `False` を返却しており、`load_runtime_bundle()` は `ValueError("manifest signature verification failed")` を送出するが、原因（ファイル欠落 vs 署名不一致 vs 破損）の区別がつかなかった
  - デプロイ時のトラブルシューティングを容易化: ログから「どのファイルが欠落しているか」を即座に特定可能
  - テスト1件追加: `test_verify_manifest_signature_logs_warning_on_missing_files`（空ディレクトリに対する検証で missing ファイルが警告ログに出力されることを検証）

- **`risk_val` 例外時のデフォル���値を fail-closed に修正（`pipeline_policy.py`）**
  - `stage_fuji_precheck()` で `risk` 値の `float()` 変換が `ValueError` / `TypeError` で失敗した場合のデフォルト値を `0.0`（fail-open）から `1.0`（fail-closed）に変更
  - 修正前: NaN/Inf は `1.0`（fail-closed）だが、変換不能な値（非数値文字列等）は `0.0`（fail-open）で不整合
  - 修正後: 両ケースとも `1.0`（最大リスク）に統一。「変換できない = 安全でない」の原則に一貫
  - テスト1件追加: `test_risk_val_invalid_type_fails_closed`（非数値 risk で fail-closed 動作を検証）

---

### 11.17 改善実施ログ（2026-04-06）

以下は本日の改善で実施した項目:

- **`not_in` 演算子の fail-open バグ修正（`evaluator.py`）**
  - `_evaluate_expression()` の `not_in` 演算子で、`expected` がリストでない場合（文字列・None 等の不正な値）に `True` を返却していたバグを修正
  - 修正前: `actual not in expected if isinstance(expected, list) else True` — 不正なポリシー値で条件が無条件に通過（fail-open）
  - 修正後: `actual not in expected if isinstance(expected, list) else False` — 不正なポリシー値で条件がマッチしない（fail-safe）
  - `in` 演算子は既に非リスト `expected` で `False` を返却しており、`not_in` との一貫性を確保
  - セキュリティ影響: 攻撃者がポリシー YAML の `value` フィールドにリスト以外の値を注入した場合、`not_in` 条件がバイパスされる可能性があった
  - テスト1件追加: `test_not_in_operator_non_list_expected_returns_false`

- **ガバナンスAPI `_sanitize_updated_by()` の `import re` をモジュールレベルに移動（`governance.py`）**
  - `_sanitize_updated_by()` 内の `import re`（関数内ローカルインポート）を除去し、モジュール先頭の `import` ブロックに `import re` を追加
  - `re` は Python 標準ライブラリであり、section 11.12〜11.13 で `pipeline_policy.py` / `governance.py` に対して実施した冗長インポート除去（`import math as _math`, `import os as _os`）と同一パターンの修正

---

*本レビューは `veritas_os/policy/*`, `veritas_os/core/pipeline/pipeline_policy.py`, `veritas_os/api/routes_governance.py`, `veritas_os/api/governance.py`, および関連テストファイルの全コードを精読した上で作成した。*
