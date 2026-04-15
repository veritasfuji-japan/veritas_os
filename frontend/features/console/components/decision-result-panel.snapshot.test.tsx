import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { financialHumanReviewFixture } from "../fixtures/financial-case";
import { DecisionResultPanel } from "./decision-result-panel";

describe("DecisionResultPanel snapshots", () => {
  it("renders financial human-review scenario without regression", () => {
    const { container } = render(<DecisionResultPanel result={financialHumanReviewFixture} />);
    expect(container.firstChild).toMatchSnapshot();
  });
});
