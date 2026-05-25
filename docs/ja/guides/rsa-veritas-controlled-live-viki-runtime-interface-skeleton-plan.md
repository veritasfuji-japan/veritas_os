# RSA ↔ VERITAS Controlled Live V.I.K.I. Runtime Interface Skeleton Plan

## 英語正本

- [RSA ↔ VERITAS Controlled Live V.I.K.I. Runtime Interface Skeleton Plan](../../en/guides/rsa-veritas-controlled-live-viki-runtime-interface-skeleton-plan.md)

## 1. 目的

本書は、将来導入する controlled live V.I.K.I. runtime interface skeleton の計画を定義します。

これは documentation-only であり、以下を実装しません。

- runtime implementation
- endpoint implementation
- network implementation
- transport/authentication implementation
- replay cache implementation
- logging / telemetry implementation
- observability runtime implementation
- live V.I.K.I. integration

本計画は secrets / credentials を追加せず、real KYC data を処理せず、production use を許可しません。

runtime interface PR を作成する前に、本計画のレビューを必須とします。

## Runtime wiring status（現状）

runtime receiver は runtime code 上で local schema adapter に接続済みですが、fail-closed / not-ready を維持しています。

- Runtime receiver: `veritas_os/governance/controlled_live_viki_interface.py`
- Runtime schema adapter: `veritas_os/governance/controlled_live_viki_schema_adapter.py`
- Runtime wiring tests: `tests/governance/test_controlled_live_viki_receiver_schema_adapter_wiring_runtime.py`

挙動サマリ:

- feature flag が厳密一致 `"true"` 以外の場合、`CONTROLLED_LIVE_DISABLED` を維持。
- feature flag が `"true"` の場合、schema adapter validation のみ実行。
- 有効な schema payload は `CONTROLLED_LIVE_SCHEMA_VALID_NOT_YET_WIRED` を返す。
- 無効な schema payload は schema adapter の reason code mapping で fail-closed。
- `SAFE_PROCEED` は upstream signal のままで、`final_commit_approved` は `false` のまま。

この runtime wiring は local/offline の範囲に限定され、endpoint behavior、network behavior、live V.I.K.I. integration、credentials、replay cache implementation、logging implementation、telemetry implementation、observability runtime、production behavior は追加しません。

## 2. 現在の baseline

以下の controlled live pre-live gates は既に存在します。

- controlled live integration threat model
- controlled live payload schema draft
- controlled live transport/authentication design
- controlled live replay protection and correlation-id design
- controlled live redaction and observability design
- controlled live payload schema fixture examples
- controlled live failure-mode test plan
- controlled live fixture validation plan
- controlled live fixture validation test skeleton
- controlled live failure-mode test skeleton
- controlled live observability event taxonomy fixture plan
- controlled live observability event fixture examples
- controlled live observability event fixture validation test skeleton
- controlled live integration implementation plan

現在の検証経路は offline・synthetic-fixture-only・no-network です。

この phase では runtime controlled live interface は存在しません。

この phase では live V.I.K.I. integration は存在しません。

この phase では production observability / telemetry pipeline は存在しません。

## 3. Runtime interface skeleton boundary

将来の interface boundary:

static or controlled input object  
→ disabled-by-default controlled live runtime interface  
→ feature-flag gate  
→ schema adapter boundary  
→ fail-closed decision object  
→ existing RSA-compatible downstream path remains unchanged

最初の runtime interface skeleton は live V.I.K.I. を呼び出してはいけません。

最初の runtime interface skeleton は API endpoint を作成してはいけません。

最初の runtime interface skeleton は network I/O を実行してはいけません。

最初の runtime interface skeleton は credentials を要求してはいけません。

最初の runtime interface skeleton は logging / telemetry を書き込んではいけません。

最初の runtime interface skeleton は replay cache を実装してはいけません。

最初の runtime interface skeleton は既存 evaluator logic を bypass してはいけません。

SAFE_PROCEED は final commit approval を決して付与してはいけません。

