import { describe, expect, it } from "vitest";

import { formatBytes } from "@/lib/format";

describe("formatBytes", () => {
  it("formats sub-kilobyte sizes as whole bytes", () => {
    expect(formatBytes(500)).toBe("500 Б");
  });

  it("formats kilobytes", () => {
    expect(formatBytes(2048)).toBe("2 КБ");
  });

  it("formats megabytes with one decimal below 10", () => {
    expect(formatBytes(4.5 * 1024 * 1024)).toBe("4.5 МБ");
  });

  it("formats megabytes without a decimal at or above 10", () => {
    expect(formatBytes(45 * 1024 * 1024)).toBe("45 МБ");
  });

  it("formats gigabytes", () => {
    expect(formatBytes(2 * 1024 * 1024 * 1024)).toBe("2 ГБ");
  });

  it("caps at gigabytes for very large sizes", () => {
    expect(formatBytes(3 * 1024 * 1024 * 1024 * 1024)).toBe("3072 ГБ");
  });
});
