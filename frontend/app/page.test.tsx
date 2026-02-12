import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import CommandDashboardPage from "./page";

describe("CommandDashboardPage", () => {
  it("renders dashboard skeleton content", () => {
    render(<CommandDashboardPage />);

    expect(screen.getByText("Command Dashboard")).not.toBeNull();
    expect(screen.getByText("Uptime Lattice")).not.toBeNull();
  });
});
