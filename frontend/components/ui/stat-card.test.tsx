import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatCard } from "./stat-card";

describe("StatCard", () => {
  it("renders label and value", () => {
    render(<StatCard label="Total" value={42} />);
    expect(screen.getByText("Total")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("applies variant-specific color class", () => {
    render(<StatCard label="Errors" value={5} variant="danger" />);
    const valueEl = screen.getByText("5");
    expect(valueEl.className).toContain("danger");
  });

  it("defaults to default variant", () => {
    render(<StatCard label="Count" value={10} />);
    const valueEl = screen.getByText("10");
    expect(valueEl.className).toContain("foreground");
  });

  it("accepts string values", () => {
    render(<StatCard label="Status" value="OK" />);
    expect(screen.getByText("OK")).toBeInTheDocument();
  });
});
