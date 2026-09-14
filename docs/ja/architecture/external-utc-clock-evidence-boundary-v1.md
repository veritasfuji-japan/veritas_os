# External UTC Clock Evidence Boundary v1

## ステータス

設計固定済みの非実行 trust boundary。

この文書は、VERITAS における external UTC clock trust の最初の
production-hardening 境界を定義します。現時点で独立した本番UTC時刻を
信頼できる状態になった、という主張ではありません。

## 問題

現在の controlled Decision-to-Effect proof では、clock callback を trusted
deployment input として受け取ります。これは frozen sandbox proof には十分ですが、
別の future claim である **external UTC clock trust** は証明していません。

本番グレードでは少なくとも次を説明できる必要があります。

- どの外部clock sourceを信頼したか
- どのverifierがprovider artifactを認証したか
- どのtrust policyがprovider/verifierの組を許可したか
- 返された時刻が古いsampleのreplayではなくfresh requestにbindされているか
- providerがどのuncertainty boundを主張したか
- monotonic round-trip timeがどれだけだったか
- serialized outputをportable runtime trustへ変えずに監査・再生できるか

## 境界

対象フローは以下です。

```text
caller-created freshness challenge
        ↓
external time provider artifact
        ↓
provider-specific authentication / normalization
        ↓
VERITAS-controlled provider + verifier allowlist
        ↓
challenge binding + uncertainty + monotonic RTT checks
        ↓
runtime-sealed VerifiedExternalClockEvidence
```

結果は**時刻に関するevidenceのみ**です。

```text
VerifiedExternalClockEvidence
!= AuthorityEvidence
!= HumanApproval
!= BindAuthorization
!= execution permission
!= runtime clock replacement
```

## Freshness model

v1では、外部UTC evidenceのfreshness確認にlocal wall clockを使ってはいけません。
それを行うと、検証対象の時刻を使って時刻自身を検証する循環になります。

代わりにchallenge bindingを使います。

1. callerがhigh-entropy nonceとchallenge identifierを作る
2. challengeをmonotonic start valueとともにcurrent processへ登録する
3. provider-specific verifierがchallengeをbindしたnative artifactを認証する
4. normalized evidenceがchallenge identifierとnonce hashを保持する
5. VERITASが登録済みchallengeと比較する
6. monotonic elapsed timeをconfigured maximum RTTと比較する
7. 成功したchallengeはこのboundaryではsingle-useとする

monotonic timingが証明するのはbounded local elapsed timeだけです。
UTCそのものの正しさはprovider evidence側で証明される必要があります。

## Normalized evidence contract

最初の実装では最低限、次をnormalizeします。

- `evidence_id`
- `provider_id`
- `artifact_id`
- `artifact_type`
- `artifact_version`
- `payload_hash`
- `challenge_id`
- `challenge_nonce_hash`
- `utc_time`
- `uncertainty_ms`
- `source_clock_id`
- `provenance`
- `metadata`

`utc_time`はtimezone-awareなUTCである必要があります。
`uncertainty_ms`は0以上の整数でなければなりません。

## Independent trust policy

provider artifact自身が自分のtrust statusを決めてはいけません。

VERITAS deployment policyが独立して以下をbindします。

- provider identifier
- verifier identifier
- verifier trust level
- verifier policy identifier
- verifier policy hash
- maximum accepted uncertainty
- maximum accepted monotonic round-trip time

これらのいずれかを変更した場合、deterministic trust-policy identityも変わります。

## Provider-specific verifier seam

provider adapterはnative authenticationとnormalizationを担当します。
generic boundaryへ返すresultには最低限、以下を含めます。

- verification success/failure
- normalized clock evidence
- verifier identity
- verifier trust level
- verifier policy identity/hash
- 必要な場合のsigning key identity / algorithm metadata
- semantic consistency result
- sanitized reason

generic boundaryは、unapproved、incomplete、inconsistent、または独立policyを
超えるresultをfail closedで拒否します。

## Runtime seal

成功したverificationはin-memory sealed proofを生成します。

- normalized evidence + deterministic evidence hash
- verifier binding
- trust-policy identity/hash
- challenge identity/hash
- measured monotonic round-trip duration
- verification source/reason
- deterministic proof hash

serialized JSONはaudit outputに限定します。後からdeserializeして、そのまま
trusted runtime stateとして再解釈してはいけません。

## 必須 fail-closed cases

focused testは最低限、以下を含めます。

- provider verification failure
- semantic inconsistency
- unapproved provider/verifier
- verifier-policy binding mismatch
- 必須の場合のsignature identity metadata欠落
- malformed payload hash
- missing/invalid challenge
- challenge identifier mismatch
- challenge nonce mismatch
- challenge replay
- non-UTCまたはtimezone-naive time
- invalid/excessive uncertainty
- negative/excessive monotonic RTT
- proof作成後のtrust-policy変更
- callerによるverified proofの改変/偽造

## Frozen Decision-to-Effect architectureとの関係

このboundaryはfrozen controlled execution proofから意図的に分離します。

v1では以下を変更しません。

- authorization issuance / consumption semantics
- current governance rechecks
- credential resolution
- Bind dispatch
- `EFFECT_UNKNOWN`
- reconciliation
- BindReceipt / Outcome semantics
- existing trusted clock callbacks
- external-effect path

standalone clock evidence boundaryがdeterministic testとsource-bound proofを持つ前に、
frozen execution pathへcompositionしてはいけません。

## Non-claims

この仕様は以下を証明しません。

- production external UTC clock trust
- live provider interoperability
- independent infrastructure ownership
- customer deployment
- regulatory / certification status
- exactly-once TrustLog publication

## Implementation PR exit gate

implementation PRは以下を満たした時点でmerge候補になります。

1. provider-neutral boundaryがstandalone moduleとして存在する
2. focused fail-closed testsがpassする
3. frozen execution semanticsを変更しない
4. network dispatchを追加しない
5. runtime clockを置き換えない
6. proof objectがevidence-onlyのままである
7. repository CIがgreenである
