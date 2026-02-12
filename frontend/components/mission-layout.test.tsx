import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MissionLayout } from "./mission-layout";

vi.mock("next/navigation", () => ({
  usePathname: () => "/governance"
}));

describe("MissionLayout", () => {
  it("shows all navigation links and highlights active route", () => {
    render(
      <MissionLayout>
        <div>child</div>
      </MissionLayout>
    );

    expect(screen.getByRole("link", { name: /command dashboard/i })).not.toBeNull();
    expect(screen.getByRole("link", { name: /decision console/i })).not.toBeNull();
    expect(screen.getByRole("link", { name: /governance control/i }).getAttribute("href")).toBe(
      "/governance"
    );
    expect(screen.getByText("Environment")).not.toBeNull();
    expect(screen.getByText("Latest Event")).not.toBeNull();
  });
});
