import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TraceabilityRail } from "./traceability-rail";

describe("TraceabilityRail", () => {
  it("updates export safety when redaction is disabled for viewer", () => {
    render(<TraceabilityRail />);

    fireEvent.change(screen.getByDisplayValue("operator"), { target: { value: "viewer" } });
    fireEvent.click(screen.getByRole("button", { name: /redaction on/i }));

    expect(screen.getByText("high")).toBeInTheDocument();
  });
});
