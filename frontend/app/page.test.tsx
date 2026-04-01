import { render, screen } from "@testing-library/react";
import CommandDashboardPage from "./page";

describe("CommandDashboardPage", () => {
  it("renders dashboard skeleton content", () => {
    render(<CommandDashboardPage />);

    expect(screen.getByText("Command Dashboard")).toBeInTheDocument();
    expect(screen.getByText("稼働格子")).toBeInTheDocument();
  });
});
