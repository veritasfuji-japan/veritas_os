import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import GlobalFatalErrorPage from "./global-error";

describe("GlobalFatalErrorPage", () => {
  it("renders fatal fallback UI and calls reset on reload", () => {
    const reset = vi.fn();

    render(
      <GlobalFatalErrorPage
        error={new Error("fatal")}
        reset={reset}
      />
    );

    expect(screen.getByText("重大な問題が発生しました")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "再読み込み" }));
    expect(reset).toHaveBeenCalledTimes(1);
  });

  it("logs the fatal error once mounted", () => {
    const consoleErrorSpy = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const error = new Error("fatal route failure");

    render(
      <GlobalFatalErrorPage
        error={error}
        reset={vi.fn()}
      />
    );

    expect(consoleErrorSpy).toHaveBeenCalledWith("Unhandled fatal app error:", error);
  });
});
