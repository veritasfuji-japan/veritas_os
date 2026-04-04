import { describe, it, expect } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { I18nProvider, useI18n } from "./i18n-provider";

function TestConsumer() {
  const { language, t, setLanguage } = useI18n();
  return (
    <div>
      <span data-testid="lang">{language}</span>
      <span data-testid="translated">{t("日本語", "English")}</span>
      <button type="button" onClick={() => setLanguage("en")}>Switch to EN</button>
      <button type="button" onClick={() => setLanguage("ja")}>Switch to JA</button>
    </div>
  );
}

describe("I18nProvider", () => {
  it("defaults to Japanese", () => {
    render(
      <I18nProvider>
        <TestConsumer />
      </I18nProvider>,
    );
    expect(screen.getByTestId("lang").textContent).toBe("ja");
    expect(screen.getByTestId("translated").textContent).toBe("日本語");
  });

  it("switches language to English", async () => {
    render(
      <I18nProvider>
        <TestConsumer />
      </I18nProvider>,
    );
    await act(async () => {
      screen.getByText("Switch to EN").click();
    });
    expect(screen.getByTestId("lang").textContent).toBe("en");
    expect(screen.getByTestId("translated").textContent).toBe("English");
  });

  it("persists language to localStorage", async () => {
    render(
      <I18nProvider>
        <TestConsumer />
      </I18nProvider>,
    );
    await act(async () => {
      screen.getByText("Switch to EN").click();
    });
    expect(window.localStorage.getItem("veritas_language")).toBe("en");
  });
});

describe("useI18n outside provider", () => {
  it("uses default context values", () => {
    render(<TestConsumer />);
    expect(screen.getByTestId("lang").textContent).toBe("ja");
  });
});
