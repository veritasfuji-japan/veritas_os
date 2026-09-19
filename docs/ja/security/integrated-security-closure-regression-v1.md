# 統合セキュリティ・クロージャ回帰 v1

## 目的

このゲートは、セキュリティ指摘F-01からF-08までの回帰テストを、1つの
必須CI単位として実行します。ポリシー、主体ID、Replay、Trust feedback、
WATの各境界を`main`上で組み合わせた後に、個別修正が静かに後退することを
防ぎます。

機械可読な正本は`security/integrated_security_closure_v1.json`です。
Security Gatesワークフローは、Pull Requestおよび`main`へのpush時に
`scripts/security/run_integrated_security_closure.py`を実行します。

## 対象境界

| 指摘 | 必須境界 |
| --- | --- |
| F-01 | リクエスト値によってサーバー必須のポリシー適用を解除したり、runtime bundleを選択したりできない。 |
| F-02 | 署名済みmanifestが、実際に評価するcanonical policy bytesと一致する。 |
| F-03 | 信頼済み鍵がない場合にEd25519検証が下位方式へ退行しない。 |
| F-04 | 認証済みprincipalが判断時のmemory取得範囲を所有する。 |
| F-05 | caller metadataによって別principalの名前空間へmemoryを書き込めない。 |
| F-06 | 公開Replayから外部APIを有効化できない。 |
| F-07 | TrustLog読取権限ではfeedbackを書けず、書込主体は認証済みprincipalに固定される。 |
| F-08 | WAT validationから発行・失効の状態遷移を作成できない。 |

同じ実行で、native-v2の単回消費契約、sandbox bind executionの安全性、
および凍結済みのcontrolled Decision-to-Effect proof境界も保全します。

## 証拠と失敗時の扱い

manifestに指定された全対象が、1つのpytest process内ですべて成功した場合に
のみゲートは成功します。対象ファイルの欠落、F-01からF-08までのmapping
不足、対象の重複、manifest不正はテスト実行前にfail-closedで拒否します。
CIが失敗している間は、修正または明示的なmanifestレビューが完了するまで
Security Closureを完了済みとは扱いません。

## 明示的な非主張

このゲートの成功は、本番準備完了、セキュリティ認証、依存ライブラリの
全advisory解消、実顧客credential／endpointの利用、独立した本番
infrastructure、または本番Decision-to-Effect E2Eの証明を意味しません。
既存のcontrolled proofはArchitecture Freeze文書の範囲に限定されます。
