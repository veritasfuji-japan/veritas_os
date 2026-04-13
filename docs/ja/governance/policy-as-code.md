# Policy-as-Code (Stage 3 / Runtime Adapter + Generated Tests)

## 目的

本ドキュメントは、VERITAS Policy-as-Code の Stage 2 として導入した
**source policy → canonical IR → compiled bundle artifacts** の実装を説明します。

Stage 1 の schema validation / canonicalization / semantic hash を土台に、
Stage 2 では **Policy Compiler v0.1** を追加しました。  
Stage 3 では、compiled policy artifacts を runtime で評価する adapter /
evaluator と、`test_vectors` 由来の generated tests を追加しました。

---

## Source Policy Format

- Authoring 形式: YAML または JSON
- スキーマバージョン: `schema_version: "1.0"`
- 必須項目:
  - `policy_id`
  - `version`
  - `title`
  - `description`
  - `scope` (`domains` / `routes` / `actors`)
  - `outcome` (`decision` / `reason`)
- 任意項目:
  - `effective_date` (ISO 日付文字列)
  - `conditions`
  - `requirements`
  - `constraints`
  - `obligations`
  - `test_vectors`
  - `source_refs`
  - `metadata`

許可される `outcome.decision` は次の列挙のみです。

- `allow`
- `deny`
- `halt`
- `escalate`
- `require_human_review`

---

## Compiler Entrypoint

CLI:

```bash
python -m veritas_os.scripts.compile_policy \
  policies/examples/high_risk_route_requires_human_review.yaml \
  --output-dir artifacts/policy_compiler
```

deterministic manifest を明示したい場合:

```bash
python -m veritas_os.scripts.compile_policy \
  policies/examples/high_risk_route_requires_human_review.yaml \
  --output-dir artifacts/policy_compiler \
  --compiled-at 2026-03-28T00:00:00Z
```

Python API:

- `veritas_os.policy.compile_policy_to_bundle(...)`

---

## 生成される Artifact

出力ディレクトリ:

```text
{output_dir}/{policy_id}/{version}/bundle/
├── compiled/
│   ├── canonical_ir.json
│   └── explain.json
├── signatures/
│   └── UNSIGNED              ← Ed25519 署名時は生成されない
├── manifest.json
└── manifest.sig              ← Ed25519 署名 or SHA-256 hex
```

加えて同階層に配布用アーカイブを生成:

```text
{output_dir}/{policy_id}/{version}/bundle.tar.gz
```

### canonical_ir.json

- 凍結済み Canonical IR
- semantic hash の source of truth
- deterministic JSON 形式

### explain.json

UI / audit export 向けの説明素材。

- policy purpose
- application scope summary
- outcome summary
- obligations summary
- requirements summary

### manifest.json

最低限以下を含みます。

- `policy_id`
- `version`
- `semantic_hash`
- `compiler_version`
- `compiled_at`
- `effective_date`
- `source_files`
- `schema_version` (manifest schema)
- `outcome_summary`
- `bundle_contents`
- `signing` (Ed25519 署名 or SHA-256 フォールバック)

---

## Ed25519 署名

policy bundle の真正性保証として Ed25519 公開鍵暗号署名をサポートしています。

### コンパイル時の署名

```python
from veritas_os.policy import compile_policy_to_bundle

# Ed25519 秘密鍵（PEM）を指定すると manifest.sig に電子署名を出力
result = compile_policy_to_bundle(
    "policies/examples/high_risk_route_requires_human_review.yaml",
    "artifacts/policy_compiler",
    signing_key=private_key_pem,  # bytes: Ed25519 秘密鍵 PEM
)
```

- `signing_key` 未指定時は従来通り SHA-256 ハッシュ整合チェック（レガシーモード）
- Ed25519 署名時: `manifest.signing.status = "signed-ed25519"`, `manifest.signing.algorithm = "ed25519"`
- レガシー時: `manifest.signing.status = "signed-local"`, `manifest.signing.algorithm = "sha256"`

### ランタイムでの署名検証

```python
from veritas_os.policy import load_runtime_bundle

# 公開鍵を指定して署名検証付きバンドルロード
bundle = load_runtime_bundle(
    "artifacts/policy_compiler/policy.id/1.0/bundle",
    public_key_pem=public_key_pem,  # bytes: Ed25519 公開鍵 PEM
)
```

