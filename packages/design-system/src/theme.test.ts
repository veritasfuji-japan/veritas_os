import { applyThemeClass, tokens } from "./theme";

describe("theme", () => {
  it("provides tokens and theme classes", () => {
    expect(tokens.radius.base).toBe("0.5rem");
    expect(applyThemeClass("light")).toBe("");
    expect(applyThemeClass("dark")).toBe("dark");
  });
});
