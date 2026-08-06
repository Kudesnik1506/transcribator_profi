import { describe, expect, it } from "vitest";

import { findActiveSegmentIndex } from "@/lib/player";

const segments = [
  { start_ms: 0, end_ms: 1000 },
  { start_ms: 1000, end_ms: 2500 },
  { start_ms: 2500, end_ms: 4000 },
];

describe("findActiveSegmentIndex", () => {
  it("finds the segment containing the current time", () => {
    expect(findActiveSegmentIndex(segments, 1500)).toBe(1);
  });

  it("returns the first segment at time zero", () => {
    expect(findActiveSegmentIndex(segments, 0)).toBe(0);
  });

  it("returns the boundary segment when time equals a start boundary", () => {
    expect(findActiveSegmentIndex(segments, 2500)).toBe(2);
  });

  it("returns -1 when time is before all segments", () => {
    expect(findActiveSegmentIndex(segments, -100)).toBe(-1);
  });

  it("returns the last segment when time is past the end", () => {
    expect(findActiveSegmentIndex(segments, 10_000)).toBe(2);
  });

  it("returns -1 for an empty segment list", () => {
    expect(findActiveSegmentIndex([], 500)).toBe(-1);
  });
});
