/**
 * Design token and theme definitions for Veritas UI.
 *
 * Layer0 responsibilities:
 * - Tokenized primitives (color / typography / spacing / radius / shadow / z-index)
 * - Light / dark CSS variable maps
 * - Accessibility utility variables (focus ring)
 * - Semantic color tokens (success / warning / danger / info)
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
    focusRing: "hsl(var(--ds-color-focus-ring))",
    success: "hsl(var(--ds-color-success))",
    successForeground: "hsl(var(--ds-color-success-foreground))",
    warning: "hsl(var(--ds-color-warning))",
    warningForeground: "hsl(var(--ds-color-warning-foreground))",
    danger: "hsl(var(--ds-color-danger))",
    dangerForeground: "hsl(var(--ds-color-danger-foreground))",
    info: "hsl(var(--ds-color-info))",
    infoForeground: "hsl(var(--ds-color-info-foreground))",
    sidebar: "hsl(var(--ds-color-sidebar))",
    sidebarBorder: "hsl(var(--ds-color-sidebar-border))",
    sidebarForeground: "hsl(var(--ds-color-sidebar-foreground))",
    sidebarMuted: "hsl(var(--ds-color-sidebar-muted))",
  },
  typography: {
    sans: "var(--ds-font-sans)",
    mono: "var(--ds-font-mono)",
    size: {
      "2xs": "0.6875rem",
      xs: "0.75rem",
      sm: "0.875rem",
      md: "1rem",
      lg: "1.125rem",
      xl: "1.25rem",
      "2xl": "1.5rem",
    },
    lineHeight: {
      compact: "1.3",
      normal: "1.5",
      relaxed: "1.65"
    },
    weight: {
      normal: "400",
      medium: "500",
      semibold: "600",
      bold: "700",
    }
  },
  spacing: {
    1: "0.25rem",
    2: "0.5rem",
    3: "0.75rem",
    4: "1rem",
    5: "1.25rem",
    6: "1.5rem",
    8: "2rem",
    10: "2.5rem",
    12: "3rem",
    16: "4rem",
  },
  radius: {
    xs: "0.25rem",
    sm: "0.375rem",
    md: "0.5rem",
    lg: "0.75rem",
    xl: "1rem",
    full: "9999px",
  },
  shadow: {
    xs: "0 1px 2px 0 rgb(0 0 0 / 0.08)",
    sm: "0 1px 3px 0 rgb(0 0 0 / 0.12), 0 1px 2px -1px rgb(0 0 0 / 0.08)",
    md: "0 4px 12px -2px rgb(0 0 0 / 0.16), 0 2px 6px -2px rgb(0 0 0 / 0.1)",
    lg: "0 10px 28px -6px rgb(0 0 0 / 0.22), 0 4px 12px -4px rgb(0 0 0 / 0.14)",
    xl: "0 20px 48px -10px rgb(0 0 0 / 0.3), 0 8px 20px -8px rgb(0 0 0 / 0.18)",
    glow: "0 0 0 1px hsl(var(--ds-color-primary) / 0.3), 0 4px 16px hsl(var(--ds-color-primary) / 0.2)",
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
  "--ds-font-sans": "'Inter', 'Noto Sans JP', 'Segoe UI', system-ui, sans-serif",
  "--ds-font-mono": "'JetBrains Mono', 'SFMono-Regular', ui-monospace, monospace",
  "--ds-spacing-1": tokens.spacing[1],
  "--ds-spacing-2": tokens.spacing[2],
  "--ds-spacing-3": tokens.spacing[3],
  "--ds-spacing-4": tokens.spacing[4],
  "--ds-spacing-5": tokens.spacing[5],
  "--ds-spacing-6": tokens.spacing[6],
  "--ds-spacing-8": tokens.spacing[8],
  "--ds-spacing-10": tokens.spacing[10],
  "--ds-spacing-12": tokens.spacing[12],
  "--ds-spacing-16": tokens.spacing[16],
  "--ds-radius-xs": tokens.radius.xs,
  "--ds-radius-sm": tokens.radius.sm,
  "--ds-radius-md": tokens.radius.md,
  "--ds-radius-lg": tokens.radius.lg,
  "--ds-radius-xl": tokens.radius.xl,
  "--ds-radius-full": tokens.radius.full,
  "--ds-shadow-xs": tokens.shadow.xs,
  "--ds-shadow-sm": tokens.shadow.sm,
  "--ds-shadow-md": tokens.shadow.md,
  "--ds-shadow-lg": tokens.shadow.lg,
  "--ds-shadow-xl": tokens.shadow.xl,
  "--ds-shadow-glow": tokens.shadow.glow,
  "--ds-z-base": tokens.zIndex.base,
  "--ds-z-nav": tokens.zIndex.nav,
  "--ds-z-overlay": tokens.zIndex.overlay,
  "--ds-z-toast": tokens.zIndex.toast,
  "--ds-z-modal": tokens.zIndex.modal
};

const lightVariables: CssVariableMap = {
  "--ds-color-background": "220 20% 97%",
  "--ds-color-foreground": "222 47% 11%",
  "--ds-color-surface": "0 0% 100%",
  "--ds-color-surface-foreground": "222 47% 11%",
  "--ds-color-primary": "221 83% 53%",
  "--ds-color-primary-foreground": "0 0% 100%",
  "--ds-color-muted": "220 14% 92%",
  "--ds-color-muted-foreground": "220 9% 46%",
  "--ds-color-border": "220 13% 87%",
  "--ds-color-focus-ring": "221 83% 53%",
  "--ds-color-success": "142 72% 29%",
  "--ds-color-success-foreground": "0 0% 100%",
  "--ds-color-warning": "32 95% 44%",
  "--ds-color-warning-foreground": "0 0% 100%",
  "--ds-color-danger": "0 72% 51%",
  "--ds-color-danger-foreground": "0 0% 100%",
  "--ds-color-info": "199 89% 38%",
  "--ds-color-info-foreground": "0 0% 100%",
  "--ds-color-sidebar": "222 30% 12%",
  "--ds-color-sidebar-border": "222 20% 20%",
  "--ds-color-sidebar-foreground": "215 25% 85%",
  "--ds-color-sidebar-muted": "220 15% 55%",
};

const darkVariables: CssVariableMap = {
  "--ds-color-background": "224 28% 7%",
  "--ds-color-foreground": "215 30% 91%",
  "--ds-color-surface": "224 25% 10%",
  "--ds-color-surface-foreground": "215 30% 91%",
  "--ds-color-primary": "217 91% 60%",
  "--ds-color-primary-foreground": "222 47% 11%",
  "--ds-color-muted": "222 18% 16%",
  "--ds-color-muted-foreground": "218 14% 58%",
  "--ds-color-border": "220 15% 22%",
  "--ds-color-focus-ring": "217 91% 60%",
  "--ds-color-success": "142 71% 45%",
  "--ds-color-success-foreground": "142 80% 10%",
  "--ds-color-warning": "38 92% 50%",
  "--ds-color-warning-foreground": "38 95% 10%",
  "--ds-color-danger": "0 84% 60%",
  "--ds-color-danger-foreground": "0 80% 10%",
  "--ds-color-info": "199 89% 48%",
  "--ds-color-info-foreground": "199 80% 10%",
  "--ds-color-sidebar": "222 35% 6%",
  "--ds-color-sidebar-border": "220 18% 15%",
  "--ds-color-sidebar-foreground": "215 20% 78%",
  "--ds-color-sidebar-muted": "220 12% 45%",
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
