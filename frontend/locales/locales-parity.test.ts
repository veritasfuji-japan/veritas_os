import { describe, expect, it } from "vitest";
import { en } from "./en";
import { ja } from "./ja";

describe("locale parity", () => {
  it("keeps ja and en locale keys aligned", () => {
    const jaKeys = Object.keys(ja).sort();
    const enKeys = Object.keys(en).sort();

    expect(enKeys).toEqual(jaKeys);
  });
});
