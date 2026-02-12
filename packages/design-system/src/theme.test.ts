import { applyThemeClass, createThemeCss, tokens } from "./theme";

describe("theme", () => {
  it("provides token groups required by layer0", () => {
    expect(tokens.color.background).toContain("--ds-color-background");
    expect(tokens.typography.mono).toBe("var(--ds-font-mono)");
    expect(tokens.spacing[4]).toBe("1rem");
    expect(tokens.radius.md).toBe("0.5rem");
    expect(tokens.shadow.md).toContain("rgb");
    expect(tokens.zIndex.modal).toBe("60");
  });

  it("creates light and dark css variable maps", () => {
    const css = createThemeCss();

    expect(css).toContain(":root {");
    expect(css).toContain(".dark {");
    expect(css).toContain("--ds-color-focus-ring");
    expect(css).toContain("--ds-font-mono");
  });

  it("provides theme classes", () => {
    expect(applyThemeClass("light")).toBe("");
    expect(applyThemeClass("dark")).toBe("dark");
  });
});
