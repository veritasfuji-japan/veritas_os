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
