# Value Core 分離

Value Core は以下の3層に分離されます。

- `normative_weights`
- `operational_preferences`
- `personal_preferences`

ガバナンススコアリングは `normative_weights` のみを使用します。`operational_preferences` と `personal_preferences` は `ValueResult.total` に影響しません。

後方互換として、旧 `weights` 形式と旧日本語キーの移行を維持します。

これにより、開発作業方針や個人嗜好が規制対象の意思決定価値と混ざることを防ぎます。
