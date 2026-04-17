import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "../../../components/i18n-provider";
import {
  financialAmbiguityHumanReviewFixture,
  financialBlockFixture,
  financialEvidenceRequiredFixture,
  financialProceedFixture,
} from "../fixtures/financial-case";
import { DecisionResultPanel } from "./decision-result-panel";

describe("DecisionResultPanel snapshots", () => {
  it("renders role-based views without regression", () => {
    const { container, rerender } = render(
      <I18nProvider>
        <DecisionResultPanel result={financialProceedFixture} viewerRole="auditor" />
      </I18nProvider>,
    );
    expect(container.firstChild).toMatchSnapshot("auditor");

    rerender(
      <I18nProvider>
        <DecisionResultPanel result={financialProceedFixture} viewerRole="operator" />
      </I18nProvider>,
    );
    expect(container.firstChild).toMatchSnapshot("operator");

    rerender(
      <I18nProvider>
        <DecisionResultPanel result={financialProceedFixture} viewerRole="developer" />
      </I18nProvider>,
    );
    expect(container.firstChild).toMatchSnapshot("developer");
  });

  it("renders four fixture states without regression", () => {
    const { container, rerender } = render(
      <I18nProvider>
        <DecisionResultPanel result={financialBlockFixture} viewerRole="auditor" />
      </I18nProvider>,
    );
    expect(container.firstChild).toMatchSnapshot("block");

    rerender(
      <I18nProvider>
        <DecisionResultPanel result={financialProceedFixture} viewerRole="operator" />
      </I18nProvider>,
    );
    expect(container.firstChild).toMatchSnapshot("proceed");

    rerender(
      <I18nProvider>
        <DecisionResultPanel result={financialEvidenceRequiredFixture} viewerRole="operator" />
      </I18nProvider>,
    );
    expect(container.firstChild).toMatchSnapshot("evidence_required");

    rerender(
      <I18nProvider>
        <DecisionResultPanel result={financialAmbiguityHumanReviewFixture} viewerRole="auditor" />
      </I18nProvider>,
    );
    expect(container.firstChild).toMatchSnapshot("ambiguity_human_review");
  });
});
