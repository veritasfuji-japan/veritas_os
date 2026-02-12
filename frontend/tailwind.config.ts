import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "../packages/design-system/src/**/*.{ts,tsx}"
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        background: "hsl(var(--ds-color-background))",
        foreground: "hsl(var(--ds-color-foreground))",
        surface: {
          DEFAULT: "hsl(var(--ds-color-surface))",
          foreground: "hsl(var(--ds-color-surface-foreground))"
        },
        primary: {
          DEFAULT: "hsl(var(--ds-color-primary))",
          foreground: "hsl(var(--ds-color-primary-foreground))"
        },
        muted: {
          DEFAULT: "hsl(var(--ds-color-muted))",
          foreground: "hsl(var(--ds-color-muted-foreground))"
        },
        border: "hsl(var(--ds-color-border))"
      },
      fontFamily: {
        sans: ["var(--ds-font-sans)"],
        mono: ["var(--ds-font-mono)"]
      },
      borderRadius: {
        sm: "var(--ds-radius-sm)",
        md: "var(--ds-radius-md)",
        lg: "var(--ds-radius-lg)"
      },
      boxShadow: {
        sm: "var(--ds-shadow-sm)",
        md: "var(--ds-shadow-md)",
        lg: "var(--ds-shadow-lg)"
      },
      zIndex: {
        base: "var(--ds-z-base)",
        nav: "var(--ds-z-nav)",
        overlay: "var(--ds-z-overlay)",
        toast: "var(--ds-z-toast)",
        modal: "var(--ds-z-modal)"
      }
    }
  },
  plugins: []
};

export default config;
