# TrustLog Publication Boundary v1

## 状態

設計固定済み・非実行のアーキテクチャ境界。

この文書は TrustLog publication semantics のための独立した proof track を定義します。既存の frozen controlled Decision-to-Effect claim は変更せず、production exactly-once delivery も主張しません。

## 目的

現在の TrustLog 経路は deterministic evidence lineage、順序、暗号化・署名 posture、mirror/anchor 構成、fail-closed behavior を保持していますが、`trustlog_exactly_once_publication` は controlled execution proof の明示的 non-claim のままです。

この境界では、混同してはいけない次の3つを分離します。

1. primary durable ledger に同一の論理 TrustLog entry を重複作成しないこと。
2. mirror / transparency anchor に対して、同じ論理 publication を identity/payload を変えずに安全に再試行できること。
3. 外部 mirror / anchor が publication を実際に exactly once 受理したこと。

将来の v1 implementation proof の対象は1のみです。3は外部 destination 側の独立検証可能な契約が必要であり、この境界からは導けません。

## コア不変条件

```text
logical TrustLog uniqueness
!= cross-system atomicity
!= exactly-once external delivery
!= execution authority
```

TrustLog publication record は事後証拠にすぎません。AuthorityEvidence、Human Approval、BindAuthorization、execution permission、external-effect confirmation を生成してはいけません。

## 論理 publication identity

publication 対象となる各 TrustLog object は、次の不変入力から deterministic publication identity に bind されなければなりません。

- `entry_type`
- stable logical `entry_id`
- canonical payload hash
- publication schema/version

そこから生成される `publication_key` は deterministic かつ content-bound です。

同じ `publication_key` と同じ canonical payload を持つ複数 attempt は、同一の論理 publication です。

同じ論理 identity に異なる canonical payload を再利用した場合は collision として fail closed にし、update・replacement・正常 duplicate として扱ってはいけません。

## Primary durable-ledger semantics

将来 v1 implementation が `primary_logical_exactly_once` を主張できるのは、PostgreSQL が deterministic publication identity の uniqueness を強制し、次をすべて証明した場合に限ります。

- 初回 insert で論理 entry が1件だけ commit される。
- same-key / same-payload duplicate は2件目を作らず、既に commit 済みの論理 entry を返す。
- same-key / different-payload は fail closed。
- commit 後に client response が失われても retry で2件目の論理 row を作らない。
- crash recovery は in-memory success flag ではなく durable database state から解決する。
- receipt は caller が新規作成したのか、既存の同一 publication を観測したのかを識別する。

この保証は primary durable ledger のみに適用されます。

## Secondary publication semantics

mirror と transparency anchor への publication は、destination ごとの別 state machine として扱います。

少なくとも次を durable に保持します。

- `publication_key`
- destination class / destination identifier
- canonical payload hash
- attempt count
- last attempt result
- 利用可能な場合の destination acknowledgement / receipt
- terminal / non-terminal state

概念上の state は次です。

```text
PENDING
ATTEMPTED_UNKNOWN
ACKNOWLEDGED
FAILED_TERMINAL
```

retry は同一 publication identity と完全に同じ canonical payload のみ再送可能です。外部 destination の response が失われたという理由で、新しい論理 TrustLog entry を生成してはいけません。

`ATTEMPTED_UNKNOWN` は failure と同義ではなく、destination が受理しなかった証明でもありません。

## Destination guarantee

mirror / transparency anchor への exactly-once publication を VERITAS が主張できるのは、destination contract が同じ publication identity に基づく独立検証可能な idempotency / deduplication semantics を提供する場合だけです。

その契約がない場合に許される最大の主張は次です。

```text
primary logical uniqueness is proven;
secondary delivery is retry-safe for the same immutable publication identity;
external exactly-once acceptance is not proven.
```

## Crash / retry rules

- commit 済みの primary logical entry は retry 時に新しい publication identity で再作成しない。
- primary commit 後の caller response loss は deterministic publication identity による lookup で解決する。
- secondary delivery の結果が不明なら `ATTEMPTED_UNKNOWN` 等の durable state にする。
- destination contract が idempotent retry を許す場合のみ、secondary recovery は同一 identity / payload を再試行する。
- retry 成功のために canonical TrustLog payload を書き換えてはいけない。
- TrustLog publication failure が governed action の authorization、effect、receipt、reconciliation state を遡及的に変更してはいけない。

## Frozen execution proof との関係

これは独立した evidence-publication proof track です。

次を変更してはいけません。

- authorization issuance / consumption
- pre-effect current rechecks
- credential resolution
- external-effect dispatch
- `EFFECT_UNKNOWN` semantics
- reconciliation
- BindReceipt / Outcome semantics
- confirmed-effect semantics
- frozen Decision-to-Effect architecture

将来 implementation は独立した deterministic proof を作るまで、既存 frozen controlled-execution claim に TrustLog exactly-once language を追加してはいけません。

## 将来の最小 machine contract

将来 implementation は、少なくとも次に相当する概念を持つべきです。

- `TrustLogPublicationIdentity`
- `TrustLogPrimaryPublicationResult`
- `TrustLogSecondaryPublicationState`
- `TrustLogPublicationReceipt`

publication metadata に plaintext secret や credential を保存してはいけません。

## Proof exit criteria

将来の `primary_logical_exactly_once` proof は、real PostgreSQL 上で次をすべて証明するまで完了しません。

1. concurrent same-key / same-payload attempts で論理 row が1件のみ。
2. same-key / different-payload collision が fail closed。
3. commit 後 response loss → retry で元の committed row に解決。
4. process restart 後も duplicate logical insertion 不可。
5. publication receipt が deterministic かつ replay-reviewable。
6. mirror / anchor uncertainty を confirmed failure / confirmed absence と誤報しない。
7. execution-authority semantics を導入しない。

## 明示的 non-claims

この v1 設計は次を主張しません。

- production readiness
- cross-system distributed transactions
- exactly-once mirror delivery
- exactly-once transparency-anchor delivery
- independently operated external TrustLog infrastructure
- external destination authenticity
- regulatory approval / certification
- TrustLog receipt が real-world effect の発生を証明すること
