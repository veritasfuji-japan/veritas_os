# Native v2 sandboxイベント連携仕様 v1

状態: 人間レビュー用の実装提案。実行処理の実装済み宣言・デプロイ許可ではありません。
基準: `33460417782b3659a32a1ecfbc20714edc5943bc`（#2197マージ後）。
英語版: [English](../../en/architecture/native-v2-sandbox-event-spec-v1.md)。

## 1. 目的と境界

native v2経路から、専用sandboxへ合成イベント1件を永続登録することを実証します。
外部作用はsandboxのイベント行の挿入です。Receipt作成やHTTP応答だけではありません。
本番API・送金・顧客データ・汎用adapter frameworkは対象外です。本書は将来の仕様で、
credential resolution・native v2 Bind・reconciliationの実装完了を主張しません。

照合した既存コード:

- `veritas_os/policy/native_bind_authorization.py`: 認可の発行・検証。
- `veritas_os/policy/native_bind_authorization_consumption.py`: 現在の再確認と永続的な単回消費。
  返り値は監査証跡であり、実行権限として再利用できません。
- `veritas_os/policy/webhook_bind_adapter.py`: 参照HTTP adapter。既存のHMACと算出式による
  idempotency keyは、本仕様のnative v2プロトコルに自動適合しません。
  再利用時は互換性を明示確認し、認可のkeyを勝手に置換しません。

## 2. 操作と同一性

| 項目 | 固定する提案 |
| --- | --- |
| Action | `sandbox.event.register.v1` |
| 作用要求 | デプロイ設定で固定した1つのHTTPS originの `POST /v1/events` |
| Body | `event_id`（UUID文字列）と `message`（合成UTF-8文字列、1〜256バイト）のみ。余分な項目を拒否 |
| 要求上限 | 4 KiB。JSONの重複key・JSON以外の値を拒否 |
| 照合 | `GET /v1/operations/{operation_id}`。応答喪失時は元のidempotency keyでも照会可能にする |
| 通信 | TLS相手検証必須。リダイレクト・POSTの自動再試行は禁止 |
| タイムアウト | 1要求の総時間5秒。期限超過は作用がなかった証明ではない |

発行前にmethod・正確なorigin/path・canonical payload digest・event ID・契約digest・
credential ref/version/scope・endpoint identity・認可のidempotency keyを対象操作へ
結び付けます。既存のcanonical JSON/hash契約を使用し、送信時に別の直列化へ切り替えません。
payload bindingが不足する場合は秘密情報取得より先に実装します。変更可能なadapter設定から
keyを再生成しません。照合先も同じoriginと検証済み識別子に限定し、応答内の任意URLを使いません。

## 3. 信頼源とcredential

運用者が、信頼するissuer鍵・ActionClassContract・source registry・endpoint identity・
credential metadataをpacketと独立に供給し、レビューされた設定変更で版管理・失効を扱います。
同一ID/versionでもembedded snapshotを代用しません。人間承認が必要なら実際の権限ある
承認Receiptを検証し、生成・推測しません。sandbox管理者、credential provider、ホスト時刻基盤、
registry管理者を明示的な信頼主体とします。これらの主体の侵害は最初の実証の保証範囲外です。

credential modelは、provider管理の版付きsandbox bearer tokenをTLSで使用する方式に限定します。
executorは認可されたrefだけを解決し、固定sandboxのイベント登録・operation照合に権限を限定します。
reconciliationは同じtoken方式の別の読み取り専用principalを使います。呼出元から秘密値や任意refを受けません。
providerで認証されたaudience・scope・version・expiry・revocation情報を利用前に確認します。
metadata不足・providerエラー時は停止し、広い権限の環境変数tokenへfallbackしません。
ローテーションはbinding変更として再認可します。秘密値は試行中のメモリだけで扱い、使用後は参照を破棄します。
Pythonメモリの完全消去は主張しません。ログ・Receiptにはrefとmetadata digestだけを残し、token・header・
秘密情報を含む例外を記録しません。

実際のHTTPS origin・hosting・provider・token ref・principal・鍵fingerprintは未確定の配備条件です。
本書で架空の値を設定しません。入力認証で確認できるのは由来・完全性であり、外部状態の真実性とは別です。

## 4. 時刻と変更条件

executor側のUTC時刻とmonotonic timerを使用し、要求側の検証時刻は信用しません。
sandbox用の提案値は、時刻健全性の観測が30秒以内、申告された不確かさが1秒以下、
最終再確認から送信まで1秒以下です。健全性情報不足・壁時計巻き戻り検出・上限超過では送信を止めます。
時刻の不確かさ区間全体が有効期間内にある場合だけ有効とし、失効後の猶予は設けません。
monotonic timerは経過時間用でありUTCの正当性を証明しません。これらの値は有効化前に配備環境で検証します。

payload/event ID・宛先・credential metadata・契約内容・authority・approval・失効状態の変更は
継続を無効にし、再評価を必要とします。最初の実証では汎用的なmateriality閾値を追加しません。
新しいrisk reviewの時刻/hashは変わり得ますが、既存verifierで同じ正確な操作へのbindingとPASSを
確認する必要があります。risk条件の変更を無害として無視しません。

