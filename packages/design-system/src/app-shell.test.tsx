import type { ReactNode, JSX } from "react";
import { AppShell } from "./app-shell";

function collectText(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }
  if (!node || typeof node === "boolean") {
    return "";
  }
  if (Array.isArray(node)) {
    return node.map((child) => collectText(child)).join(" ");
  }
  if (typeof node === "object" && "props" in node) {
    const props = (node as JSX.Element).props as { children?: ReactNode };
    return collectText(props.children);
  }
  return "";
}

describe("AppShell", () => {
  it("uses an english default skip-link label", () => {
    const tree = AppShell({
      title: "Dashboard",
      children: <div>Content</div>
    });

    expect(collectText(tree)).toContain("Skip to main content");
  });

  it("allows overriding the skip-link label for locale support", () => {
    const tree = AppShell({
      title: "ダッシュボード",
      skipLinkLabel: "メインコンテンツへスキップ",
      children: <div>コンテンツ</div>
    });

    expect(collectText(tree)).toContain("メインコンテンツへスキップ");
  });
});
