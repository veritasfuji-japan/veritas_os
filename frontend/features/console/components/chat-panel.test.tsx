import { render, screen, fireEvent } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChatPanel } from "./chat-panel";

const t = (_ja: string, en: string) => en;
const translations: Record<string, string> = {
  chatMessagesAriaLabel: "Chat messages",
  messageLabel: "messageLabel",
  noMessagesYet: "noMessagesYet",
  send: "send",
  sending: "sending",
};
const tk = (key: string) => translations[key] ?? key;

function renderPanel(overrides: Partial<Parameters<typeof ChatPanel>[0]> = {}) {
  const defaults = {
    t,
    tk: tk as Parameters<typeof ChatPanel>[0]["tk"],
    chatMessages: [],
    query: "",
    loading: false,
    executionStatus: "idle" as const,
    error: null,
    setQuery: vi.fn(),
    runDecision: vi.fn().mockResolvedValue(undefined),
  };
  return render(<ChatPanel {...defaults} {...overrides} />);
}

describe("ChatPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the empty state message when there are no messages", () => {
    renderPanel();
    expect(screen.getByText("noMessagesYet")).toBeInTheDocument();
  });

  it("renders chat messages", () => {
    renderPanel({
      chatMessages: [
        { id: 1, role: "user", content: "Hello" },
        { id: 2, role: "assistant", content: "Hi there" },
      ],
    });
    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.getByText("Hi there")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Chat messages" })).toBeInTheDocument();
  });

  it("strips HTML tags from message content for XSS protection", () => {
    renderPanel({
      chatMessages: [
        { id: 1, role: "assistant", content: '<script>alert("xss")</script>Safe text' },
      ],
    });
    expect(screen.queryByText('<script>alert("xss")</script>')).not.toBeInTheDocument();
    expect(screen.getByText('alert("xss")Safe text')).toBeInTheDocument();
  });

  it("strips HTML tags from error messages for XSS protection", () => {
    renderPanel({ error: "<img onerror=alert(1)>error msg" });
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toBe("error msg");
  });

  it("calls setQuery on textarea change", () => {
    const setQuery = vi.fn();
    renderPanel({ setQuery });
    fireEvent.change(screen.getByLabelText("messageLabel"), {
      target: { value: "new text" },
    });
    expect(setQuery).toHaveBeenCalledWith("new text");
  });

  it("calls runDecision on form submit", () => {
    const runDecision = vi.fn().mockResolvedValue(undefined);
    renderPanel({ runDecision });
    fireEvent.submit(screen.getByRole("button", { name: "send" }).closest("form")!);
    expect(runDecision).toHaveBeenCalled();
  });

  it("disables submit button when loading", () => {
    renderPanel({ loading: true });
    expect(screen.getByRole("button", { name: "sending" })).toBeDisabled();
  });

  it("shows submitting status message", () => {
    renderPanel({ executionStatus: "submitting" });
    expect(screen.getByText("submittingStatus")).toBeInTheDocument();
  });

  it("shows streaming status message", () => {
    renderPanel({ executionStatus: "streaming" });
    expect(screen.getByText("streamingStatus")).toBeInTheDocument();
  });

  it("renders danger presets when enabled", () => {
    vi.stubEnv("NODE_ENV", "test");
    vi.stubEnv("NEXT_PUBLIC_ENABLE_DANGER_PRESETS", "true");
    renderPanel();
    expect(screen.getByText("dangerPresets")).toBeInTheDocument();
    // Should render preset buttons
    const presetButtons = screen.getAllByRole("button").filter(
      (btn) => btn.className.includes("red-500"),
    );
    expect(presetButtons.length).toBe(3);
    vi.unstubAllEnvs();
  });

  it("danger preset button calls runDecision with preset text", async () => {
    vi.stubEnv("NODE_ENV", "test");
    vi.stubEnv("NEXT_PUBLIC_ENABLE_DANGER_PRESETS", "true");
    const runDecision = vi.fn().mockResolvedValue(undefined);
    renderPanel({ runDecision });
    const presetButtons = screen.getAllByRole("button").filter(
      (btn) => btn.className.includes("red-500"),
    );
    fireEvent.click(presetButtons[0]);
    expect(runDecision).toHaveBeenCalled();
    vi.unstubAllEnvs();
  });

  it("renders system role label", () => {
    renderPanel({
      chatMessages: [
        { id: 1, role: "system", content: "System message" },
      ],
    });
    expect(screen.getByText("chatRoleSystem")).toBeInTheDocument();
    expect(screen.getByText("System message")).toBeInTheDocument();
  });
});
