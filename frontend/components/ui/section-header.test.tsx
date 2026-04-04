import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SectionHeader } from "./section-header";

describe("SectionHeader", () => {
  it("renders title", () => {
    render(<SectionHeader title="My Section" />);
    expect(screen.getByText("My Section")).toBeInTheDocument();
  });

  it("renders description when provided", () => {
    render(<SectionHeader title="Title" description="Some description" />);
    expect(screen.getByText("Some description")).toBeInTheDocument();
  });

  it("does not render description when not provided", () => {
    const { container } = render(<SectionHeader title="Title" />);
    const paragraphs = container.querySelectorAll("p");
    expect(paragraphs).toHaveLength(1); // only title
  });

  it("renders trailing element", () => {
    render(<SectionHeader title="Title" trailing={<button type="button">Action</button>} />);
    expect(screen.getByRole("button", { name: "Action" })).toBeInTheDocument();
  });
});