## 5. 消費から実行直前まで

1. 既存native v2と外部の信頼入力で発行時・現在のgovernanceを検証し、PostgreSQLで単回消費します。
2. 信頼する永続ストアから消費行を取得し、認可と対象操作の完全な同一性を確認します。
   呼出元の `authorization_consumed=true` 宣言では代用しません。
3. 消費identityごとに実行試行の排他的な担当取得を永続化します。別workerによる重複取得を拒否します。
   旧workerと交代workerが並行送信できる期限付きleaseは使用しません。
4. credential material取得前に契約・endpoint・credential metadata・authority・人間承認・失効・riskを
   再確認し、そのrefだけを解決します。処理が挟まった場合は送信直前にfreshness/governanceを再確認し、
   bindingや有効性が変わっていれば停止します。
5. 要求がexecutorを出る前に送信意図を永続化し、その試行と元のkeyで1回送ります。
   DB commitが不明なら、信頼するストアで担当取得状態を確定できるまで送信しません。

消費結果だけではBindを許可しません。クラッシュ後は永続的な試行記録を使って復旧します。
担当不明・送信済みの可能性がある場合は再取得・再送ではなく照合します。
イベントが発生しなくても認可消費は取り消しません。ローカル再確認で外部のpolicy/失効状態を
原子的に固定することはできません。時間差の上限と残る競合リスクをE2E証拠に記録し、解消済みと表現しません。

## 6. sandboxの永続性と重複処理

sandbox DBの1トランザクションで元のidempotency keyとevent IDの一意性を保証し、イベント行と
operation記録・要求digestを保存します。commit後だけ成功応答を返します。
同一key・同一digestなら元のoperationを返し、同一key・異なるdigestは新しい作用なしのconflictです。
別keyによる同一event IDの再使用もconflictとします。同時要求でも行は1つです。
PoC中は重複防止記録を失効させず、未完了・不明の操作がある間はnamespaceをリセットしません。
許可された環境終了でも証拠を保持します。

応答にはoperation ID・元key・payload digest・永続状態を含めます。`201`は新規登録、`200`は
同じ登録の存在、`409`はconflictです。クライアントは照合前の応答を観測として扱います。
providerエラー・5xx・timeoutは作用なしの証明にしません。

## 7. Receipt・Outcome・照合

| 観測・状態 | 意味 |
| --- | --- |
| ローカル受付 | governance/試行を受理。外部成功ではない |
| 送信意図の永続化 | 送信された可能性がある。復旧時は照合から開始 |
| Dispatched | transportが送信を報告。永続登録の証明ではない |
| Externally acknowledged | 対応するoperationを示す有効な応答を受領 |
| Confirmed success | 読取専用照合で永続イベント・key・event ID・digestが一致 |
| 送信前失敗 | 要求未発行をローカルで証明。認可は消費済みのまま |
| Unknown | 要求・commit・Receipt状態が不明。無条件再送・成功推測は禁止 |

BindReceiptは観測した事実を記録し、認可・消費・試行・action digest・operation identityへ結び付けます。
Outcomeには独立した照会証拠を加えます。HTTP statusを成功確定へ置き換えません。
Receipt保存に失敗した場合、イベントが存在しても試行は未解決として照合を行います。
復旧書込みは冪等にし、以前の事実を書き換えず証拠を追加します。

別の読み取り専用process/principalでsandboxの永続operationを照会します。
送信応答からは独立していますが、sandbox運用者から独立した証明ではありません。
operation IDがなければ元keyで照会します。not-found・照会不能・digest不一致・未認証応答はunknownを維持します。
送信中の要求が後からcommitする可能性があるためです。v1では自動再送しません。
同じ業務イベントの結果がunknownの間は、代わりの認可による実行も止めます。
人間へのエスカレーションは調査のためであり、証拠なくunknownを失敗確定へ変えません。

## 8. 合格条件と実装順序

| 必須試験 | 合格証拠 |
| --- | --- |
| 承認必須／正当に承認不要 | 独立したpolicy検証。架空Receiptなし |
| 正常登録 | イベント1件、消費、試行、観測Receipt、一致する照合 |
| worker・要求の同時重複 | 永続担当1件・外部イベント1件 |
| 同一keyで異なるpayload／同一eventで異なるkey | conflict、2行目なし |
| 同一ID/version契約の承認不要への改ざん・source差替え | 秘密取得・送信前に拒否 |
| 失効・期限超過・drift・時計巻き戻り／健全性不明 | 停止。不正な送信なし |
| provider失敗・scope/audience/version不一致 | 秘密を露出せず停止 |
| 消費後／送信前クラッシュ | 消費再利用なし。永続状態を確認して復旧 |
| 作用commit後の応答喪失／Receipt保存失敗 | unknownから照合で確定。再送なし |
| 照合停止・遅延・記録不一致 | unknownを維持。結果を推測しない |

