import { render, screen } from "@testing-library/react";
import CommandDashboardPage from "./page";
import { I18nProvider } from "../components/i18n";

describe("CommandDashboardPage", () => {
  it("renders dashboard skeleton content", () => {
    render(
      <I18nProvider>
        <CommandDashboardPage />
      </I18nProvider>
    );

    expect(screen.getByText("Command Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Uptime Lattice")).toBeInTheDocument();
  });
});
