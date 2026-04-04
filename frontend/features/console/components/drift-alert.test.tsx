import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { DriftAlert } from "./drift-alert";

describe("DriftAlert", () => {
  it("returns null when alert is null", () => {
    const { container } = render(
      <DriftAlert alert={null} showAlert={false} setShowAlert={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders title button when alert is provided", () => {
    const alert = { title: "1 Issue", description: "Drift detected" };
    render(<DriftAlert alert={alert} showAlert={false} setShowAlert={vi.fn()} />);
    expect(screen.getByRole("button", { name: "1 Issue" })).toBeInTheDocument();
  });

  it("shows description when showAlert is true", () => {
    const alert = { title: "1 Issue", description: "Drift detected" };
    render(<DriftAlert alert={alert} showAlert={true} setShowAlert={vi.fn()} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Drift detected")).toBeInTheDocument();
  });

  it("hides description when showAlert is false", () => {
    const alert = { title: "1 Issue", description: "Drift detected" };
    render(<DriftAlert alert={alert} showAlert={false} setShowAlert={vi.fn()} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("toggles alert on button click", () => {
    const setShowAlert = vi.fn();
    const alert = { title: "1 Issue", description: "Drift detected" };
    render(<DriftAlert alert={alert} showAlert={false} setShowAlert={setShowAlert} />);
    fireEvent.click(screen.getByRole("button"));
    expect(setShowAlert).toHaveBeenCalledOnce();
    // The callback receives a toggle function
    const toggleFn = setShowAlert.mock.calls[0][0];
    expect(typeof toggleFn).toBe("function");
    expect(toggleFn(false)).toBe(true);
  });
});
