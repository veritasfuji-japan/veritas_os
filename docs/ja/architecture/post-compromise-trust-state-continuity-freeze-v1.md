# Post-Compromise Trust-State Continuity Freeze v1

Status: **FROZEN PREREGISTRATION SCOPE**

Machine-readable contract:
[`docs/architecture/post-compromise-trust-state-continuity-freeze-v1.json`](../../architecture/post-compromise-trust-state-continuity-freeze-v1.json)

## 1. 目的

この文書は、Product semanticsを変更する前にTASK-031をpreregisterします。

検証する問いは限定的です。

> compromiseまたはrollback後にhistorical operational stateを復元したとき、historical execution authority、revoked credential、revoked authority、stale Human Approval、stale trust assumptionを暗黙に復活させずに済むか。

これはproduction disaster recoveryの主張ではありません。
bounded proof contractです。

## 2. Core invariants

次をproofで維持します。

```text
Operational rollback != Trust rollback
Historical State != Current Authority
Recovered service health != Execution permission
```

historical snapshotはlineage evidenceとして使えます。

しかし、それだけでcurrent credential validity、current authority、current approval validity、current policy admissibility、current authorization usabilityを証明してはいけません。

## 3. Recovery-state model

初期proofではoperational recoveryとtrust validityを分けます。

```text
OPERATIONALLY_RECOVERED / TRUST_NOT_REVALIDATED
OPERATIONALLY_RECOVERED / TRUST_REVALIDATING
OPERATIONALLY_RECOVERED / TRUST_REVALIDATED
OPERATIONALLY_RECOVERED / TRUST_INVALID
```

新しいexecution pathの候補になれるのは`TRUST_REVALIDATED`だけです。

operational healthだけでは不十分です。

## 4. Trust generation / recovery epoch

proofでは明示的なmonotonic trust generationまたはrecovery epochを使用できます。

例:

```text
snapshot trust_generation = 41
current trust_generation  = 42
```

snapshotを復元しただけでgeneration 41のauthorization、approval、credential bindingがgeneration 42のexecution permissionになってはいけません。

productionの最終実装方式はまだfreezeしません。
freezeするのはsafety propertyです。

## 5. 実行前に必要なcurrent-state observation

post-recoveryで新しいexecution permissionを成立させる前に、次をfreshに確立します。

1. current authority / revocation state
2. current credential-provider state
3. current credential scope / endpoint binding
4. current policy state
5. 必要な場合のcurrent Human Approval validity
6. current execution-intent / action binding
7. authorization identity / consumption state
8. `EFFECT_UNKNOWN`を含むunresolved external-effect state

必要なcurrent observationがunavailable、ambiguous、stale、conflictingならfail closedします。

## 6. Frozen initial scenario corpus

初期proof corpusは次の10ケースです。

1. **rollback後もtrust不変**  
   historical stateを戻してもfresh revalidationは必須。

2. **snapshot後にcredential revoke**  
   snapshotではvalidでもcurrent providerでrevokedなら拒否。

3. **snapshot後にauthority revoke**  
   historical authorityがvalidでもcurrent authority sourceが拒否すれば拒否。

4. **snapshot後にHuman Approval失効 / 無効化**  
   historical approvalをそのまま使わない。Action Contractに従い拒否またはfresh approvalを要求。

5. **snapshot後にcredential version変更**  
   historical materialをrestore / reuseせず、current providerから再resolution。

6. **trust-generation mismatch**  
   historical authorization / approval bindingは新generationでは実行不可。

7. **current trust evidenceが取得不能 / ambiguous**  
   fail closed。

8. **snapshot後にpolicy変更**  
   historical admissibilityではなくcurrent policyを優先。

9. **recovery後のhistorical authorization replay**  
   consumed / stale authorizationは再利用不可。

10. **recovery後のfresh requalification**  
    current authority、policy、approval、credential、action contextがすべて成立した場合のみ、新しいauthorizationを発行可能。

## 7. External-effect continuity

既存のno-blind-retry ruleを維持します。

pre-recovery actionが未解決なら:

```text
EFFECT_UNKNOWN
```

rollbackによってfailure扱いに変えてはいけません。
redispatch authorityも発生しません。

external outcomeを断定する前にread-only reconciliationが必要です。

## 8. Evidence requirements

各scored runは少なくとも次を保存します。

- exact tested source SHA
- protocol / corpus version
- snapshot identity
- historical / current trust generation
- authority / revocation observation
- credential ref / non-secret resolution evidence
- policy / approval state
- authorization identity / consumption state
- recovery classification
- allow / block reason code
- runtime-record hashes
- 使用したreconciliation evidence

runtime pathはexecution前にoffline expected labelを受け取ってはいけません。

## 9. TASK-029との関係

TASK-029はrevocationがauthorization consumption / execution commitmentに対してどこでlinearizeするかを扱います。

TASK-031はhistorical rollback / post-compromise recoveryをまたいでcurrent trustが維持されるかを扱います。

関連しますが同じtaskではありません。

## 10. 再利用可能な既存primitive

現在のrepositoryには次が既に存在します。

- fresh governance rechecks
- PostgreSQL single-use consumption
- credential resolution
- endpoint / scope binding
- durable external-effect state
- `EFFECT_UNKNOWN`
- read-only reconciliation
- crash recovery

これらを再利用しても、強いpost-compromise trust-state claimが既に証明済みという意味ではありません。

## 11. Explicit non-claims

bounded proofがPASSしても次は証明しません。

- production disaster-recovery readiness
- universal incident-response correctness
- production IAM / KMS / HSM trust
- independent ultimate trust-root legitimacy
- production customer credential-lifecycle correctness
- HA / DR / SLA compliance
- third-party certification
- regulatory approval

## 12. Implementation gate

このpreregistration scopeがmergeされる前にTASK-031向けProduct semanticsを変更しません。

merge後は、frozen corpusを実行してinvariantをproveまたはfalsifyするために必要な最小実装だけを追加します。
