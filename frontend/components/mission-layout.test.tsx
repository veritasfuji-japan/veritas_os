import { fireEvent, render, screen } from "@testing-library/react";
import { MissionLayout } from "./mission-layout";
import { I18nProvider } from "./i18n";

vi.mock("next/navigation", () => ({
  usePathname: () => "/governance"
}));

describe("MissionLayout", () => {
  it("shows all navigation links and highlights active route", () => {
    render(
      <I18nProvider>
        <MissionLayout>
          <div>child</div>
        </MissionLayout>
      </I18nProvider>
    );

    expect(screen.getByRole("link", { name: /command dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /decision console/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /governance control/i })).toHaveAttribute(
      "href",
      "/governance"
    );
    expect(screen.getByText("環境")).toBeInTheDocument();
    expect(screen.getByText("最新イベント")).toBeInTheDocument();
    expect(screen.getByText("可読性を優先した運用ビュー")).toBeInTheDocument();
  });

  it("switches language to english", () => {
    render(
      <I18nProvider>
        <MissionLayout>
          <div>child</div>
        </MissionLayout>
      </I18nProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: "en" }));
    expect(screen.getByText("Operational view focused on readability")).toBeInTheDocument();
    expect(screen.getByText("Global health and alerts")).toBeInTheDocument();
  });
});
