import { describe, expect, it } from "vitest";
import { sanitizeText } from "./utils";

describe("sanitizeText", () => {
  it("returns plain text unchanged", () => {
    expect(sanitizeText("hello world")).toBe("hello world");
  });

  it("strips HTML tags", () => {
    expect(sanitizeText('<script>alert("xss")</script>')).toBe('alert("xss")');
  });

  it("strips self-closing tags", () => {
    expect(sanitizeText('<img src="x" onerror="alert(1)" />')).toBe("");
  });

  it("strips null bytes", () => {
    expect(sanitizeText("hello\0world")).toBe("helloworld");
  });

  it("strips nested tags formed after inner tag removal", () => {
    expect(sanitizeText("x<b>y")).toBe("xy");
    // Multiple tags in sequence
    expect(sanitizeText("<a><b>safe</b></a>")).toBe("safe");
  });

  it("handles non-string values", () => {
    expect(sanitizeText(42)).toBe("42");
    expect(sanitizeText(null)).toBe("");
    expect(sanitizeText(undefined)).toBe("");
  });
});
