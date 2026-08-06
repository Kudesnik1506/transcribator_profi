export type TimedSegment = {
  start_ms: number;
  end_ms: number;
};

export function findActiveSegmentIndex(segments: TimedSegment[], currentTimeMs: number): number {
  if (segments.length === 0) return -1;
  if (currentTimeMs < segments[0].start_ms) return -1;

  for (let i = 0; i < segments.length; i++) {
    if (currentTimeMs >= segments[i].start_ms && currentTimeMs < segments[i].end_ms) {
      return i;
    }
  }

  return segments.length - 1;
}
