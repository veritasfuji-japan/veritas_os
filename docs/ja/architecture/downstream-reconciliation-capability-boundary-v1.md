# Downstream Reconciliation Capability Boundary v1

Status: **DESIGN-FIXED / NON-ENFORCING**

## 1. 目的

VERITAS は、曖昧な外部作用を `EFFECT_UNKNOWN` として扱い、terminal な effect claim を受け入れる前に、独立して検証された reconciliation を要求する。

この文書では、さらに次の境界を明示する。

> 曖昧な外部作用を reconciliation できるかどうかは、VERITAS だけではなく、実行先となる downstream system 側の性質にも依存する。

Downstream system が、caller 側で事前に選んだ durable な correlation key、単一の execution attempt を後から問い合わせられる記録、または別の authoritative observation surface を提供しない場合がある。VERITAS は、その不足を heuristic matching で暗黙に代替してはならない。

この文書は意図的に non-enforcing である。Frozen controlled Decision-to-Effect proof、authorization semantics、retry semantics、または confirmed external effect の現在の定義を変更しない。

## 2. Core invariant

境界は次の通りである。

`missing authoritative reconciliation capability != proof of no effect`

したがって、次を守る。

- query result が存在しないことは、何も起きなかった証拠ではない。
- query API が存在しないことは、何も起きなかった証拠ではない。
- timestamp、amount、payload similarity、log proximity、operator intuition は、それ単独では authoritative effect evidence ではない。
- 何が起きたか判定できないことは、retry permission を生成しない。
- configured reconciliation verifier が受理できる evidence により terminal claim を支えられない限り、`EFFECT_UNKNOWN` は unresolved のまま維持する。

既存 invariant は変わらない。

`EFFECT_UNKNOWN -> verified reconciliation -> {CONFIRMED_EFFECT | CONFIRMED_NO_EFFECT | EFFECT_UNKNOWN}`

## 3. Capability classes

この文書では downstream reconciliation capability を記述するため、4つの descriptive class を定義する。v1 では architecture vocabulary であり、runtime policy input ではない。

### 3.1 `AUTHORITATIVE_QUERY`

Downstream system が、単一の execution attempt に対する exact read-only lookup を提供する。

強い例では、少なくとも次を満たす。

- correlation identity が dispatch 前に決まっている。
- その identity が exact VERITAS operation / authorization / consumption lineage に binding されている。
- downstream system が、その identity を attempted effect とともに durable に保存する。
- read-only lookup で、その exact identity の record を取得できる。
- 返された observation を configured verifier policy の下で独立検証できる。

Caller-generated idempotency key と authoritative status / operation lookup の組み合わせは、一つの実現例である。ただし、downstream system が後から exact attempt の結果を回答できないなら、key だけでは十分ではない。

### 3.2 `AUTHORITATIVE_EVIDENCE`

Downstream system に exact query API はないが、別の authoritative observation surface によって effect state を証明できる。

例として、signed receipt、独立検証可能な event record、immutable ledger entry などが考えられる。

Evidence は exact operation lineage に binding され、`EFFECT_UNKNOWN` を terminalize する前に configured `ReconciliationEvidenceVerifier` を通過しなければならない。

### 3.3 `HEURISTIC_ONLY`

Downstream system と approximate にしか correlation できない場合。

例:

- timestamp window
- amount / value matching
- payload similarity
- nearby log entries
- fuzzy operator search

これらは investigation を補助できるが、それ単独で `CONFIRMED_EFFECT` または `CONFIRMED_NO_EFFECT` を生成してはならない。

### 3.4 `UNAVAILABLE_OR_UNVERIFIED`

Authoritative reconciliation surface が存在しない、またはその capability を依存可能な強度で検証できていない状態。

Execution attempt が ambiguous になった場合、state は `EFFECT_UNKNOWN` のまま維持する。Blind redispatch は引き続き禁止する。

## 4. Authoritative reconciliation path に必要な性質

VERITAS が downstream reconciliation path を authoritative として扱う将来実装では、少なくとも次を確立できる必要がある。

