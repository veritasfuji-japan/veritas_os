import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { EmptyState } from "./empty-state";

describe("EmptyState", () => {
  it("renders title and description", () => {
    render(<EmptyState title="No items" description="Nothing to display" />);
    expect(screen.getByText("No items")).toBeInTheDocument();
    expect(screen.getByText("Nothing to display")).toBeInTheDocument();
  });

  it("renders icon when provided", () => {
    render(
      <EmptyState
        title="No items"
        description="Nothing"
        icon={<span data-testid="icon">★</span>}
      />,
    );
    expect(screen.getByTestId("icon")).toBeInTheDocument();
  });

  it("does not render icon wrapper when icon is not provided", () => {
    const { container } = render(
      <EmptyState title="No items" description="Nothing" />,
    );
    expect(container.querySelector(".border-dashed")).toBeNull();
  });

  it("renders action when provided", () => {
    render(
      <EmptyState
        title="No items"
        description="Nothing"
        action={<button type="button">Add</button>}
      />,
    );
    expect(screen.getByRole("button", { name: "Add" })).toBeInTheDocument();
  });

  it("applies custom className", () => {
    const { container } = render(
      <EmptyState title="T" description="D" className="extra" />,
    );
    expect(container.firstElementChild?.className).toContain("extra");
  });
});
