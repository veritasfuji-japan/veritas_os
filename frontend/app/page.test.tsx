import { render, screen } from "@testing-library/react";
import Home from "./page";

describe("Home", () => {
  it("renders workspace card", () => {
    render(<Home />);
    expect(screen.getByText("Veritas UI Workspace")).toBeInTheDocument();
  });
});