### 環境変数

| 変数 | 目的 |
|------|------|
| `VERITAS_POLICY_VERIFY_KEY` | Ed25519 公開鍵 PEM ファイルのパスを指定。`public_key_pem` 引数が未指定の場合にフォールバックとして使用 |
| `VERITAS_POLICY_RUNTIME_ENFORCE` | `true` を設定すると、全リクエストで compiled policy enforcement を有効化。リクエスト単位の `policy_runtime_enforce` が未設定の場合のデフォルト |
| `VERITAS_POLICY_REQUIRE_ED25519` | `true` を設定すると、マニフェストが Ed25519 署名を宣言しているバンドルに対して SHA-256 フォールバックを拒否。公開鍵が利用不可の場合は `ValueError` を送出し、サイレントダウングレードを防止 |

### 鍵ペアの生成

```python
from veritas_os.policy.signing import generate_keypair

private_pem, public_pem = generate_keypair()
# private_pem → コンパイル環境に秘密保管
# public_pem → ランタイム環境に配布 or VERITAS_POLICY_VERIFY_KEY で指定
```

---

## Deterministic Output の方針

- Canonical IR は list/order/辞書キーを正規化して deterministic serialize します。
- `semantic_hash` は canonical IR のみを入力に SHA-256 で計算します。
- `compiled_at` は manifest 監査情報であり、semantic hash の対象外です。
- 生成 JSON は stable formatting (`sort_keys=True`, fixed indent) で出力します。

> 同一 source かつ同一 `--compiled-at` を与えた場合、manifest / compiled artifacts は一致します。

---

## Bundle Signing

v0.1 では SHA-256 ハッシュ整合のみでしたが、Ed25519 公開鍵暗号署名が実装済みです。

- `manifest.sig`: Ed25519 署名（Base64）または SHA-256 hex digest
- `manifest.signing`:
  - `status`: `"signed-ed25519"` または `"signed-local"` (SHA-256)
  - `algorithm`: `"ed25519"` または `"sha256"`
  - `signature_ref`: `"manifest.sig"`
  - `key_id`: 署名鍵識別子
  - `extensions`: 将来拡張用

Ed25519 署名により、秘密鍵を保有しない攻撃者はバンドルの改ざん後に有効な署名を再生成できません。
レガシー SHA-256 バンドルとの後方互換性を維持しています。

将来 Task で、以下を段階的に追加できます。

1. transparency log / trust log 連携
2. rollout / rollback policy pack metadata の追加

### Rollout / Rollback metadata（2026-04）

`metadata` に以下を追加すると、runtime bridge が段階ロールアウトを自動解釈します。

- `metadata.rollout_controls.strategy`
  - `disabled` / `canary` / `staged` / `full`
- `metadata.rollout_controls.canary_percent`
  - `0..100`（`canary` / `staged` 時に使用）
- `metadata.rollout_controls.full_enforce_after`
  - ISO-8601 datetime。到達後は canary から自動で `full` へ昇格
- `metadata.rollback`
  - `target_policy_version`, `reason` など rollback 用監査メタデータ

runtime bridge は `governance.compiled_policy_rollout` に
`enforced/state/rollback` を出力し、`policy_runtime_enforce=true` でも
canary 対象外リクエストは observe-only に維持します。

---

## Validation / Compile Flow

1. `load_and_validate_policy` で source policy を strict validation。
2. `to_canonical_ir` で Canonical IR に正規化。
3. `semantic_policy_hash` を計算。
4. `explain.json` と `manifest.json` を生成。
5. bundle directory + `bundle.tar.gz` を生成。

---

## Stage 3: Runtime Adapter / Evaluator

追加モジュール:

- `veritas_os/policy/runtime_adapter.py`
  - `load_runtime_bundle(bundle_dir, *, public_key_pem)`:
    - `manifest.json` + `compiled/canonical_ir.json` を読み込み
    - manifest.sig の署名検証（Ed25519 / SHA-256 自動判別）
    - runtime-evaluable な `RuntimePolicyBundle` へ変換
  - `adapt_compiled_payload(...)`:
    - API/pipeline から in-memory payload を渡す際の bridge
