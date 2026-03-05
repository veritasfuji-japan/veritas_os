import { render, screen, fireEvent } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChatPanel } from "./chat-panel";

const t = (_ja: string, en: string) => en;
const tk = (key: string) => key;

function renderPanel(overrides: Partial<Parameters<typeof ChatPanel>[0]> = {}) {
  const defaults = {
    t,
    tk: tk as Parameters<typeof ChatPanel>[0]["tk"],
    chatMessages: [],
    query: "",
    loading: false,
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
    expect(screen.getByRole("list", { name: "chat messages" })).toBeInTheDocument();
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
    fireEvent.change(screen.getByPlaceholderText("messagePlaceholder"), {
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
});
