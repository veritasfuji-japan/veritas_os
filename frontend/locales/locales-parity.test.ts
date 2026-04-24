import { describe, expect, it } from "vitest";

import { en } from "./en";
import { ja } from "./ja";

describe("locale parity", () => {
  it("keeps English and Japanese locale keys in sync", () => {
    const enKeys = Object.keys(en).sort();
    const jaKeys = Object.keys(ja).sort();
    expect(enKeys).toEqual(jaKeys);
  });

  it("keeps Japanese locale values non-empty", () => {
    for (const [key, value] of Object.entries(ja)) {
      expect(value.trim(), `ja locale value is empty: ${key}`).not.toBe("");
    }
  });
});
