import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import GlobalErrorPage from "./error";

describe("GlobalErrorPage", () => {
  it("renders recovery UI and calls reset on retry", () => {
    const reset = vi.fn();

    render(
      <GlobalErrorPage
        error={new Error("boom")}
        reset={reset}
      />
    );

    expect(screen.getByText("問題が発生しました")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "再試行" }));
    expect(reset).toHaveBeenCalledTimes(1);
  });

  it("logs the routed error once mounted", () => {
    const consoleErrorSpy = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const error = new Error("route failure");

    render(
      <GlobalErrorPage
        error={error}
        reset={vi.fn()}
      />
    );

    expect(consoleErrorSpy).toHaveBeenCalledWith("Unhandled route error:", error);
  });
});
