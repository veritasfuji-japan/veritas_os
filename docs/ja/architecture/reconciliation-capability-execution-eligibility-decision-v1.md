# Reconciliation Capability Execution Eligibility Decision v1

Status: **DECIDED / IMPLEMENTATION DEFERRED**

## 1. 決定

VERITAS は、**governing action / deployment policy が、その external effect に対して authoritative reconciliation を要求する場合に限り**、authoritative downstream reconciliation capability を execution-target eligibility の前提条件として扱う。

これは、すべての target に対する一律要件ではない。

決定は次の通り。

> **Policy が authoritative reconciliation を要求する場合、external effect に進む前に、その target は current かつ independently anchored な reconciliation-capability evidence を提示しなければならない。**

この前提条件を満たし得る capability class は次の2つ。

- `AUTHORITATIVE_QUERY`
- `AUTHORITATIVE_EVIDENCE`

次の2つは満たさない。

- `HEURISTIC_ONLY`
- `UNAVAILABLE_OR_UNVERIFIED`

この文書は、将来の execution contract の意図を固定する。Runtime への wiring はまだ行わない。

## 2. この決定が必要な理由

VERITAS は既に、ambiguous な dispatch outcome を `EFFECT_UNKNOWN` として扱い、blind redispatch を禁止している。

しかしこのモデルを安全に閉じるには、downstream system または別の accepted authoritative evidence source が、後から exact attempt に対して何が起きたかを回答できる必要がある。

その capability が無い場合、VERITAS は uncertainty を保持することはできても、external truth を作り出すことはできない。

したがって reconciliation capability は post-effect の問題だけではない。Policy が選択した external effect については、その target を automated execution に使ってよいかを決める execution eligibility の一部になる。

## 3. Policy scope

将来の enforcement は globally hard-coded ではなく、policy-selected でなければならない。

Policy は、例えば次の effect に authoritative reconciliation を要求できる。

- high-impact / high-risk な external action
- duplicate execution が material harm を生み得る action
- reversal が困難または不可能な action
- unresolved `EFFECT_UNKNOWN` が許容できない operational risk を生む action
- deployment policy が明示的に authoritative reconciliation required と指定した action

この文書は、新しい risk taxonomy を導入せず、既存の action class も再定義しない。

Policy source は deployment-controlled でなければならない。Request や AI output が requirement を downgrade できてはならない。

## 4. 前提条件を満たすための条件

Authoritative reconciliation が required の場合、evidence は次のすべてを満たした場合のみ admissible とする。

1. capability class が `AUTHORITATIVE_QUERY` または `AUTHORITATIVE_EVIDENCE`
2. 当該 class の既存 structural semantics を満たす
3. endpoint identity が assessment 時と一致する
4. target configuration が assessment 時と一致する
5. evidence が expired でも future-dated でもない
6. verifier identity / policy binding が independently supplied trust anchor と一致する
7. expected evidence digest がある場合、presented artifact と一致する
8. evidence 自体は non-authorizing のままである

この decision より前に追加された machine-readable evidence と negative-proof validator は、将来の gate に入る evidence input であり、permission object ではない。

## 5. 前提条件を満たさない capability

Policy が authoritative reconciliation を要求する場合:

- `HEURISTIC_ONLY` は eligibility prerequisite を満たさない
- `UNAVAILABLE_OR_UNVERIFIED` は eligibility prerequisite を満たさない
- evidence missing は fail
- stale evidence は fail
- target binding drift は fail
- caller-declared verifier identity は deployment-controlled trust anchor の代替にならない

Heuristic signal は investigation の補助に使えても、authoritative reconciliation capability に昇格させてはならない。

## 6. Enforcement placement

将来の enforcement point は、**authorization consumption より前、かつ transport 開始より前**とする。

想定 sequence は次の通り。

```text
ExecutionIntent
-> policy determines whether authoritative reconciliation is required
-> current reconciliation-capability evidence is verified
-> current target/configuration/verifier bindings are rechecked
-> if required capability is absent or invalid: fail closed
-> native authorization consumption
-> durable attempt ownership
-> transport
-> EFFECT_UNKNOWN when outcome is ambiguous
-> independent reconciliation
-> retrospective receipt/outcome
```

Capability check 自体が authorization を consume してはならない。

したがって failed capability check は、consumed authorization、network attempt、retry permission、terminal effect claim のいずれも作らない。

## 7. Binding と drift

将来の enforcing design では、別 target や materially changed target configuration が以前の assessment を暗黙に引き継げないよう、accepted capability state を十分強く bind しなければならない。

