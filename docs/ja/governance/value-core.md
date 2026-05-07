# Value Core 分離

Value Core は以下の3層に分離されます。

- `normative_weights`
- `operational_preferences`
- `personal_preferences`

ガバナンススコアリングは `normative_weights` のみを使用します。`operational_preferences` と `personal_preferences` は `ValueResult.total` に影響しません。
`DEFAULT_WEIGHTS` と `ValueProfile.weights` は旧互換の表示用ビューであり、legacy operational/personal key を含む場合があります。
ガバナンススコア計算には使いません。
ガバナンス計算の正規ソースは `DEFAULT_NORMATIVE_WEIGHTS` です。
`personal_preferences` の正規キーとして現在は `sauna_less` を allowlist しています。
個人嗜好は互換性・ユーザー設定保持のために保存されますが、ガバナンススコア計算には含めません。

後方互換として、旧 `weights` 形式と旧日本語キーの移行を維持します。

これにより、開発作業方針や個人嗜好が規制対象の意思決定価値と混ざることを防ぎます。
