export const tokens = {
  color: {
    background: "hsl(var(--background))",
    foreground: "hsl(var(--foreground))",
    primary: "hsl(var(--primary))"
  },
  radius: {
    base: "0.5rem"
  }
} as const;

export type ThemeMode = "light" | "dark";

export function applyThemeClass(mode: ThemeMode): string {
  return mode === "dark" ? "dark" : "";
}
