import { type LocaleKey } from "./ja";

export const en: Record<LocaleKey, string> = {
  consoleDescription: "Run POST /v1/decide directly and visualize the decision pipeline.",
  noResultsYet: "No results yet.",
  queryRequired: "Please enter query.",
  authError: "401: Missing or invalid API key.",
  authErrorAssistant: "401 error: Missing or invalid API key.",
  serviceUnavailable: "503: service_unavailable (backend execution unavailable).",
  serviceUnavailableAssistant: "503 error: service_unavailable (backend execution unavailable).",
  schemaMismatch: "Schema mismatch: response is not an object.",
  networkError: "Network error: cannot reach backend.",
  chatHistory: "Chat history",
  noMessagesYet: "No messages yet.",
  messagePlaceholder: "Enter a message",
  dangerPresets: "Danger presets (for safety rejection checks)",
  sending: "Sending...",
  send: "Send",
};
