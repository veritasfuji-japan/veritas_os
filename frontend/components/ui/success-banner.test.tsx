import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SuccessBanner } from "./success-banner";

describe("SuccessBanner", () => {
  it("renders message with status role", () => {
    render(<SuccessBanner message="Operation succeeded" />);
    expect(screen.getByRole("status")).toHaveTextContent("Operation succeeded");
  });

  it("applies success styles", () => {
    render(<SuccessBanner message="Done" />);
    expect(screen.getByRole("status").className).toContain("text-success");
  });

  it("applies custom className", () => {
    render(<SuccessBanner message="OK" className="my-class" />);
    expect(screen.getByRole("status").className).toContain("my-class");
  });
});
