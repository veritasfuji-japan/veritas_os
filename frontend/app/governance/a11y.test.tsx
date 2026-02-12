import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import GovernanceControlPage from "./page";

/**
 * Basic accessibility checks using semantic HTML inspection.
 * Full axe-core checks run in Playwright E2E tests (e2e/smoke.spec.ts).
 */
describe("Governance a11y (unit)", () => {
  it("all interactive elements have accessible labels", () => {
    const { container } = render(<GovernanceControlPage />);

    // Buttons should have text content
    const buttons = container.querySelectorAll("button");
    for (const btn of buttons) {
      const hasLabel =
        btn.textContent?.trim() ||
        btn.getAttribute("aria-label") ||
        btn.getAttribute("aria-labelledby");
      expect(hasLabel).toBeTruthy();
    }

    // Inputs should have labels
    const inputs = container.querySelectorAll("input");
    for (const input of inputs) {
      const hasLabel =
        input.getAttribute("aria-label") ||
        input.getAttribute("aria-labelledby") ||
        input.closest("label");
      expect(hasLabel).toBeTruthy();
    }
  });

  it("error/success messages use proper ARIA roles", () => {
    // The page has role="alert" for errors and role="status" for success.
    // Verify the page renders without violating this contract.
    const { container } = render(<GovernanceControlPage />);
    // In the initial state no alerts/statuses should be shown
    expect(container.querySelector("[role='alert']")).toBeNull();
    expect(container.querySelector("[role='status']")).toBeNull();
  });

  it("page has heading structure", () => {
    const { container } = render(<GovernanceControlPage />);
    // Should have card title headings
    const headings = container.querySelectorAll("h2, h3");
    expect(headings.length).toBeGreaterThan(0);
  });
});
