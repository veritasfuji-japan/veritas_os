import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { StaleBanner } from "./stale-banner";

describe("StaleBanner", () => {
  it("renders message with status role", () => {
    render(<StaleBanner message="Data is stale" />);
    expect(screen.getByRole("status")).toHaveTextContent("Data is stale");
  });

  it("renders refresh button when onRefresh is provided", () => {
    const onRefresh = vi.fn();
    render(<StaleBanner message="Stale" onRefresh={onRefresh} />);
    const btn = screen.getByRole("button", { name: "Refresh" });
    fireEvent.click(btn);
    expect(onRefresh).toHaveBeenCalledOnce();
  });

  it("uses custom refreshLabel", () => {
    render(<StaleBanner message="Stale" onRefresh={() => {}} refreshLabel="Reload" />);
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
  });

  it("does not render refresh button when onRefresh is omitted", () => {
    render(<StaleBanner message="Stale" />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("applies custom className", () => {
    render(<StaleBanner message="S" className="extra" />);
    expect(screen.getByRole("status").className).toContain("extra");
  });
});
