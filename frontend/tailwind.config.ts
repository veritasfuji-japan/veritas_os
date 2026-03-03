import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./features/**/*.{ts,tsx}",
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
        border: "hsl(var(--ds-color-border))",
        success: {
          DEFAULT: "hsl(var(--ds-color-success))",
          foreground: "hsl(var(--ds-color-success-foreground))"
        },
        warning: {
          DEFAULT: "hsl(var(--ds-color-warning))",
          foreground: "hsl(var(--ds-color-warning-foreground))"
        },
        danger: {
          DEFAULT: "hsl(var(--ds-color-danger))",
          foreground: "hsl(var(--ds-color-danger-foreground))"
        },
        info: {
          DEFAULT: "hsl(var(--ds-color-info))",
          foreground: "hsl(var(--ds-color-info-foreground))"
        },
        sidebar: {
          DEFAULT: "hsl(var(--ds-color-sidebar))",
          border: "hsl(var(--ds-color-sidebar-border))",
          foreground: "hsl(var(--ds-color-sidebar-foreground))",
          muted: "hsl(var(--ds-color-sidebar-muted))"
        }
      },
      fontFamily: {
        sans: ["var(--ds-font-sans)"],
        mono: ["var(--ds-font-mono)"]
      },
      borderRadius: {
        xs: "var(--ds-radius-xs)",
        sm: "var(--ds-radius-sm)",
        md: "var(--ds-radius-md)",
        lg: "var(--ds-radius-lg)",
        xl: "var(--ds-radius-xl)"
      },
      boxShadow: {
        xs: "var(--ds-shadow-xs)",
        sm: "var(--ds-shadow-sm)",
        md: "var(--ds-shadow-md)",
        lg: "var(--ds-shadow-lg)",
        xl: "var(--ds-shadow-xl)",
        glow: "var(--ds-shadow-glow)"
      },
      zIndex: {
        base: "var(--ds-z-base)",
        nav: "var(--ds-z-nav)",
        overlay: "var(--ds-z-overlay)",
        toast: "var(--ds-z-toast)",
        modal: "var(--ds-z-modal)"
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 0.2s ease-out",
        "slide-up": "slideUp 0.25s ease-out",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        }
      }
    }
  },
  plugins: []
};

export default config;