別系統の VERITAS commit gate が承認しない限り、final_commit_approved は false を維持します。

## 4. Planned interface responsibility

将来の runtime interface skeleton が定義してよいもの:

- controlled live payload-like data の input container
- disabled-by-default entry function
- feature flag check
- fail-closed output shape
- 将来の schema validation adapter への handoff point
- no-network default behavior
- synthetic-input-only testability

将来の runtime interface skeleton が定義してはいけないもの:

- production HTTP endpoint
- webhook endpoint
- live V.I.K.I. client
- transport authentication implementation
- message integrity implementation
- replay cache implementation
- logging implementation
- telemetry implementation
- observability runtime implementation
- production credentials
- production endpoint URLs
- real KYC processing
- final commit automation

## 5. Planned feature flag

Primary planned flag:

- VERITAS_CONTROLLED_LIVE_VIKI_ENABLE

ルール:

- Default は disabled。
- Missing flag は disabled として扱う。
- Empty flag は disabled として扱う。
- Unknown flag value は disabled として扱う。
- Disabled state は fail closed。
- この flag の有効化だけで network calls を有効化してはいけません。
- この flag の有効化だけで live V.I.K.I. を有効化してはいけません。
- この flag の有効化だけで production use を有効化してはいけません。
- この flag の有効化だけで tests、schema validation、replay validation、transport/authentication validation、redaction、observability constraints、commit gate controls を bypass してはいけません。

## 6. Planned default-disabled behavior

controlled live runtime interface が disabled のとき、将来挙動は deterministic fail-closed result を返す必要があります。

- veritas_continuation_decision: PAUSE_FOR_HUMAN_REVIEW
- veritas_sandbox_commit_state: SUSPENDED_NOT_COMMITTED
- final_commit_approved: false
- required_next_action: REQUEST_HUMAN_REVIEW_OR_RETRY_WITH_VALID_UPSTREAM_STATE
- veritas_reason_code: CONTROLLED_LIVE_DISABLED

disabled は silent ignore を意味してはいけません。

disabled は SAFE_PROCEED を意味してはいけません。

disabled は final approval を意味してはいけません。

disabled は network call を実行してはいけません。

disabled は live V.I.K.I. を呼び出してはいけません。

disabled は telemetry を emit してはいけません。

disabled は raw input を永続化してはいけません。

## 7. Planned input boundary

将来の runtime interface input は、controlled-live schema-compatible fields のみ含めます。

- schema_version
- rsa_status
- trigger_source
- timestamp
- request_id
- correlation_id
- payload_issued_at
- tests に必要な synthetic metadata

Input に含めてはいけないもの:

- chain_of_thought
- hidden_model_state
- raw_llm_reasoning
- raw_viki_reasoning
- raw_llm_text
- raw_kyc_record
- customer_pii
- secrets
- credentials
- api_key
- access_token
- refresh_token
- private_key
- webhook_secret
- raw_authorization_header
- authorization
- bearer_token
- unredacted_regulated_data
- raw_payload_body
- raw_request_body
- raw_response_body
- raw_stack_trace_with_secrets

## 8. Planned output boundary

将来の runtime interface output は deterministic かつ redacted でなければなりません。

Required output shape:

- veritas_continuation_decision
- veritas_reason_code
- veritas_sandbox_commit_state
- required_next_action
- final_commit_approved
- upstream_signal_source
- request_id
- correlation_id
- schema_version
- decision_source

Rules:

- final_commit_approved の default は false。
- veritas_sandbox_commit_state の default は SUSPENDED_NOT_COMMITTED。
- upstream_signal_source は "RSA" を維持。
- output は raw payload body を含めない。
- output は raw reasoning を含めない。
- output は KYC data を含めない。
- output は secrets を含めない。
- output は credentials を含めない。

## 9. Planned fail-closed reason codes

Draft reason codes:

- CONTROLLED_LIVE_DISABLED
- CONTROLLED_LIVE_UNSUPPORTED_SCHEMA_VERSION
- CONTROLLED_LIVE_UNKNOWN_RSA_STATUS
- CONTROLLED_LIVE_MISSING_REQUIRED_FIELD
- CONTROLLED_LIVE_INVALID_TIMESTAMP
- CONTROLLED_LIVE_FORBIDDEN_FIELD_PRESENT
- CONTROLLED_LIVE_SECRET_LIKE_VALUE_PRESENT
- CONTROLLED_LIVE_REGULATED_DATA_PRESENT
- CONTROLLED_LIVE_REPLAY_DUPLICATE_REQUEST_ID
- CONTROLLED_LIVE_REPLAY_CACHE_UNAVAILABLE
- CONTROLLED_LIVE_TRANSPORT_AUTH_FAILED
- CONTROLLED_LIVE_MESSAGE_INTEGRITY_FAILED
- CONTROLLED_LIVE_UPSTREAM_TIMEOUT
- CONTROLLED_LIVE_UPSTREAM_UNAVAILABLE
- CONTROLLED_LIVE_UNEXPECTED_EXCEPTION

これらは draft runtime-interface reason codes です。

deterministic を維持し、raw sensitive values を含めてはいけません。

core/errors.py への最終マッピングは、後続 implementation PR でレビューする必要があります。

## 10. Compatibility preservation

- rsa_status は v1 payload field として維持。
- RSASandboxPayload は downstream payload container として維持。
- evaluate_rsa_sandbox_signal() は downstream evaluator として維持。
- upstream_signal_source は "RSA" を維持。
- request_id / correlation_id は controlled-live schema/correlation fields であり、rsa_status の置換ではありません。
- この phase では viki_status を導入しません。
- この phase では VIKIPayload を導入しません。
- 命名 migration は v2 として別 PR で扱います。

## 11. Planned future file placement

本 PR では actual file placement を実装しません。

Possible future placement candidates:

- veritas_os/governance/controlled_live_viki_interface.py
- veritas_os/governance/controlled_live_viki_schema_adapter.py
- veritas_os/governance/controlled_live_viki_decisions.py
- tests/governance/test_controlled_live_viki_default_disabled.py
- tests/governance/test_controlled_live_viki_schema_adapter.py

これらは planning candidates のみです。

本 PR で runtime files を作成してはいけません。

後続 PR で実際の package layout を確定してから runtime code を追加します。

## 12. Required test plan before runtime interface implementation

runtime interface implementation の前に、default-disabled behavior 用の test-only PR を追加する必要があります。

Future tests should verify:

- feature flag missing means disabled
- feature flag empty means disabled
- feature flag false means disabled
- unknown flag value means disabled
- disabled returns CONTROLLED_LIVE_DISABLED
- disabled returns PAUSE_FOR_HUMAN_REVIEW
- disabled returns SUSPENDED_NOT_COMMITTED
- disabled returns final_commit_approved false
- disabled does not call network
- disabled does not require credentials
- disabled does not import live client
- disabled does not write telemetry
- disabled does not persist raw payload
- SAFE_PROCEED does not grant final commit approval

## 13. Runtime interface implementation acceptance criteria

将来の runtime interface implementation PR は次を証明する必要があります。

- default disabled
- no endpoint
- no network call
- no live V.I.K.I. client
- no credentials
- no production endpoint URL
- no logging implementation
- no telemetry implementation
- no replay cache implementation
- no observability runtime implementation
- deterministic fail-closed output
- final_commit_approved false by default
- compatibility contract preserved
- targeted tests pass
- no dependency audit weakening

## 14. Non-goals

本計画が許可しないもの:

- runtime implementation
- endpoint implementation
- live V.I.K.I. integration
- network calls
- authentication implementation
- replay cache implementation
- logging implementation
- telemetry implementation
- observability runtime implementation
- real KYC data processing
- live customer data processing
- live LLM text ingestion
- raw V.I.K.I. reasoning ingestion
- chain-of-thought storage
- hidden model state storage
- final commit automation based only on V.I.K.I.
- bypass of VERITAS commit gate
- secrets in repository
- production AML/KYC compliance claims
- regulatory approval claims
- legal advice claims

