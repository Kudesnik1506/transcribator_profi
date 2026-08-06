import { describe, expect, it } from "vitest";

import { pluralizeRu } from "@/lib/plural";

describe("pluralizeRu", () => {
  const forms: [string, string, string] = ["совпадение", "совпадения", "совпадений"];

  it("uses the singular form for 1", () => {
    expect(pluralizeRu(1, forms)).toBe("совпадение");
  });

  it("uses the few form for 2-4", () => {
    expect(pluralizeRu(2, forms)).toBe("совпадения");
    expect(pluralizeRu(3, forms)).toBe("совпадения");
    expect(pluralizeRu(4, forms)).toBe("совпадения");
  });

  it("uses the many form for 5-20", () => {
    expect(pluralizeRu(5, forms)).toBe("совпадений");
    expect(pluralizeRu(11, forms)).toBe("совпадений");
    expect(pluralizeRu(12, forms)).toBe("совпадений");
    expect(pluralizeRu(14, forms)).toBe("совпадений");
    expect(pluralizeRu(20, forms)).toBe("совпадений");
  });

  it("uses the singular form for numbers ending in 1 (except 11)", () => {
    expect(pluralizeRu(21, forms)).toBe("совпадение");
    expect(pluralizeRu(31, forms)).toBe("совпадение");
    expect(pluralizeRu(101, forms)).toBe("совпадение");
  });

  it("uses the few form for numbers ending in 2-4 (except 12-14)", () => {
    expect(pluralizeRu(22, forms)).toBe("совпадения");
    expect(pluralizeRu(23, forms)).toBe("совпадения");
    expect(pluralizeRu(24, forms)).toBe("совпадения");
  });

  it("uses the many form for numbers ending in 0 or 5-9", () => {
    expect(pluralizeRu(25, forms)).toBe("совпадений");
    expect(pluralizeRu(30, forms)).toBe("совпадений");
  });
});
