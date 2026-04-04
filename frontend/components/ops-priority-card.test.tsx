import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { OpsPriorityCard } from "./ops-priority-card";
import { I18nProvider } from "./i18n-provider";
import type { OpsPriorityItem } from "./dashboard-types";

const item: OpsPriorityItem = {
  key: "drift",
  titleJa: "ドリフト対応",
  titleEn: "Drift Response",
  owner: "Platform Team",
  whyNowJa: "乖離が増加中",
  whyNowEn: "Drift is increasing",
  impactWindowJa: "24時間以内",
  impactWindowEn: "Within 24 hours",
  ctaJa: "確認する",
  ctaEn: "Review",
  href: "/governance",
};

describe("OpsPriorityCard", () => {
  it("renders Japanese content by default", () => {
    render(
      <I18nProvider>
        <OpsPriorityCard item={item} priority={1} />
      </I18nProvider>,
    );
    expect(screen.getByText("ドリフト対応")).toBeInTheDocument();
    expect(screen.getByText("Owner: Platform Team")).toBeInTheDocument();
    expect(screen.getByText("乖離が増加中")).toBeInTheDocument();
  });

  it("renders link with href", () => {
    render(
      <I18nProvider>
        <OpsPriorityCard item={item} priority={2} />
      </I18nProvider>,
    );
    const link = screen.getByRole("link", { name: "確認する" });
    expect(link).toHaveAttribute("href", "/governance");
  });
});
