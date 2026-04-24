import { describe, expect, it } from "vitest";

import { en } from "./en";
import { ja } from "./ja";

describe("locale parity", () => {
  it("keeps English and Japanese locale key sets identical", () => {
    const enKeys = Object.keys(en).sort();
    const jaKeys = Object.keys(ja).sort();

    expect(jaKeys).toEqual(enKeys);
  });

  it("ensures Japanese locale values are present", () => {
    for (const [key, value] of Object.entries(ja)) {
      expect(value, `ja locale value is empty: ${key}`).toBeTruthy();
      expect(value.trim(), `ja locale value is blank: ${key}`).not.toBe("");
    }
  });
});
