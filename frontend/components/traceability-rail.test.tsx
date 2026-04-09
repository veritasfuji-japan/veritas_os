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

  it("blocks trust log link when request_id format is invalid", () => {
    render(<TraceabilityRail />);

    fireEvent.change(screen.getByDisplayValue("req-"), {
      target: { value: "invalid-request-id" },
    });

    expect(
      screen.getByText("request_id は req- で始まり、英数字または . _ - を含めてください。"),
    ).toBeInTheDocument();
    const trustLogLink = screen.getByRole("link", { name: "TrustLog" });
    expect(trustLogLink).toHaveAttribute("aria-disabled", "true");
    expect(trustLogLink).toHaveAttribute("href", "#");
  });
});
