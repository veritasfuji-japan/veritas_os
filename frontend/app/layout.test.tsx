import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RootLayout, { metadata } from "./layout";

vi.mock("@veritas/design-system", () => ({
  ThemeStyles: () => <style data-testid="theme-styles" />,
  applyThemeClass: () => "theme-light",
}));
vi.mock("../components/mission-layout", () => ({
  MissionLayout: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="mission-layout">{children}</div>
  ),
}));
vi.mock("../components/i18n-provider", () => ({
  I18nProvider: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="i18n-provider">{children}</div>
  ),
}));
vi.mock("./globals.css", () => ({}));

describe("RootLayout", () => {
  it("renders children wrapped in I18nProvider and MissionLayout", () => {
    render(<RootLayout><span data-testid="child">hello</span></RootLayout>);

    const i18n = screen.getByTestId("i18n-provider");
    const missionLayout = screen.getByTestId("mission-layout");
    const child = screen.getByTestId("child");

    expect(i18n).toBeInTheDocument();
    expect(missionLayout).toBeInTheDocument();
    expect(child).toBeInTheDocument();

    // MissionLayout is inside I18nProvider
    expect(i18n).toContainElement(missionLayout);
    // Child is inside MissionLayout
    expect(missionLayout).toContainElement(child);
  });

  it("exports correct metadata", () => {
    expect(metadata.title).toBe("Mission Control IA");
    expect(metadata.description).toBe("Decision Governance and Bind-Boundary Control Plane operations console");
    expect(metadata.icons).toEqual({ icon: "/icon.svg" });
  });

  it("sets lang='ja' on html element", () => {
    const { container } = render(
      <RootLayout><span>test</span></RootLayout>
    );

    // In JSDOM the <html> rendered inside the test may appear as a child node
    // since RootLayout returns an <html> element. Check the rendered output.
    const rendered = container.innerHTML;
    expect(rendered).toContain('lang="ja"');
  });
});
