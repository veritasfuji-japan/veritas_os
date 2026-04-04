import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ResultSection } from "./result-section";

describe("ResultSection", () => {
  it("renders title and string value", () => {
    render(<ResultSection title="Evidence" value="Some evidence text" />);
    expect(screen.getByText("Evidence")).toBeInTheDocument();
    expect(screen.getByText("Some evidence text")).toBeInTheDocument();
  });

  it("renders object value as JSON", () => {
    render(<ResultSection title="Data" value={{ key: "val" }} />);
    expect(screen.getByText("Data")).toBeInTheDocument();
    expect(screen.getByText(/key/)).toBeInTheDocument();
  });

  it("renders null value", () => {
    render(<ResultSection title="Empty" value={null} />);
    expect(screen.getByText("null")).toBeInTheDocument();
  });

  it("has accessible section labelled by title", () => {
    render(<ResultSection title="My Section" value="content" />);
    const section = screen.getByRole("region", { name: "My Section" });
    expect(section).toBeInTheDocument();
  });
});
