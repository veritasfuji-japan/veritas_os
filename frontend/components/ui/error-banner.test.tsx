import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ErrorBanner } from "./error-banner";

describe("ErrorBanner", () => {
  it("renders message with alert role", () => {
    render(<ErrorBanner message="Something went wrong" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
  });

  it("applies danger styles by default", () => {
    render(<ErrorBanner message="Error" />);
    expect(screen.getByRole("alert").className).toContain("text-danger");
  });

  it("applies warning styles for warning variant", () => {
    render(<ErrorBanner message="Warning" variant="warning" />);
    expect(screen.getByRole("alert").className).toContain("text-warning");
  });

  it("renders retry button when onRetry is provided", () => {
    const onRetry = vi.fn();
    render(<ErrorBanner message="Fail" onRetry={onRetry} />);
    const btn = screen.getByRole("button", { name: "Retry" });
    fireEvent.click(btn);
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("uses custom retryLabel", () => {
    render(<ErrorBanner message="Fail" onRetry={() => {}} retryLabel="Try again" />);
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("does not render retry button when onRetry is omitted", () => {
    render(<ErrorBanner message="Fail" />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("applies custom className", () => {
    render(<ErrorBanner message="E" className="custom" />);
    expect(screen.getByRole("alert").className).toContain("custom");
  });
});