- `veritas_os/policy/evaluator.py`
  - `evaluate_runtime_policies(runtime_bundle, context)`:
    - `effective_date` フィルタリング（将来日付のポリシーはスキップ）
    - applicability 判定（domain/route/actor）
    - conditions / constraints 判定
    - outcome（allow / deny / halt / escalate / require_human_review）
    - obligations / requirements / evidence gaps / approval gaps
    - explanation を構造化して返却

返却構造（要点）:

- `applicable_policies`
- `triggered_policies`
- `final_outcome`
- `reasons`
- `required_actions`
- `obligations`
- `approval_requirements`
- `evidence_gaps`
- `explanations`
- `policy_results`

---

## FUJI / governance / pipeline への最小 integration point

`veritas_os/core/pipeline_policy.py` に bridge を追加:

- `ctx.context["compiled_policy_bundle_dir"]` が指定されると
  compiled bundle をロードして runtime 評価を実行
- 結果を `ctx.response_extras["governance"]["compiled_policy"]` に格納
- `ctx.context["policy_runtime_enforce"] = True` のときのみ
  FUJI status へ反映（最小 enforcement）
  - `deny` / `halt` → `rejected`
  - `escalate` / `require_human_review` → `modify`
- 環境変数 `VERITAS_POLICY_RUNTIME_ENFORCE=true` でデプロイメントレベルの
  enforcement デフォルト設定が可能（リクエスト単位の設定が優先）

既存の FUJI 本体を全面置換せず、「接続点のみ」を追加した最小実装です。

---

## Generated Tests (policy test_vectors → pytest)

追加モジュール:

- `veritas_os/policy/generated_tests.py`
  - `build_generated_test_cases()`
  - `policies/examples/*.yaml` の `test_vectors` を deterministic に収集
  - pytest parametrize 用ケースを生成

実テスト:

- `veritas_os/tests/test_policy_generated_vectors.py`
  - generated case を evaluator に通し、`expected_outcome` を検証
  - deterministic 生成の再現性も検証
- `veritas_os/tests/test_policy_runtime_adapter.py`
  - high-risk human review
  - missing evidence halt
  - external tool deny
  - explanation / unmet approvals / obligations surfaced
  - allow / escalate outcome support
- `veritas_os/tests/test_pipeline_compiled_policy_bridge.py`
  - pipeline integration point が governance 出力へ反映されること
  - opt-in enforcement が FUJI status に反映されること

実行例:

```bash
pytest -q veritas_os/tests/test_policy_runtime_adapter.py \
  veritas_os/tests/test_policy_generated_vectors.py \
  veritas_os/tests/test_pipeline_compiled_policy_bridge.py
```

---

## テスト観点

- valid policy compile success
- invalid policy compile failure
- manifest の必須項目整合
- explanation metadata 出力確認
- semantic hash stability
- deterministic output（固定 `compiled_at`）
- bundle structure validity

---

## セキュリティ上の注意

- semantic hash は改ざん検知の基礎であり、Ed25519 署名と組み合わせることで **真正性保証** が成立します。
- Ed25519 署名済みバンドル（`signing.status="signed-ed25519"`）は、秘密鍵なしで改ざん後の署名再生成が不可能です。
- レガシーモード（`signing.status="signed-local"`）は SHA-256 ハッシュ整合のみのため、信頼境界を跨ぐ配布には Ed25519 署名の使用を推奨します。
- source policy の `metadata` / `source_refs` は監査補助情報であり、機密データの生埋め込みは避けてください。
- runtime bridge の enforcement は opt-in (`policy_runtime_enforce` or `VERITAS_POLICY_RUNTIME_ENFORCE`) です。
  本番環境では `VERITAS_POLICY_RUNTIME_ENFORCE=true` を設定し、全リクエストでの enforcement を保証してください。
  rollout 時は監査ログと canary を併用し、fail-closed 設定を段階的に適用してください。
- Ed25519 署名済みバンドルを運用する場合は `VERITAS_POLICY_REQUIRE_ED25519=true` を設定し、
  公開鍵の設定ミスによるサイレントダウングレード（Ed25519→SHA-256）を防止してください。
