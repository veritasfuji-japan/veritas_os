import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { LoadingSkeleton } from "./loading-skeleton";

describe("LoadingSkeleton", () => {
  it("renders with status role and accessible label", () => {
    render(<LoadingSkeleton />);
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders 3 skeleton lines by default", () => {
    const { container } = render(<LoadingSkeleton />);
    const lines = container.querySelectorAll(".h-3");
    expect(lines).toHaveLength(3);
  });

  it("renders custom number of lines", () => {
    const { container } = render(<LoadingSkeleton lines={5} />);
    const lines = container.querySelectorAll(".h-3");
    expect(lines).toHaveLength(5);
  });

  it("applies custom className", () => {
    render(<LoadingSkeleton className="my-class" />);
    expect(screen.getByRole("status").className).toContain("my-class");
  });
});
