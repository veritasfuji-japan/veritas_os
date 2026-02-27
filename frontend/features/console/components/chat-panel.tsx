import { type LocaleKey } from "../../../locales/ja";
import { Button, Card } from "@veritas/design-system";
import { DANGER_PRESETS } from "../constants";
import { type ChatMessage } from "../types";

interface ChatPanelProps {
  t: (ja: string, en: string) => string;
  tk: (key: LocaleKey) => string;
  chatMessages: ChatMessage[];
  query: string;
  loading: boolean;
  error: string | null;
  setQuery: (value: string) => void;
  runDecision: (nextQuery?: string) => Promise<void>;
}

export function ChatPanel({
  t,
  tk,
  chatMessages,
  query,
  loading,
  error,
  setQuery,
  runDecision,
}: ChatPanelProps): JSX.Element {
  return (
    <Card title="Chat" className="bg-background/75">
      <div className="mb-4 rounded-md border border-border bg-background/60 p-3">
        <p className="mb-2 text-xs font-medium text-muted-foreground">{tk("chatHistory")}</p>
        {chatMessages.length > 0 ? (
          <ul className="space-y-2" aria-label="chat messages">
            {chatMessages.map((message) => (
              <li
                key={message.id}
                className={`max-w-[90%] whitespace-pre-wrap rounded-md px-3 py-2 text-sm ${
                  message.role === "user"
                    ? "ml-auto bg-primary/20 text-foreground"
                    : "mr-auto border border-border bg-background text-foreground"
                }`}
              >
                <p className="mb-1 text-[11px] font-semibold uppercase text-muted-foreground">{message.role}</p>
                {message.content}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">{tk("noMessagesYet")}</p>
        )}
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void runDecision();
        }}
        className="space-y-3"
      >
        <label className="block space-y-1 text-xs">
          <span className="font-medium">message</span>
          <textarea
            className="min-h-28 w-full rounded-md border border-border bg-background px-2 py-2"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={tk("messagePlaceholder")}
          />
        </label>

        <div className="space-y-2">
          <p className="text-xs font-medium">
            {tk("dangerPresets")}
          </p>
          <div className="flex flex-wrap gap-2">
            {DANGER_PRESETS.map((preset) => (
              <button
                key={preset.ja}
                type="button"
                className="rounded-md border border-red-500/50 bg-red-500/10 px-2 py-1 text-xs text-red-300"
                onClick={() => void runDecision(t(preset.ja, preset.en))}
                disabled={loading}
              >
                {t(preset.ja, preset.en).slice(0, 24)}...
              </button>
            ))}
          </div>
        </div>

        <Button type="submit" disabled={loading}>
          {loading ? tk("sending") : tk("send")}
        </Button>

        {error ? (
          <p role="alert" className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-300">
            {error}
          </p>
        ) : null}
      </form>
    </Card>
  );
}
