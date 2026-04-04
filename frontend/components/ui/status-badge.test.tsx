import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "./status-badge";

describe("StatusBadge", () => {
  it("renders label text", () => {
    render(<StatusBadge label="Active" variant="success" />);
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("applies success variant styles", () => {
    render(<StatusBadge label="OK" variant="success" />);
    expect(screen.getByText("OK").className).toContain("success");
  });

  it("applies danger variant styles", () => {
    render(<StatusBadge label="Error" variant="danger" />);
    expect(screen.getByText("Error").className).toContain("danger");
  });

  it("applies custom className", () => {
    render(<StatusBadge label="Test" variant="info" className="my-custom" />);
    expect(screen.getByText("Test").className).toContain("my-custom");
  });
});