少なくとも次を bind または recheck する。

- reconciliation-capability evidence digest
- endpoint identity binding digest
- target configuration digest
- required capability class / policy requirement
- verifier identity と verifier policy identity/hash
- assessment freshness

Effect 前に required binding が変わった場合は fail closed とし、current policy の下で新しい admissible capability assessment を要求する。

この文書は、dispatch 直前に reconciliation endpoint へ live network probe することを要求しない。Structural capability / current trust binding と transient service availability は別概念である。

## 8. Temporary outage と absent capability

Target は authoritative reconciliation capability を持っていても、その read path が一時的に unavailable になることがある。

したがって:

- dispatch 後の temporary lookup outage は、original target を retroactively ineligible にしない
- effect は `EFFECT_UNKNOWN` のまま
- automatic redispatch は禁止のまま
- authoritative path が復旧すれば reconciliation を再開できる

一方、accepted authoritative reconciliation path を最初から持たない target は、その capability を required とする policy を満たせない。

## 9. Dispatch 後に capability が失われた場合

Attempt dispatch 後に authoritative reconciliation surface が消失、unavailable、または trust を失った場合:

- `CONFIRMED_NO_EFFECT` に変換しない
- heuristic から success を推論しない
- absence から failure を推論しない
- automatic retry を許可しない
- `EFFECT_UNKNOWN` を保持する
- 別の authoritative evidence path または governed human investigation へ escalate する

Human involvement は evidence collection の調整には使える。Human assertion 単独は、governing reconciliation contract がその evidence form を明示的に受理し検証しない限り、external-effect proof にはならない。

## 10. Frozen controlled proof との関係

既存の frozen controlled Decision-to-Effect proof は変更しない。

現在の proof は既に、次を持つ controlled target を証明している。

- caller-controlled pre-dispatch correlation identity
- durable downstream persistence
- independent read-only lookup
- lookup outage 中の `EFFECT_UNKNOWN` 保持
- blind redispatch 禁止

この decision はその proof を書き換えない。

将来の enforcing PR では、それが frozen contract の extension なのか、新しい proof version なのか、policy-gated execution profile なのかを明示しなければならない。既存 claim を暗黙に拡張してはならない。

## 11. Runtime enforcement 前に必要な proof

この decision を execution に wire する前に、少なくとも次を focused proof する。

1. policy requires authoritative reconciliation + current `AUTHORITATIVE_QUERY` -> prerequisite pass
2. policy requires authoritative reconciliation + current `AUTHORITATIVE_EVIDENCE` -> prerequisite pass
3. required + `HEURISTIC_ONLY` -> consumption 前に fail
4. required + `UNAVAILABLE_OR_UNVERIFIED` -> consumption 前に fail
5. required evidence missing -> consumption 前に fail
6. expired evidence -> consumption 前に fail
7. endpoint identity drift -> consumption 前に fail
8. target configuration drift -> consumption 前に fail
9. verifier/policy trust-anchor mismatch -> consumption 前に fail
10. capability evidence digest mismatch -> consumption 前に fail
11. policy が capability を required としない -> existing execution contract は unchanged
12. post-dispatch reconciliation outage -> `EFFECT_UNKNOWN` 保持、redispatch なし
13. failed eligibility check -> authorization unconsumed、network unused

## 12. Non-claims

この decision は次を主張しない。

- every external API が reconcilable
- idempotency key だけで十分
- authoritative reconciliation が exactly-once delivery を保証する
- runtime enforcement が既に存在する
- all external actions がこの prerequisite を必須とする
- dispatch 前に transient lookup availability の synchronous probe が必要
- production readiness
- regulatory approval

## 13. Implementation boundary

Implementation は別PRへ意図的に defer する。

そのPRでは次を満たす必要がある。

- explicit deployment-controlled policy input を導入
- existing reconciliation-capability evidence を narrowly scoped gate で利用
- current-target / trust / freshness recheck を実施
- prerequisite 不成立時、authorization consumption と transport の前に fail
- existing `EFFECT_UNKNOWN`, retry, replacement, reconciliation, recovery semantics を保持
- 上記 proof case を追加
- resulting controlled-proof version/profile を文書化

## 14. Resulting principle

Architecture decision は次の通り。

> **Policy が authoritative reconciliation を要求する external effect では、reconciliation capability は execution-target eligibility の一部である。**

Fail-closed consequence は次の通り。

> **Required capability を current target について authoritatively establish できない場合、VERITAS は external effect に進んではならない。**