## 15. What this plan validates

- runtime interface skeleton responsibility is defined
- default-disabled behavior is specified
- feature flag expectations are specified
- input boundary is specified
- output boundary is specified
- fail-closed reason codes are drafted
- compatibility contract is preserved
- future file placement candidates are identified
- default-disabled test plan is defined
- no runtime implementation is introduced

## 16. What this plan does not validate

- it does not implement runtime code
- it does not implement tests
- it does not implement fixtures
- it does not implement endpoints
- it does not implement transport
- it does not implement authentication
- it does not implement replay cache
- it does not implement logging
- it does not implement telemetry
- it does not implement observability runtime
- it does not connect live V.I.K.I.
- it does not process real KYC data
- it does not authorize production deployment

## 17. Recommended next PR after this plan

最も安全な次 PR は、test-only の controlled live default-disabled behavior test skeleton です。

Recommended next PR title:

`tests: add controlled live V.I.K.I. default-disabled behavior skeleton`

## 10. test-only default-disabled skeleton の現状

test-only の default-disabled behavior skeleton は
[`tests/governance/test_controlled_live_viki_default_disabled.py`](../../../tests/governance/test_controlled_live_viki_default_disabled.py) に追加済みです。

この追加は offline / synthetic-input-only であり、runtime behavior、endpoint behavior、network calls、credentials、replay cache implementation、logging implementation、telemetry implementation、observability runtime implementation、live V.I.K.I. integration は導入しません。

## 11. test-only schema adapter behavior skeleton の現状

test-only の schema adapter behavior skeleton は
[`tests/governance/test_controlled_live_viki_schema_adapter_behavior.py`](../../../tests/governance/test_controlled_live_viki_schema_adapter_behavior.py) に追加済みです。

この追加は offline / synthetic-fixture-only であり、schema adapter runtime behavior、endpoint behavior、network calls、credentials、replay cache implementation、logging implementation、telemetry implementation、observability runtime implementation、live V.I.K.I. integration は導入しません。

## Runtime status update (2026-05-24)

最初の最小 runtime module は `veritas_os/governance/controlled_live_viki_interface.py` に追加され、runtime validation は `tests/governance/test_controlled_live_viki_runtime_interface.py` に追加されました。

この runtime interface は disabled-by-default かつ local in-process only です。endpoint behavior / network behavior / live V.I.K.I. integration / credentials / replay cache / logging implementation / telemetry implementation / observability runtime / production behavior は導入していません。

## Runtime schema adapter status update

ローカル・pure・offline の runtime schema adapter が `veritas_os/governance/controlled_live_viki_schema_adapter.py` に追加され、runtime テストは `tests/governance/test_controlled_live_viki_schema_adapter_runtime.py` にあります。

この adapter が追加するのは deterministic な payload classification と fail-closed decision 構築のみです。endpoint behavior・network behavior・live V.I.K.I. integration・credentials・replay cache implementation・logging implementation・telemetry implementation・observability runtime・production behavior は追加しません。

`SAFE_PROCEED` は upstream signal のままであり、adapter の fail-closed decision では `final_commit_approved` は常に `false` のままです。

## Receiver から schema adapter への wiring behavior test skeleton の状態

`tests/governance/test_controlled_live_viki_receiver_schema_adapter_wiring_behavior.py` に **test-only** の receiver schema-adapter wiring behavior skeleton が追加されています。

この skeleton は意図的に offline / synthetic fixture 専用であり、runtime behavior の wiring はまだ実装していません。endpoint behavior、network behavior、live V.I.K.I. integration、credentials、replay cache implementation、logging implementation、telemetry implementation、observability runtime、production behavior は追加していません。

SAFE_PROCEED は upstream signal のままであり、この skeleton でも `final_commit_approved` は `false` のままです。
