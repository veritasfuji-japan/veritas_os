import { createThemeCss } from "./theme";

/**
 * Injects design-system CSS variables so host applications can consume
 * tokenized light/dark themes without duplicating variable declarations.
 */
export function ThemeStyles(): JSX.Element {
  return <style id="veritas-design-system-theme">{createThemeCss()}</style>;
}
