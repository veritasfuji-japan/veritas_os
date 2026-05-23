# RSA ↔ VERITAS ローカル V.I.K.I. Mock Receiver E2E Harness 検証スナップショット

## 英語正本

- [RSA ↔ VERITAS Local V.I.K.I. Mock Receiver E2E Harness Validation Snapshot](../../en/guides/rsa-veritas-local-viki-mock-receiver-e2e-harness-validation-snapshot.md)

## 1. 目的

本スナップショットは、fixture-driven なローカル V.I.K.I. mock receiver E2E harness の現時点の検証状態を記録する文書です。

- これは documentation-only です。
- これは新しい runtime implementation ではありません。
- これは live V.I.K.I. integration ではありません。
- これは production API endpoint ではありません。
- これは、マージ済みの local fixture-driven E2E harness の実装挙動を記録します。

## 2. 実装済みハーネスの対象範囲

Harness test file:

- `tests/governance/test_local_viki_mock_receiver_e2e_harness.py`

Fixture directory:

- `tests/fixtures/local_viki_mock_receiver/`

この harness は次を実施します。

- static synthetic JSON fixture files を raw text として読み込む
- raw fixture text を `ingest_local_viki_mock_payload()` に渡す
- fixed receiver clock を使用する
- 明示的な test-only guard として `VERITAS_LOCAL_VIKI_MOCK_RECEIVER_ENABLE=1` を有効化する
- 期待される VERITAS decision を検証する
- default audit redaction を検証する
- invalid fixtures の fail-closed behavior を検証する
- guard 無効時に `RuntimeError` が発生することを検証する

この harness は次を行いません。

- socket を開く
- HTTP server を起動する
- network service を呼び出す
- live V.I.K.I. に接続する
- live LLM text を取り込む
- 実データの KYC を処理する
- production commit authority を追加する

## 3. E2E 検証フロー

```text
static synthetic JSON fixture
→ raw fixture text
→ ingest_local_viki_mock_payload()
→ RSASandboxPayload
→ evaluate_rsa_sandbox_signal()
→ VERITAS decision
→ redacted audit output
```

これにより、network transport や live middleware を導入せずに local mock path を検証します。

## 4. Positive fixture inventory

| Fixture file | rsa_status | Expected continuation_decision | Expected reason_code | Expected sandbox_commit_state | Validation result |
| --- | --- | --- | --- | --- | --- |
| `tests/fixtures/local_viki_mock_receiver/viki_pos_001_safe_proceed.json` | SAFE_PROCEED | CONTINUE_TO_BIND_BOUNDARY | UPSTREAM_SAFE_PROCEED_SIGNAL | SUSPENDED_NOT_COMMITTED | Implemented |
| `tests/fixtures/local_viki_mock_receiver/viki_pos_002_density_throttled.json` | DENSITY_THROTTLED | CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED | UPSTREAM_INTERVENTION_DENSITY_THROTTLE | SUSPENDED_NOT_COMMITTED | Implemented |
| `tests/fixtures/local_viki_mock_receiver/viki_pos_003_algorithmic_humility_engaged.json` | ALGORITHMIC_HUMILITY_ENGAGED | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_INCOMPLETE_KYC_CONTEXT | SUSPENDED_NOT_COMMITTED | Implemented |
| `tests/fixtures/local_viki_mock_receiver/viki_pos_004_deferral_engaged.json` | DEFERRAL_ENGAGED | BLOCK_FINAL_COMMIT | UPSTREAM_CRITICAL_DEFERRAL_SIGNAL | BLOCKED_NOT_COMMITTED | Implemented |

## 5. Negative fixture inventory

Negative fixtures は、malformed / missing / unknown / invalid / shape mismatch の payload が `SAFE_PROCEED` に変換されないことを検証します。

| Fixture file | Invalid condition | Expected continuation_decision | Expected reason_code | Expected sandbox_commit_state | Expected next action | Validation result |
| --- | --- | --- | --- | --- | --- | --- |
| `tests/fixtures/local_viki_mock_receiver/viki_neg_001_invalid_json.json` | Malformed JSON | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_MOCK_PAYLOAD_INVALID | SUSPENDED_NOT_COMMITTED | REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW | Implemented |
| `tests/fixtures/local_viki_mock_receiver/viki_neg_002_missing_rsa_status.json` | Missing rsa_status | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_MOCK_PAYLOAD_INVALID | SUSPENDED_NOT_COMMITTED | REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW | Implemented |
| `tests/fixtures/local_viki_mock_receiver/viki_neg_003_unknown_rsa_status.json` | Unknown rsa_status | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_MOCK_PAYLOAD_INVALID | SUSPENDED_NOT_COMMITTED | REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW | Implemented |
| `tests/fixtures/local_viki_mock_receiver/viki_neg_004_invalid_timestamp.json` | Invalid timestamp | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_MOCK_PAYLOAD_INVALID | SUSPENDED_NOT_COMMITTED | REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW | Implemented |
| `tests/fixtures/local_viki_mock_receiver/viki_neg_005_payload_shape_array.json` | Payload shape is array instead of object | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_MOCK_PAYLOAD_INVALID | SUSPENDED_NOT_COMMITTED | REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW | Implemented |

