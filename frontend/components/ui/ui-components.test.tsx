import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ErrorBanner } from "./error-banner";
import { EmptyState } from "./empty-state";
import { SuccessBanner } from "./success-banner";
import { LoadingSkeleton } from "./loading-skeleton";
import { StaleBanner } from "./stale-banner";

describe("ErrorBanner", () => {
  it("renders error message with role=alert", () => {
    render(<ErrorBanner message="Something went wrong" />);
    const alert = screen.getByRole("alert");
    expect(alert).toBeInTheDocument();
    expect(alert).toHaveTextContent("Something went wrong");
  });

  it("renders retry button when onRetry provided", () => {
    const onRetry = vi.fn();
    render(<ErrorBanner message="Error" onRetry={onRetry} retryLabel="Try again" />);
    const button = screen.getByRole("button", { name: "Try again" });
    expect(button).toBeInTheDocument();
    fireEvent.click(button);
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("does not render retry button when onRetry not provided", () => {
    render(<ErrorBanner message="Error" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("applies warning variant styles", () => {
    render(<ErrorBanner message="Warning" variant="warning" />);
    const alert = screen.getByRole("alert");
    expect(alert.className).toContain("warning");
  });
});

describe("EmptyState", () => {
  it("renders title and description", () => {
    render(<EmptyState title="No data" description="Try loading" />);
    expect(screen.getByText("No data")).toBeInTheDocument();
    expect(screen.getByText("Try loading")).toBeInTheDocument();
  });

  it("renders action when provided", () => {
    render(
      <EmptyState
        title="Empty"
        description="Nothing here"
        action={<button type="button">Load</button>}
      />,
    );
    expect(screen.getByRole("button", { name: "Load" })).toBeInTheDocument();
  });
});

describe("SuccessBanner", () => {
  it("renders success message with role=status", () => {
    render(<SuccessBanner message="Done!" />);
    const status = screen.getByRole("status");
    expect(status).toBeInTheDocument();
    expect(status).toHaveTextContent("Done!");
  });
});

describe("LoadingSkeleton", () => {
  it("renders with role=status and accessible label", () => {
    render(<LoadingSkeleton lines={3} />);
    const status = screen.getByRole("status");
    expect(status).toBeInTheDocument();
    expect(status).toHaveAttribute("aria-label", "Loading");
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders correct number of skeleton lines", () => {
    const { container } = render(<LoadingSkeleton lines={5} />);
    const lines = container.querySelectorAll(".h-3");
    expect(lines.length).toBe(5);
  });
});

describe("StaleBanner", () => {
  it("renders stale message with role=status", () => {
    render(<StaleBanner message="Data may be outdated" />);
    const status = screen.getByRole("status");
    expect(status).toBeInTheDocument();
    expect(status).toHaveTextContent("Data may be outdated");
  });

  it("renders refresh button when onRefresh provided", () => {
    const onRefresh = vi.fn();
    render(
      <StaleBanner
        message="Stale"
        onRefresh={onRefresh}
        refreshLabel="Refresh now"
      />,
    );
    const button = screen.getByRole("button", { name: "Refresh now" });
    fireEvent.click(button);
    expect(onRefresh).toHaveBeenCalledOnce();
  });
});
