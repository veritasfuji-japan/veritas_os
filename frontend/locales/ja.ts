export const ja = {
  consoleDescription: "POST /v1/decide を直接実行し、意思決定パイプラインを可視化します。",
  noResultsYet: "まだ結果はありません。",
  queryRequired: "query を入力してください。",
  authError: "401: APIキー不足、または無効です。",
  authErrorAssistant: "401 エラー: APIキー不足、または無効です。",
  serviceUnavailable: "503: service_unavailable（バックエンド処理を実行できません）。",
  serviceUnavailableAssistant: "503 エラー: service_unavailable（バックエンド処理を実行できません）。",
  schemaMismatch: "schema不一致: レスポンスがオブジェクトではありません。",
  networkError: "ネットワークエラー: バックエンドへ接続できません。",
  chatHistory: "チャット履歴",
  noMessagesYet: "まだメッセージはありません。",
  messagePlaceholder: "メッセージを入力",
  dangerPresets: "危険プリセット（安全拒否確認用）",
  sending: "送信中...",
  send: "送信",
} as const;

export type LocaleKey = keyof typeof ja;
