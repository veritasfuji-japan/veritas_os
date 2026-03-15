import { fireEvent, render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import GlobalFatalErrorPage from "./global-error";

function renderGlobalFatalErrorPage(error: Error, reset: () => void) {
  document.documentElement.innerHTML = "";

  return render(
    <GlobalFatalErrorPage
      error={error}
      reset={reset}
    />,
    {
      baseElement: document.documentElement,
      container: document.documentElement,
    },
  );
}

describe("GlobalFatalErrorPage", () => {
  beforeEach(() => {
    Object.defineProperty(navigator, "language", { value: "ja", configurable: true });
  });

  it("renders fatal fallback UI and calls reset on reload", () => {
    const consoleErrorSpy = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const reset = vi.fn();
    const rendered = renderGlobalFatalErrorPage(new Error("fatal"), reset);

    expect(rendered.getByText("重大な問題が発生しました")).toBeTruthy();
    fireEvent.click(rendered.getByRole("button", { name: "再読み込み" }));
    expect(reset).toHaveBeenCalledTimes(1);
  });

  it("logs the fatal error once mounted", () => {
    const consoleErrorSpy = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const error = new Error("fatal route failure");

    renderGlobalFatalErrorPage(error, vi.fn());

    expect(consoleErrorSpy).toHaveBeenCalledWith("Unhandled fatal app error:", error);
  });
});