## 6. Guard validation

E2E harness には guard-path test が含まれます。

期待挙動:

- `VERITAS_LOCAL_VIKI_MOCK_RECEIVER_ENABLE` が未設定の場合、`ingest_local_viki_mock_payload()` は `RuntimeError` を送出する
- guard は payload processing より前にブロックする
- これにより、明示的な local mock test context 以外での accidental use を防ぐ

明確化:

- guard は test-only の opt-in control である
- guard は production authentication ではない
- guard はこの receiver を production-ready にしない

## 7. Audit redaction validation

すべての positive E2E fixture で次を検証します。

- `audit_entry.upstream_signal_source == "RSA"`
- `audit_entry.original_llm_intent == "[REDACTED]"`
- `audit_entry.rsa_action_taken == "[REDACTED]"`
- `audit_entry.veritas_continuation_decision` が期待 `continuation_decision` と一致
- `audit_entry.veritas_sandbox_commit_state` が期待 `sandbox_commit_state` と一致

negative fixtures では次を検証します。

- `audit_entry.rsa_status == "INVALID_OR_UNAVAILABLE"`
- `audit_entry.trigger_source == "LOCAL_VIKI_MOCK_RECEIVER"`
- `audit_entry.original_llm_intent == "[REDACTED]"`
- `audit_entry.rsa_action_taken == "[REDACTED]"`

したがって次は保存されません。

- raw upstream reasoning
- V.I.K.I. internal reasoning
- chain-of-thought
- hidden model state

## 8. No-network validation boundary

- harness は local fixture files のみを読み込みます。
- harness は `requests` / `httpx` を mock しません。
- harness は sockets を必要としません。
- harness は network I/O を実行しません。
- harness は live middleware を使用しません。
- harness は secrets / credentials を使用しません。

## 9. Test command

意図された focused test command:

```bash
python -m pytest -q tests/governance/test_local_viki_mock_receiver.py tests/governance/test_local_viki_mock_receiver_e2e_harness.py
```

必要に応じて:

```bash
python -m pytest -q tests/governance/test_rsa_sandbox_receiver.py
```

この snapshot は tests や CI を変更せず、意図された validation surface の記録のみを行います。

## 10. Compatibility validation

E2E harness は次を保持します。

- `rsa_status`
- `RSASandboxPayload`
- `evaluate_rsa_sandbox_signal()`
- `upstream_signal_source = "RSA"`

互換性に関する明確化:

- `rsa_status` は `viki_status` に rename していない
- `RSASandboxPayload` は `VIKIPayload` に rename していない
- `evaluate_rsa_sandbox_signal()` は downstream evaluator のままである
- naming migration は out of scope であり、別の v2 migration として扱う

## 11. この snapshot が検証すること

- Static synthetic JSON fixtures が存在する。
- harness が raw fixture text から receiver を駆動する。
- 4 つの positive `rsa_status` variants が期待 VERITAS decisions にマップされる。
- negative fixtures は fail closed になる。
- malformed JSON は proceed しない。
- unknown `rsa_status` は proceed しない。
- invalid timestamp は proceed しない。
- array payload shape は proceed しない。
- default audit redaction が維持される。
- 明示 guard が検証される。
- live V.I.K.I. connection は存在しない。

## 12. この snapshot が検証しないこと

- live V.I.K.I. middleware は検証しない。
- network transport は検証しない。
- authentication / authorization は検証しない。
- production AML/KYC compliance は検証しない。
- regulatory approval は検証しない。
- legal advice は提供しない。
- real KYC data は検証しない。
- live LLM text は検証しない。
- local mock receiver を production-ready にはしない。
- controlled integration threat modeling の必要性を置き換えない。

## 13. この snapshot の次に推奨する PR

次の safe PR は次のいずれかです。

- controlled live V.I.K.I. integration threat model
- live payload schema draft
- local mock receiver CI validation command documentation
- fixture manifest / coverage index

推奨:

最も安全な次 PR は controlled live V.I.K.I. integration threat model です。理由は、local mock phase に design notes / fixture plan / implementation / validation snapshot / fixture-driven E2E harness がそろっているためです。