実装順は、配備契約とpayload binding → 実行直前・試行管理境界 → credential resolver →
sandbox native Bindと観測Receipt/Outcome → reconciliationと障害復旧 → 再現可能な正常・障害E2Eです。
全条件の成功後にfreezeし、commit・設定digest・証拠を保存します。
その後に大規模Consolidation Audit、benchmark再基準化、外部レビューを進めます。

## 9. 接続前に必要な決定

sandbox origin/TLS identityと管理者、credential provider/ref/scope、信頼registry・鍵管理、
時刻健全性の取得元と実測上限、DB永続性・保持条件・読取専用照合権限を記録します。
合成payloadと障害注入の範囲も確定します。これらは必須の配備入力です。
供給・レビューが済むまでは、作用のないテストによる実装準備に限定し、秘密取得・インフラ配備・外部要求を行いません。

## 10. 最初のmetadata binding実装

`veritas_os/policy/sandbox_action_binding.py`に、明示的に呼び出すローカル検証境界を設けます。
`build_sandbox_action_binding`は2文字列のpayloadと明示的な配備設定を検証し、
`sandbox-action:v1:sha256:`参照を返します。この参照をdecision記録・promotion・認可発行より前に、
候補の `evidence_refs` に正確に1つ含めます。POST・正確なendpoint・payload digest・契約全体のdigest・
credential metadataの固定値を含み、後から生成される認可digestとの循環依存は作りません。

`verify_sandbox_action_binding`は独立したsource/governance/trust入力でnative認可verifierを呼び、
参照を再構築して検証済みintent・endpoint・credential metadataに照合します。
元の認可のidempotency keyを維持します。不変の関連付け結果は実行許可ではなく、native検証の代用にもなりません。
既存のnative入口の経路は変更しません。将来のsandbox executorは、この境界に加えて消費・実行直前再確認を必須にします。

credential versionは発行前に結び付ける配備固定値です。providerに対するversion・expiry・revocationの
真正性確認はresolverの作業として残ります。本モジュールはTLS・時刻健全性・provider情報・payloadの真実性を
認証せず、実行担当取得・秘密情報取得・外部作用も実装しません。

## 11. 外部作用を伴わない試行準備

`prepare_sandbox_attempt`は永続化された消費レコードを読み、独立検証したnative認可とsourceから
全項目を再構築して照合します。既存の`bind_effect_states`を再利用し、消費・認可ごとに
一つの恒久的な`IN_FLIGHT`試行をPostgreSQLの一意制約で登録します。既存v1実行入口は変更しません。
プロセス内ストアは明示的なテスト指定が必要で、プロセス間の保証はありません。

登録のcommit後に、executor設定のcallbackから独立した現在のsource・契約・credential metadata・
権限・承認・runtime riskを取得し、native verifierで元の操作と照合します。
packet内snapshotを信頼源にしません。時刻・健全性callbackは信頼された配備入力です。
健全性確認から30秒以内、不確実性1秒以内、UTC・単調時計の両方で再検証所要時間1秒以内を要求し、
巻き戻りを拒否します。有効期間は不確実性の下限から保守的な2秒後の上限
（処理1秒＋最大不確実性1秒）まで検証するため、有効期限の余裕が短い場合も停止します。
ホスト時刻・健全性情報の真正性は配備上の信頼前提であり、この処理で証明するものではありません。

読取失敗・消費レコード欠落・照合不一致は登録前に停止します。登録応答の喪失や登録後の検証失敗では、
試行を解放せず、消費も取り消しません。放置された試行も別callerから再取得できません。
`IN_FLIGHT`は送信や成功を意味しません。結果を確定するにはクラッシュ復旧と独立照合が別途必要です。

返却値は監査情報のみです。credential取得・送信意図の永続化・Bind・外部リクエスト・
Human Approval作成・BindReceipt/Outcome生成は行いません。将来のexecutorは実際の送信境界で
試行所有を強制し、credential処理後に再検証する必要があります。1秒制限は強制条件であり、
測定済み性能保証ではありません。配備性能と信頼callbackの設定確認は引き続き必須です。

## 12. Credential解決の継続処理

`prepare_and_resolve_sandbox_credential`が試行準備自体を実行します。元の認可と独立した
deployment/source/governance入力を受け取り、callerのprepared結果やconsumedフラグは受け取りません。
既存の試行をこの入口から再開できません。標準では引き続きPostgreSQLが必須です。

信頼されたexecutorが一つの`SandboxCredentialProvider`を指定します。`describe`は秘密値を返さず、
`resolve`はproviderを認証し、期待するmetadata digestと現在の失効・versionを原子的に照合して、
そのmetadataに結び付いたmaterialを返す契約です。packetの`authenticated=true`は代用になりません。
ローカル処理はprovider信頼源の確立・vendor選択・環境変数tokenの読取・サービス接続を行いません。
provider/hosting設定と実providerでの試験は配備前の確認事項です。

検証済み操作のbindingからcredential参照・provider・version・完全一致するscope・environment・
HTTPS origin audienceを固定します。metadataにはbearer種別と非失効状態の明示が必要で、
有効期間は確認した時刻の不確実性区間全体を含む必要があります。欠落・形式不正・陳腐化・
同じ参照のversion変更・宛先違い・過大scope・期限切れ・provider障害は停止します。
provider呼び出しは各5秒でtimeoutし、再試行しません。継続処理全体でdescriptorの経過時間も5秒以内です。

