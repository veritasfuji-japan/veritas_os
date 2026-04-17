import { render, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "../../../components/i18n-provider";
import { financialHumanReviewFixture } from "../fixtures/financial-case";
import { DecisionResultPanel } from "./decision-result-panel";

describe("DecisionResultPanel i18n snapshots", () => {
  it("renders Japanese locale snapshot", () => {
    window.localStorage.setItem("veritas_language", "ja");
    const { container } = render(
      <I18nProvider>
        <DecisionResultPanel result={financialHumanReviewFixture} viewerRole="operator" />
      </I18nProvider>,
    );
    expect(container.firstChild).toMatchSnapshot();
  });

  it("renders English locale snapshot", async () => {
    window.localStorage.setItem("veritas_language", "en");
    const { container, findByText } = render(
      <I18nProvider>
        <DecisionResultPanel result={financialHumanReviewFixture} viewerRole="operator" />
      </I18nProvider>,
    );
    await findByText("Public decision output");
    await waitFor(() => {
      expect(container.textContent).toContain("Generate Evidence Bundle");
    });
    expect(container.firstChild).toMatchSnapshot();
  });
});
