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
│   └── UNSIGNED
└── manifest.json
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
- `signing` (future extension)

---

## Deterministic Output の方針

- Canonical IR は list/order/辞書キーを正規化して deterministic serialize します。
- `semantic_hash` は canonical IR のみを入力に SHA-256 で計算します。
- `compiled_at` は manifest 監査情報であり、semantic hash の対象外です。
- 生成 JSON は stable formatting (`sort_keys=True`, fixed indent) で出力します。

> 同一 source かつ同一 `--compiled-at` を与えた場合、manifest / compiled artifacts は一致します。

---

## Bundle Format v0.1 と将来署名拡張

v0.1 では署名本体は未実装ですが、bundle 構造に以下の拡張点を用意しています。

- `signatures/UNSIGNED` マーカー
- `manifest.signing`
  - `status`
  - `signature_ref`
  - `key_id`
  - `extensions`

将来 Task で、以下を段階的に追加できます。

1. `signatures/manifest.sig` の実装
2. `manifest.signing.signature_ref` の実リンク化
3. transparency log / trust log 連携
4. rollout / rollback policy pack metadata の追加

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
  - `load_runtime_bundle(bundle_dir)`:
    - `manifest.json` + `compiled/canonical_ir.json` を読み込み
    - runtime-evaluable な `RuntimePolicyBundle` へ変換
  - `adapt_compiled_payload(...)`:
    - API/pipeline から in-memory payload を渡す際の bridge
- `veritas_os/policy/evaluator.py`
  - `evaluate_runtime_policies(runtime_bundle, context)`:
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

- semantic hash は改ざん検知の基礎だが、**真正性保証は署名導入後**に成立します。
- `signing.status=unsigned` の bundle は、配布時に信頼境界を跨ぐ用途へそのまま使わないでください。
- source policy の `metadata` / `source_refs` は監査補助情報であり、機密データの生埋め込みは避けてください。
- runtime bridge の enforcement は opt-in (`policy_runtime_enforce`) です。  
  rollout 時は監査ログと canary を併用し、fail-closed 設定を段階的に適用してください。