metadata確認後の秘密値取得直前と、取得後の両方で試行レコード全体を読み直し、#2200の
現在条件の再検証を行います。検証失敗時はmaterialを返さず、試行・消費も解放しません。
既存verifierを再利用し、埋め込みsnapshotを信頼源へ戻しません。

materialは表示を伏せる`SecretBytes`で保持します。結果は汎用JSON・dataclass・pickleで
シリアライズできません。信頼されたコードが明示的に`material.get_secret_value()`を呼ぶとbytesへ
アクセスできます。`close()`は結果の参照を破棄しますが、Pythonのメモリ消去やprovider内部ログの
制御は保証しません。公開例外は固定コードのみで、provider例外のcontextを保持しません。
監査情報は準備結果とmetadata digestだけで、token自体やtokenのhashを含めません。

Authorization header・Bind・network dispatch・外部作用・Human Approval・BindReceipt・Outcomeは
作成しません。将来のsenderは使用時に所有・期限・現在条件を再検証し、送信意図を永続化する必要があります。
試験は合成credentialを使用します。限定的なホスト実時計での測定を13節に示します。
実providerの真正性と配備環境での性能は未実証です。

## 13. ホスト実時計での限定検証

再検証1秒、保守的な確認上限2秒、providerとdescriptorの5秒制限を維持します。
各公開verifierは独立したsource/contractを必須とし、全項目を再構築します。同じ呼び出し内では、
HARRが再構築したsourceをnative satisfactionへ返し、readinessと最終再検証は完全に再構築した
親packetの子要素を使用し、native risk検証は自身が再構築した最終sourceを保持します。
グローバル・呼び出し間の検証キャッシュや、callerのverifiedフラグによる省略はありません。
現在のpolicy・失効・署名・時間区間両端の再検証を維持します。JSONの組み込みscalar値では
不要なPydanticモデル判定を省きますが、各境界の正規化・時刻処理・不正値拒否は維持します。

明示実行する性能試験は実際の`datetime.now(timezone.utc)`と`time.monotonic()`、
本物のnative verifier、署名した合成artifactを使用し、測定区間内で新しいrisk証拠を生成します。
coverageやprofilingと同時に実行せず、次のコマンドで測定します。

```sh
VERITAS_RUN_SANDBOX_TIMING=1 python -m pytest veritas_os/tests/test_sandbox_real_clock.py -q -s --no-cov -o junit_family=xunit1 --junitxml=/tmp/sandbox-timing.xml
```

2026-09-07のPython 3.12開発ホストでは、正常3回の計9回の再検証が各0.603〜0.770秒、
credential継続処理全体が2.592〜2.749秒でした。fixture発行と消費の時間は全体測定に含めません。
descriptorの経過時間は1.287〜1.456秒で、既存の5秒制限以内でした。
source取得へ1.05秒、providerのdescribe/resolveへ5.05秒の遅延を入れると拒否され、
消費と試行を保持し、再試行しません。単一ホストの観測であり、スループットや配備性能の保証ではありません。
性能試験は各測定値を出力し、対象段階へ到達できない場合や正常処理が既存制限を超えた場合に失敗します。

このcheckpointの測定は明示指定のin-memory store、合成material/provider、
健全性と誤差ゼロを宣言した時計を使用しました。実provider・PostgreSQL遅延・認証された時刻源・
外部作用は測定していません。当時の誤差50ミリ秒のケースは、`checked.now`で記録する新しいrisk証拠が
検証に使う誤差下限より未来になるため、provider接続前に拒否されました。
この時間検証に限定した修正を14節で定義します。

## 14. 因果順序を示す観測時刻と独立した有効期間

executorは恒久的に所有する試行内で`checked.now`を取得し、その後に信頼された同期型の
current-input loaderを呼びます。再構築したrisk decisionの`reviewed_at`とpacketの`recorded_at`は、
両方ともこの時刻と厳密に一致する必要があります。これは今回の呼び出しの観測を示す時刻であり、
外部からの権限付与の有効開始時刻ではありません。risk/sourceは独立したsource/contract入力を
すべて必須として`checked.now`で再構築します。verifierによる証拠の過去への日付変更・再ハッシュや、
callerのverifiedフラグによる受け入れは行いません。

この規則はsandboxの所有呼び出し内に限定します。共通のnative/risk verifierは従来の厳密な
単一時刻の検証を維持し、指定された検証時刻より未来に記録されたpacketを拒否します。
全項目とhashを再構築しても、今回の観測時刻から1マイクロ秒ずれたrisk packetは拒否します。
時計誤差の範囲内にあることは再利用の許可ではありません。

