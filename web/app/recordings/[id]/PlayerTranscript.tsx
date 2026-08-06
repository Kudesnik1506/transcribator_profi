"use client";

import { useEffect, useRef, useState } from "react";

import { searchRecording } from "@/lib/api";
import { formatDate } from "@/lib/date";
import { findActiveSegmentIndex } from "@/lib/player";

type Segment = {
  id: string;
  start_ms: number;
  end_ms: number;
  text: string;
};

function formatTimestamp(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export function PlayerTranscript({
  recordingId,
  mediaUrl,
  mediaDeletedAt,
  contentType,
  segments,
}: {
  recordingId: string;
  mediaUrl: string | null;
  mediaDeletedAt: string | null;
  contentType: string;
  segments: Segment[];
}) {
  const mediaRef = useRef<HTMLVideoElement & HTMLAudioElement>(null);
  const paragraphRefs = useRef<(HTMLParagraphElement | null)[]>([]);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [mediaUnavailable, setMediaUnavailable] = useState(false);
  const unavailable = mediaUnavailable || mediaUrl === null;

  const [query, setQuery] = useState("");
  const [matchedIds, setMatchedIds] = useState<Set<string>>(new Set());
  const [matchCount, setMatchCount] = useState(0);
  const [searchError, setSearchError] = useState<string | null>(null);

  function handleTimeUpdate() {
    const el = mediaRef.current;
    if (!el) return;
    setActiveIndex(findActiveSegmentIndex(segments, el.currentTime * 1000));
  }

  useEffect(() => {
    if (activeIndex < 0) return;
    paragraphRefs.current[activeIndex]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activeIndex]);

  function seekTo(startMs: number) {
    const el = mediaRef.current;
    if (!el) return;
    el.currentTime = startMs / 1000;
  }

  function handleParagraphClick(startMs: number) {
    seekTo(startMs);
    mediaRef.current?.play().catch(() => {
      // autoplay can be blocked by the browser — the user can still press play manually
    });
  }

  useEffect(() => {
    let cancelled = false;
    const trimmed = query.trim();

    const timer = setTimeout(async () => {
      if (cancelled) return;

      if (!trimmed) {
        setMatchedIds(new Set());
        setMatchCount(0);
        setSearchError(null);
        return;
      }

      try {
        const result = await searchRecording(recordingId, trimmed);
        if (cancelled) return;
        setMatchedIds(new Set(result.matches.map((m) => m.segment_id)));
        setMatchCount(result.total);
        setSearchError(null);

        const firstMatch = result.matches[0];
        if (firstMatch) {
          const index = segments.findIndex((s) => s.id === firstMatch.segment_id);
          if (index >= 0) {
            setActiveIndex(index);
            seekTo(firstMatch.start_ms);
          }
        }
      } catch (err) {
        if (!cancelled) setSearchError(err instanceof Error ? err.message : "Поиск не удался");
      }
    }, 300);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, recordingId]);

  const isVideo = contentType.startsWith("video/");

  return (
    <div className="flex flex-col gap-4">
      {unavailable ? (
        <p className="rounded-lg bg-zinc-100 px-4 py-3 text-sm text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          {mediaDeletedAt
            ? `Исходный файл удалён ${formatDate(mediaDeletedAt)} по истечении срока хранения. Текст ниже остаётся доступен.`
            : "Исходный файл удалён — медиа хранится ограниченное время после загрузки. Текст ниже остаётся доступен."}
        </p>
      ) : isVideo ? (
        <video
          ref={mediaRef}
          src={mediaUrl}
          controls
          className="w-full rounded-lg"
          onTimeUpdate={handleTimeUpdate}
          onError={() => setMediaUnavailable(true)}
        />
      ) : (
        <audio
          ref={mediaRef}
          src={mediaUrl}
          controls
          className="w-full"
          onTimeUpdate={handleTimeUpdate}
          onError={() => setMediaUnavailable(true)}
        />
      )}

      <div className="flex items-center gap-3">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Поиск по записи…"
          className="flex-1 rounded-full border border-solid border-black/[.08] px-4 py-1.5 text-sm dark:border-white/[.145] dark:bg-zinc-900"
        />
        {query.trim() && (
          <span className="shrink-0 text-sm text-zinc-500">
            {matchCount > 0 ? `${matchCount} совпадений` : "ничего не найдено"}
          </span>
        )}
      </div>
      {searchError && <p className="text-sm text-red-600">{searchError}</p>}

      <div className="flex flex-col gap-1">
        {segments.map((segment, index) => (
          <p
            key={segment.id}
            ref={(node) => {
              paragraphRefs.current[index] = node;
            }}
            onClick={() => handleParagraphClick(segment.start_ms)}
            className={[
              "cursor-pointer rounded px-2 py-1 transition-colors",
              matchedIds.has(segment.id) ? "bg-yellow-200/60 dark:bg-yellow-500/20" : "",
              index === activeIndex ? "ring-2 ring-inset ring-foreground/40" : "",
              matchedIds.has(segment.id) || index === activeIndex
                ? "text-black dark:text-zinc-50"
                : "text-zinc-700 dark:text-zinc-300",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            <span className="mr-2 font-mono text-sm text-zinc-400">{formatTimestamp(segment.start_ms)}</span>
            {segment.text}
          </p>
        ))}
      </div>
    </div>
  );
}
