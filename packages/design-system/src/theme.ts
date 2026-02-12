/**
 * Design token and theme definitions for Veritas UI.
 *
 * Layer0 responsibilities:
 * - Tokenized primitives (color / typography / spacing / radius / shadow / z-index)
 * - Light / dark CSS variable maps
 * - Accessibility utility variables (focus ring)
 */
export const tokens = {
  color: {
    background: "hsl(var(--ds-color-background))",
    foreground: "hsl(var(--ds-color-foreground))",
    surface: "hsl(var(--ds-color-surface))",
    surfaceForeground: "hsl(var(--ds-color-surface-foreground))",
    primary: "hsl(var(--ds-color-primary))",
    primaryForeground: "hsl(var(--ds-color-primary-foreground))",
    muted: "hsl(var(--ds-color-muted))",
    mutedForeground: "hsl(var(--ds-color-muted-foreground))",
    border: "hsl(var(--ds-color-border))",
    focusRing: "hsl(var(--ds-color-focus-ring))"
  },
  typography: {
    sans: "var(--ds-font-sans)",
    mono: "var(--ds-font-mono)",
    size: {
      xs: "0.75rem",
      sm: "0.875rem",
      md: "1rem",
      lg: "1.125rem",
      xl: "1.25rem"
    },
    lineHeight: {
      compact: "1.3",
      normal: "1.5",
      relaxed: "1.65"
    }
  },
  spacing: {
    1: "0.25rem",
    2: "0.5rem",
    3: "0.75rem",
    4: "1rem",
    6: "1.5rem",
    8: "2rem",
    12: "3rem"
  },
  radius: {
    sm: "0.375rem",
    md: "0.5rem",
    lg: "0.75rem"
  },
  shadow: {
    sm: "0 1px 2px 0 rgb(0 0 0 / 0.12)",
    md: "0 4px 10px -2px rgb(0 0 0 / 0.18)",
    lg: "0 10px 24px -8px rgb(0 0 0 / 0.24)"
  },
  zIndex: {
    base: "1",
    nav: "20",
    overlay: "40",
    toast: "50",
    modal: "60"
  }
} as const;

export type ThemeMode = "light" | "dark";

type CssVariableMap = Record<string, string>;

const sharedVariables: CssVariableMap = {
  "--ds-font-sans": "Inter, 'Noto Sans JP', 'Segoe UI', sans-serif",
  "--ds-font-mono": "'JetBrains Mono', 'SFMono-Regular', ui-monospace, monospace",
  "--ds-spacing-1": tokens.spacing[1],
  "--ds-spacing-2": tokens.spacing[2],
  "--ds-spacing-3": tokens.spacing[3],
  "--ds-spacing-4": tokens.spacing[4],
  "--ds-spacing-6": tokens.spacing[6],
  "--ds-spacing-8": tokens.spacing[8],
  "--ds-spacing-12": tokens.spacing[12],
  "--ds-radius-sm": tokens.radius.sm,
  "--ds-radius-md": tokens.radius.md,
  "--ds-radius-lg": tokens.radius.lg,
  "--ds-shadow-sm": tokens.shadow.sm,
  "--ds-shadow-md": tokens.shadow.md,
  "--ds-shadow-lg": tokens.shadow.lg,
  "--ds-z-base": tokens.zIndex.base,
  "--ds-z-nav": tokens.zIndex.nav,
  "--ds-z-overlay": tokens.zIndex.overlay,
  "--ds-z-toast": tokens.zIndex.toast,
  "--ds-z-modal": tokens.zIndex.modal
};

const lightVariables: CssVariableMap = {
  "--ds-color-background": "0 0% 100%",
  "--ds-color-foreground": "224 71% 8%",
  "--ds-color-surface": "210 33% 98%",
  "--ds-color-surface-foreground": "224 71% 8%",
  "--ds-color-primary": "221 83% 53%",
  "--ds-color-primary-foreground": "210 40% 98%",
  "--ds-color-muted": "216 33% 94%",
  "--ds-color-muted-foreground": "218 18% 38%",
  "--ds-color-border": "214 29% 84%",
  "--ds-color-focus-ring": "221 83% 53%"
};

const darkVariables: CssVariableMap = {
  "--ds-color-background": "222 47% 7%",
  "--ds-color-foreground": "213 31% 91%",
  "--ds-color-surface": "223 33% 10%",
  "--ds-color-surface-foreground": "213 31% 91%",
  "--ds-color-primary": "217 91% 60%",
  "--ds-color-primary-foreground": "222 47% 11%",
  "--ds-color-muted": "218 24% 19%",
  "--ds-color-muted-foreground": "215 20% 71%",
  "--ds-color-border": "217 19% 25%",
  "--ds-color-focus-ring": "217 91% 60%"
};

function serializeVariables(selector: string, variables: CssVariableMap): string {
  const lines = Object.entries(variables).map(([key, value]) => `  ${key}: ${value};`);
  return `${selector} {\n${lines.join("\n")}\n}`;
}

export function createThemeCss(): string {
  return [
    serializeVariables(":root", { ...sharedVariables, ...lightVariables }),
    serializeVariables(".dark", darkVariables)
  ].join("\n\n");
}

export function applyThemeClass(mode: ThemeMode): string {
  return mode === "dark" ? "dark" : "";
}