Authorizationと署名付きAuthority/Approvalは、引き続き時計誤差の下限で検証します。
riskの期限・Authorization・governanceは、既存の保守的上限`checked.now + 2秒`でも
有効でなければなりません。処理時間はUTCとmonotonicの両方で1秒以内、完了時の時計は健全かつ
認可の有効期間内である必要があります。未来の署名付き権限・期限切れ・巻き戻り・過大な遅延は
引き続きfail-closedです。TTLの延長、時計誤差1秒・健全性確認の経過30秒・credential providerと
descriptorの5秒制限の緩和はしません。credential継続処理の両方の再検証にも同じ規則を適用し、
失敗時は消費と試行を保持します。

明示実行する実時計試験は、誤差ゼロと遅延拒否に加え、宣言誤差50ミリ秒・1秒の正常継続を必須にします。
決定的な試験では、再構築済みpacketの時刻差し替え、合成Ed25519署名付きAuthorityの有効期間境界、
credential取得後の検証失敗を確認します。これらは時計やproviderの真正性を認証する試験ではありません。
executor設定のloaderには本当に現在の入力を取得する責務があり、時刻一致と署名だけでは入力の真実性を
証明できません。配備環境の時計/provider検証、送信意図、Bind、外部作用、結果照合はこの修正の範囲外です。
credential継続処理の成功も、それらの実行許可にはなりません。

## 15. 再構築後の正規化の重複を削減

計測では、入れ子のpacket全体を繰り返しJSON正規化する処理が再検証時間の大きな割合を占めていました。
satisfaction・readiness・gate・fresh-source・final-recheckの5つのverifierは、入力の正規化、
スキーマ検証、独立した全項目の再構築を行った後、モデルの全Python出力を比較します。
この5つのbuilderが返す項目はJSON形式の値です。入力正規化、全項目の比較、hash、両方の時刻での
source再構築、署名・失効確認は維持します。小さいruntime-risk packetには日時型が含まれるため、
その正規化は従来どおりです。あらゆるモデルに共通の比較省略を導入するものではありません。

回帰試験は承認が必要・不要の両方を対象とし、正規化後の値とhashの一致、新しい戻り値オブジェクト、
不正な入れ子のdict/model入力、承認要件を改ざんしてhashを再計算するケースを確認します。

2026-09-08のPython 3.12開発ホストでは、最終実時計試験の8件が成功しました。
内訳は誤差ゼロの正常継続3回、誤差50ミリ秒・1秒の正常継続、遅延を入れた拒否3件です。
正常15回の再検証は0.529〜0.680秒、継続処理は2.184〜2.426秒、descriptorの経過時間は
1.103〜1.261秒でした。既存の時間制限をすべて適用しています。
以前のホストの1.4〜1.7秒の失敗が解消した理由を、すべてこの変更に帰すことはできません。
現在のホストでは最適化前の誤差ゼロの対照試験も成功し、再検証は0.622〜0.784秒でした。
これらはこのホストでの結果であり、全環境の遅延保証ではありません。
配備先では想定負荷の下で、時計・provider・データベースの設定を検証する必要があります。

## 16. 所有呼出し内のdispatch接続点（非通信試験のみ）

`execute_sandbox_bind`は準備とcredential解決を自身で実行し、呼出し側が渡した
解決済みcredentialや準備結果を認可として受け取りません。独立した現在のgovernanceと
所有権を再検証し、既存effect-stateのcompare-and-setで`EFFECT_UNKNOWN`とreason
`SANDBOX_DISPATCH_INTENT_PERSISTED_EFFECT_UNCONFIRMED`を永続化してからtransportへ
進みます。記録は消費済みauthorizationと元のidempotency keyに結び付き、authorizationが
action/payload bindingへ結び付きます。commit応答消失、CAS失敗、読戻し不一致では
transportを呼びません。状態・消費・専有attemptを解放、リセット、再試行しません。

最後の所有権読出し、governance再構築、intent書込み・読戻し、transport準備に共通の
UTC/monotonic 1秒上限を適用します。material受渡しcallbackでその上限、時計の健全性、
authorizationの有効区間、元のcredential descriptorの有効期限・経過時間を再検証します。
callbackは1回限りです。transport呼出し全体のtimeoutは5秒です。成功・失敗・キャンセルで
material参照をcloseしますが、Pythonメモリの消去は保証しません。

`SandboxDispatchTransport`は信頼されたexecutor設定から注入するインターフェースであり、
実HTTPS adapterではありません。唯一の送信の直前にcallbackを呼び、canonical payloadと
元のkeyを保持し、TLS検証とredirect・proxy・retry無効化を実装する必要があります。
不正な実装がmaterialを保持したり期限後に送信することを、このインターフェースだけで
防いだとは主張しません。外部作用を有効にする前に、具体的transportのレビューと実時計の
送信試験が必須です。デフォルトtransportやAPI routeは追加していません。

transport応答を権限や外部作用の証拠として解釈しません。返却する
`SandboxDispatchObservation`は常に`UNKNOWN`で、見かけ上のtransport成功でも永続状態は
`EFFECT_UNKNOWN`のままです。このローカル結果はBindReceipt・Outcome・外部acknowledgement
ではありません。キャンセルでは秘匿済み例外を返し、永続的な不確実状態を保持します。
復旧処理は元のidempotency keyで照合し、盲目的に再送してはいけません。

