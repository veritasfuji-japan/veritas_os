import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import CommandDashboardPage from "./page";

describe("CommandDashboardPage", () => {
  it("renders dashboard skeleton content", () => {
    render(<CommandDashboardPage />);

    expect(screen.getByText("Command Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Uptime Lattice")).toBeInTheDocument();
  });
});