1. **Pre-dispatch identity** — transport 開始前に correlation identity が存在する。
2. **Exact lineage binding** — observation が verifier policy の要求に従い、exact operation、authorization、consumption、execution intent に binding される。
3. **Downstream durability** — original response を失った後でも、target または independent evidence source が結果確認に必要な state を保持する。
4. **Read-only verification** — reconciliation は external effect を再送しない。
5. **Verifier-controlled trust** — caller-declared success / failure を独立検証なしに信頼しない。
6. **Deterministic terminalization** — verified evidence のみが unresolved state を terminal effect state に移行できる。

## 5. `EFFECT_UNKNOWN` との関係

この境界は新しい effect state を追加しない。

既存 state はそのままである。

- `IN_FLIGHT`
- `EFFECT_UNKNOWN`
- `CONFIRMED_EFFECT`
- `CONFIRMED_NO_EFFECT`

新しい区別は、選択された target が ambiguity 発生時に `EFFECT_UNKNOWN` を trustworthy に解消する path を持つかどうかである。

その path が存在しない、または不十分なら、

`EFFECT_UNKNOWN -> EFFECT_UNKNOWN`

のまま維持する。

Workflow を terminal にするために certainty を作り出してはならない。

## 6. Retry / replacement behavior

Reconciliation capability が欠けていることは、blind redispatch を許可しない。

External effect が発生した可能性があり、authoritative に解決できない場合:

- original authorization は consumed のまま維持する。
- unresolved effect は `EFFECT_UNKNOWN` のまま維持する。
- same business event は既存の unresolved-event block の対象であり続ける。
- replacement authorization で uncertainty を回避してはならない。
- recovery は investigation へ escalation できるが、investigation 自体は configured verifier が受理する evidence を生成しない限り effect evidence にはならない。

Human involvement は recovery の調整や evidence 取得を行える。ただし human assertion 単独では、governing contract がその evidence form を明示的に受理・検証しない限り、external effect を遡及的に証明しない。

## 7. Execution eligibility への含意

Reconciliation capability は、とくに high-risk external effect において、execution-target eligibility の一部になり得る。

将来の enforcing design では、execution authority の consumption 前、または transport 開始前に、target が accepted reconciliation capability を示すことを要求する可能性がある。

ただし、この文書では**実装しない**。

その precondition を追加することは controlled execution contract の変更に該当するため、explicit architecture decision、focused tests、proof update、human approval が必要である。Incidental refactor や documentation-only semantic change として導入してはならない。

## 8. Controlled proof との関係

Frozen controlled Decision-to-Effect proof はすでに、次の性質を持つ target を扱っている。

- caller-controlled idempotency / correlation identity
- durable downstream persistence
- independent read-only lookup path
- lookup outage 中の `EFFECT_UNKNOWN` 維持
- no blind redispatch
- terminal receipt / outcome evidence 前の verified reconciliation

この文書は、その proof claim を arbitrary enterprise endpoint へ広げない。

むしろ、controlled proof を「何が起きたかを authoritative に回答できない target」へ自動的に一般化できない理由を明示する。

## 9. 将来追加する場合の proof cases

この境界を将来 executable policy にする場合、少なくとも次の focused proof case を持つべきである。

1. exact authoritative query -> verified terminal reconciliation
2. temporary lookup outage -> `EFFECT_UNKNOWN` 維持
3. heuristic-only correlation -> `EFFECT_UNKNOWN` 維持
4. no reconciliation capability -> `EFFECT_UNKNOWN` 維持 + no redispatch
5. stale / changed capability evidence -> 依存前に fail closed
6. verifier proof のない caller-declared terminal result -> reject
7. original business event unresolved 中の replacement authorization -> existing replacement-blocking semantics により reject

## 10. Non-claims

この文書は次を主張しない。

- すべての external API が安全に reconcilable であること
- idempotency key 単独で external effect state を証明できること
- external provider による exactly-once delivery
- production readiness
- heuristic correlation が authoritative evidence であること
- human review が unavailable external truth を復元できること
- current frozen proof が non-reconcilable target に拡張されたこと

## 11. Design principle

この境界から得られる原則は次の通りである。

> **Reconciliation capability is a property of the execution target and may constrain execution eligibility.**

そして fail-closed consequence は次の通りである。

> **VERITAS が authoritative に「何が起きたか」を判定できない場合、certainty や retry permission を作り出さず、uncertainty を維持しなければならない。**