この工程は合成materialと非通信transportを実native verifierで試験するものです。
実HTTPS送信、PostgreSQLの遅延、sandbox側の永続性、正式Receipt/Outcome連携、reconciliationは
未検証・未完了です。これらは後続の必須工程であり、この試験で保証されたものではありません。
外部へ接続するには引き続き第9節の配備条件の確定が必要です。

## 17. 独立したsandbox eventサービス

`create_sandbox_event_service`は独立ASGIアプリを作成します。main APIへの組込みや
デフォルトapp・listenerはありません。ユーザーが承認し規約に明記した限定例外として、
このサービスはBearer認証、既存VERITAS APIは引き続きX-API-Key認証を使用します。
operatorが信頼された設定から、有効期限付きの別々のwriter（登録・参照）とreader
（参照のみ）tokenを渡します。tokenの生成、providerからの解決、環境変数へのfallback、
operationへの記録は行いません。設定欠落・不正は起動時に拒否し、未認証・期限切れの
リクエストはbody処理・DBアクセス前に拒否します。現在のrotationは新設定でappを再作成する
方式です。実credentialの配布・失効反映、TLS終端、ネットワーク制御は配備前の必須条件です。

operatorは専用psycopg async poolを渡し、sandbox専用DBに
`veritas_os/policy/sandbox_events.sql`を適用します。main API用migrationには追加しません。
同じ不変行がeventとoperationを表し、operation ID・元のkey・event IDに一意制約を設けます。
実行用DB principalはSELECT/INSERTのみ、独立reconcilerは読取りのみとしてください。
lookupのtransactionはread-onlyです。

`POST /v1/events`は固定JSON payloadと単一`Idempotency-Key`ヘッダーを受け取ります。
JSONキー重複、余分なfield、不正UUID・UTF-8、NUL、body・messageの上限超過は保存前に拒否します。
keyはASCII英数字・ピリオド・アンダースコア・コロン・ハイフンの1〜256文字です。
READ COMMITTED transaction内でINSERT ON CONFLICT DO NOTHINGを実行後、別のSQL文で
元のkeyを読みます。同じkey・同じpayloadは元のoperationを200で返し、新規commitは201です。
同じkey・異なるpayload、または同じevent ID・異なるkeyは409となり、2件目を保存しません。
commitと接続contextの終了後にだけ成功を返し、登録ではsynchronous_commitを有効にします。
SQL実行は4秒に制限し、timeoutやcommit不明は503です。自動再試行・成功推測は行いません。
TTL・削除・リセットAPIもありません。

参照は`GET /v1/operations/{operation_id}`または
`GET /v1/operations?idempotency_key=<元のkey>`です。認証を必須とし、operation ID・元のkey・
event ID・canonical payload digest・`PERSISTED`を返します。message・credentialは返しません。
全応答をno-storeとします。未発見の404は「作用なしの証拠」ではなく、DB障害は503です。
POST応答が失われても元のkeyで調査できます。サービスのPERSISTED観測はVERITASの確定Outcomeや
BindReceiptではありません。独立照合と、結果不明中の代替authorization抑止は送信側の後続課題です。

ASGI試験は合成tokenとSQL doubleを使用します。別の実PostgreSQL試験では、隔離した一時schemaで
同一要求・競合要求の同時実行、rollback、commit応答消失を検証し、既存PostgreSQL CIへ追加します。
ローカルmockを永続性の証明とは扱いません。HTTPS transport、実配備・provider設定、native
Receipt/Outcome/reconciliationは、このサービス実装ではまだ接続していません。

## 18. 明示設定するHTTPS transport（合成stream試験）

`SandboxHTTPSTransport`を`execute_sandbox_bind`へ明示的に渡せるようにします。
default transport・宛先・provider・listener・配備は追加しません。
executorが独立した信頼設定から正確なHTTPS宛先とCA（既定はsystem roots）を指定します。
毎回新しい接続でDNS名をTLS peer identityとして検証し、TLS 1.2以上・HTTP/1.1を使用します。
これはCAとhostnameの検証であり、証明書fingerprint pinningやDNS/IPの証明ではありません。

canonical payload・digest・元のkeyを検証し、TLS完了後、唯一のwrite直前に既存の
一回限りのmaterial callbackを呼びます。その間にawaitは挟みません。
接続遅延も既存の送信期限検証対象です。proxy・redirect・retryは使いません。
全体5秒、応答header 8 KiB・Content-Length body 4 KiBに制限し、chunked・encoding・
重複headerは拒否します。汎用HTTP adapterではなく限定protocolです。

201/200は元のkey・event ID・digest・正しいoperation UUIDが一致した場合のみ
固定の観測分類を返します。生body・header・remote operation ID・例外は保持しません。
409と503も区別しますが、作用なしや成功の証明にはしません。
永続状態は常にEFFECT_UNKNOWNのままです。Noneを返す既存transportの動作は維持します。

試験は合成credential、実native verifier、模擬streamを使用します。
実TLS handshake・実HTTPS送信・receiver commitの証明ではありません。
外部作用の有効化前には実TLS・host clock・PostgreSQLとreceiverの結合障害試験、
および第9節の配備条件の確認が必要です。Reconciliationでは元のkeyを使い、
HTTP観測から成功を推測しません。

