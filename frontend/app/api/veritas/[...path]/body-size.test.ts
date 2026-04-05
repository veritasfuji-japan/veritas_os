import { describe, it, expect } from "vitest";
import { getBodySizeBytes } from "./body-size";

describe("getBodySizeBytes", () => {
  it("returns correct byte length for ASCII strings", () => {
    expect(getBodySizeBytes("hello")).toBe(5);
    expect(getBodySizeBytes("")).toBe(0);
  });

  it("returns UTF-8 byte length for multi-byte characters", () => {
    // Japanese characters are 3 bytes each in UTF-8
    expect(getBodySizeBytes("あ")).toBe(3);
    expect(getBodySizeBytes("日本語")).toBe(9);
  });

  it("returns correct byte length for emoji", () => {
    // Most emoji are 4 bytes in UTF-8
    expect(getBodySizeBytes("😀")).toBe(4);
  });

  it("handles mixed ASCII and multi-byte", () => {
    expect(getBodySizeBytes("hi あ")).toBe(2 + 1 + 3); // "hi" + space + "あ"
  });
});
