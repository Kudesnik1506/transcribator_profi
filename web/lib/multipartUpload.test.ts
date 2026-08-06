import { describe, expect, it } from "vitest";

import { computeParts, fileFingerprint, missingParts } from "@/lib/multipartUpload";

describe("computeParts", () => {
  it("splits a file into equal parts with the last part shorter", () => {
    const parts = computeParts(40, 16);

    expect(parts).toEqual([
      { partNumber: 1, start: 0, end: 16 },
      { partNumber: 2, start: 16, end: 32 },
      { partNumber: 3, start: 32, end: 40 },
    ]);
  });

  it("returns a single part when the file is smaller than part size", () => {
    const parts = computeParts(5, 16);

    expect(parts).toEqual([{ partNumber: 1, start: 0, end: 5 }]);
  });

  it("returns exactly one part per boundary when file size is an exact multiple", () => {
    const parts = computeParts(32, 16);

    expect(parts).toHaveLength(2);
    expect(parts[1]).toEqual({ partNumber: 2, start: 16, end: 32 });
  });
});

describe("missingParts", () => {
  it("returns parts whose number is not in the uploaded set", () => {
    const all = [
      { partNumber: 1, start: 0, end: 16 },
      { partNumber: 2, start: 16, end: 32 },
      { partNumber: 3, start: 32, end: 40 },
    ];

    const missing = missingParts(all, new Set([1]));

    expect(missing.map((p) => p.partNumber)).toEqual([2, 3]);
  });

  it("returns empty when everything is already uploaded", () => {
    const all = [{ partNumber: 1, start: 0, end: 16 }];

    expect(missingParts(all, new Set([1]))).toEqual([]);
  });
});

describe("fileFingerprint", () => {
  it("combines name, size and lastModified into a stable string", () => {
    const fingerprint = fileFingerprint({ name: "a.mp4", size: 1234, lastModified: 999 });

    expect(fingerprint).toBe("a.mp4:1234:999");
  });

  it("differs when any field differs", () => {
    const a = fileFingerprint({ name: "a.mp4", size: 1234, lastModified: 999 });
    const b = fileFingerprint({ name: "a.mp4", size: 1235, lastModified: 999 });

    expect(a).not.toBe(b);
  });
});