## 19. 独立したread-only sandbox reconciliation

`reconcile_sandbox_effect`は元のauthorization・payloadと独立した過去時点の
source/governance/trust入力でnative issuance、action binding、消費行全体を再構築します。
対象は一致するrevision 2のsandbox dispatch-intent EFFECT_UNKNOWN行のみです。
欠落・差替え・terminal・別経路の行は拒否し、新たな消費や実行attemptは作りません。

現在のoperator設定から、送信用とは別のreader reference・version・provider・environment・
CAを渡します。scopeは`sandbox.operation.lookup.v1`固定で、writer referenceは拒否します。
reader・CA・元のdeployment/action設定全体への独立したReconciliationVerifierPolicy承認を
必須とします。providerのaudience・scope・version・失効・有効期限・clock healthは
解決前後とTLS後に再検証します。referenceの違いだけではprincipal分離の証明にならず、
provider/serviceでread-only権限と別principalを強制する配備が必要です。

元のoriginの`/v1/operations`へ、元のkeyだけをqueryに指定したGETを行います。
POST・redirect・proxy・retry・応答指定の宛先は使いません。providerと照会全体を5秒に制限します。
bounded HTTP framingのみ既存parserを再利用し、内容解釈とbindingは独立に検証します。
200 PERSISTEDのkey・event ID・digestの一致とremote operation UUIDの形式を確認します。
remote UUIDは独立lookupから取得し、dispatch応答には依存しません。
明示的なPERSISTED stateを含む全5項目を必須とし、送信側・照合側ともに
モデルの既定値からstateを補って成功を推測しません。

取得operationのcanonical digest、全観測lineage・時刻、承認policy hash、元の行hash、
reader metadata digestを検証済み証拠へ結び付けた後、CASでCONFIRMED_EFFECTへ進めます。
commit readbackが確認できた場合だけ確認済みを返します。404・401・503・redirectなど
200以外は元のUNKNOWNを保持します。不正応答・不一致・timeout・保存不明は成功を返しません。
CAS応答喪失時にはterminal行だけcommit済みの可能性があり、resetや再送ではなく
trusted storageの調査が必要です。

過去のissuance検証と現在のreader認可は分離し、元の認可が失効していても過去の作用を
調査できます。実行権限は復元しません。terminal行は書換えず拒否します。
独立とはdispatch応答からの独立であり、sandbox operatorからの独立ではありません。

effect storeに保持するのは証拠digestで、返した証拠全文の永続保管は後続Receipt/Outcome
工程に残ります。証拠・receiptのatomic保存、代替認可抑止、terminal自動復旧も未完です。
完全なE2E証明ではありません。試験は実native verifier、合成provider/stream、明示許可した
in-memory storeを使用します。実TLS・PostgreSQL結合試験と第9節の配備条件は引き続き必須です。
実credential・外部送信は、この試験では許可しません。

## 20. 照合証拠と確定状態の原子的保存

本節は第19節の「digestのみ保存」という制限を更新します。migration 0006の適用後、
sandbox reconciliationはCONFIRMED_EFFECT行と証拠全文SandboxReconciliationArchiveを
bind_effect_statesの一つのSQL UPDATEで保存します。CASは元のJSON行全体・hash・state・
revisionの一致とarchive列が空であることを要求します。CAS不成立時はどちらも保存せず、
archive保存済みの行は既存transitionからも更新できません。

archiveには検証済み証拠、元のUNKNOWN行、取得operationの5項目、reader metadata digestを
保持し、observation・acknowledgement・元の行・verification proofのhashを再計算できます。
token・Authorization header・生応答・event messageは保存しません。get_reconciliationは
状態と証拠を一緒に読み、schema・hash・時刻・lineageを検証します。commitと検証済みreadbackが
成功した場合だけreconcile_sandbox_effectは確定を返します。証拠欠落や不整合は拒否し、
既存のterminal行へ架空の証拠を補完しません。

commit応答喪失時は、両方が保存済みでも例外を返す可能性があります。その後operatorは
新しいlookup・POST・認可・状態変更なしで証拠を取得できます。これは保存内容の整合性検証で、
自動復旧・HTTPS再検証・Receipt/Outcome発行ではありません。hashは署名ではなく、DB管理者が
関連データ全体を書き換える攻撃は防ぎません。sandbox/providerとDBの信頼は前提に残ります。

既存transitionを含め、このコードの利用前にmigration 0006を適用します。nullable列の追加で
旧行とhashは維持します。downgradeは証拠を削除するため、operatorは先に保持方針に従って
保存する必要があります。effect-state CIの実PostgreSQL試験はrollback・commit応答喪失・
競合・別storeからの読戻し・証拠欠落を検証します。これは保存処理の試験であり、実TLSとreceiverを
結合したE2E証明ではありません。Receipt/Outcome発行、代替認可による重複実行の抑止、自動障害復旧、
実TLS/provider/host-clockの結合検証は未完です。第9節の配備条件は引き続き適用し、実外部アクセスは
有効化しません。

