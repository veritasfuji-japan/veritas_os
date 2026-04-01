import { render, screen } from "@testing-library/react";
import { MissionLayout } from "./mission-layout";

vi.mock("next/navigation", () => ({
  usePathname: () => "/governance"
}));

describe("MissionLayout", () => {
  it("shows all navigation links and highlights active route", () => {
    render(
      <MissionLayout>
        <div>child</div>
      </MissionLayout>
    );

    expect(screen.getByRole("link", { name: /command dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /decision console/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /governance control/i })).toHaveAttribute(
      "href",
      "/governance"
    );
    expect(screen.getByText("環境")).toBeInTheDocument();
    expect(screen.getByText("最新イベント")).toBeInTheDocument();
    expect(screen.getByText("稼働中")).toBeInTheDocument();
    expect(screen.getByText("可読性を優先した運用ビュー")).toBeInTheDocument();
  });
});
