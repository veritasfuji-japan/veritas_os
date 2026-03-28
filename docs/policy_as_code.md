# Policy-as-Code (Stage 2 / Compiler v0.1)

## 目的

本ドキュメントは、VERITAS Policy-as-Code の Stage 2 として導入した
**source policy → canonical IR → compiled bundle artifacts** の実装を説明します。

Stage 1 の schema validation / canonicalization / semantic hash を土台に、
Stage 2 では **Policy Compiler v0.1** を追加しました。

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