## 21. 保存済み証拠からのBindReceipt / Outcome発行

publish_sandbox_receiptsは独立した過去時点のsource/governance/trust入力で元のnative認可と
sandbox actionを再検証します。消費行全体と確定effect行を再構築し、保存archiveを検証して、
event ID・payload digest・originが認可されたactionと一致することを確認します。保存時の
reconciliation policy設定全体への承認も必要です。呼出側が作ったreceiptや送信ACKは受け付けません。

既存のBindReceiptとOutcomeReceipt形式を再利用します。BindReceiptは事後の記録で、bind_tsは
保存済みdispatch-intentの時刻です。実行時の検証時刻を捏造しません。保存されていないconstraint・
drift・riskの検証結果はLIVE_RESULTS_NOT_ARCHIVEDとし、新しい適格性や実行許可を主張しません。
COMMITTEDとoutcomeのpostcondition passedは、対象sandbox eventの保存を独立照合で確認した意味に
限定します。前後のシステム状態fingerprintは補いません。過去の人間承認statusとproof digestを
関連付けますが、新しい承認receiptは作りません。

両receiptに認可・消費・intent/decision・payload・外部operation・確定行・保存証拠hashを結び付け、
OutcomeからBindReceipt hashを参照します。IDと時刻は元の記録から決定的に導出し、bundle hashで
組全体を結び付けます。返却dictを変更しても保存値は変わりません。event message・credential・
生HTTPデータはコピーしません。

migration 0007は同じeffect行にnullableのsandbox_receipt_bundle列を追加します。元の確定行と
archiveの完全一致を条件に、一つのUPDATEで組全体を一度だけ保存します。同一入力の再呼出しは
同じ組を返し、異なる保存内容・証拠欠落・readback失敗は情報を漏らさない例外にします。commit応答
喪失時は保存済みの可能性があります。同じ独立検証入力で再呼出しすると、POST・lookup・追加消費・
effect状態変更なしで組を回収できます。effect行の元の記録とarchiveは変更しません。利用前に
migration 0007を適用し、列を削除するdowngrade前にはreceiptを保持方針に従って保存します。

これにより確定sandbox effectとDB保存されたartifactを接続します。TrustLogへは発行せず、
trustlog_hashは空、metadataはNOT_PUBLISHEDを明示します。障害に強いTrustLogへの一度だけの配信、
完全な自動復旧、実Decision-to-Effect E2Eは未完です。これらと第9節の配備条件は別工程に残ります。
本実装と合成試験は実credential・外部作用を許可しません。

## 22. 同一business eventのreplacement execution抑止

migration 0008は`bind_effect_states`にnullableかつuniqueな`business_event_key`列を追加します。
このkeyは実行ownership用metadataであり、既存Evidence hashを変えないためhash対象の
`EffectStateRecord` JSONには追加しません。新しいsandbox attemptはdomain separator、sandbox action、
target system、正確なHTTPS endpoint、event UUIDからkeyを導出します。message本文・authorization ID・
idempotency keyは含めません。そのため同じeventについて新しいauthorizationを発行しても、これらの値を
変えるだけでは既存claimを回避できません。

`prepare_sandbox_attempt`はeffect-state行をclaimする同じatomic INSERTへbusiness-event keyを渡します。
cross-processの競合はPostgreSQLのunique制約が裁定し、in-memory storeは明示的なtest時だけ同じ挙動を
再現します。事前の「存在しない」というreadを実行許可として扱いません。claim失敗や結果不明は
fail closedです。同じconsumed authorizationのreplayは従来どおり`SPE_ATTEMPT_ALREADY_EXISTS`、
別operationが同じbusiness eventに衝突した場合は`SPE_BUSINESS_EVENT_ALREADY_CLAIMED`として、
current-governance再確認・credential resolution・transportより前に拒否します。

`IN_FLIGHT`と`EFFECT_UNKNOWN`はbusiness-event claimを保持します。`CONFIRMED_EFFECT`も永久に保持し、
同じsandbox business eventへの二重作用を防ぎます。独立した証拠により`CONFIRMED_NO_EFFECT`へ遷移する
場合だけ、同じstate UPDATE内でunique keyを解放し、後続authorizationが新たなclaimを取得できるように
します。storage ambiguityはno-effectを意味せず、replacementを許可しません。

このguardは意図的にexecution-claim boundaryへ置きます。同じeventのnative authorization artifactが
発行済み・存在済みでも、競合するdurable claimが残る間はexecution permissionにはなりません。
issuance自体を禁止するのは別のpolicy surfaceであり、「replacementがcredential/network executionへ
到達しない」という本safety propertyには必須ではありません。

migration 0008はlegacy行へ架空のbusiness-event identityをbackfillしません。このsandbox execution pathを
有効化する前にmigrationを適用し、migration前のsandbox attemptが存在する場合はdeployment手順で確認します。
完全なautomatic recovery coordinator、実TLS/provider/host-clock/PostgreSQLの配備結合、TrustLogの
exactly-once発行、passing real Decision-to-Effect E2E proofは引き続き未完です。
