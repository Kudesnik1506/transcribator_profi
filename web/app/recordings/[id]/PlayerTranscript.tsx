"use client";

import { useEffect, useRef, useState } from "react";

import { findActiveSegmentIndex } from "@/lib/player";

type Segment = {
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
  mediaUrl,
  contentType,
  segments,
}: {
  mediaUrl: string;
  contentType: string;
  segments: Segment[];
}) {
  const mediaRef = useRef<HTMLVideoElement & HTMLAudioElement>(null);
  const paragraphRefs = useRef<(HTMLParagraphElement | null)[]>([]);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [mediaUnavailable, setMediaUnavailable] = useState(false);

  function handleTimeUpdate() {
    const el = mediaRef.current;
    if (!el) return;
    setActiveIndex(findActiveSegmentIndex(segments, el.currentTime * 1000));
  }

  useEffect(() => {
    if (activeIndex < 0) return;
    paragraphRefs.current[activeIndex]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activeIndex]);

  function handleSeek(startMs: number) {
    const el = mediaRef.current;
    if (!el) return;
    el.currentTime = startMs / 1000;
    el.play().catch(() => {
      // autoplay can be blocked by the browser — the user can still press play manually
    });
  }

  const isVideo = contentType.startsWith("video/");

  return (
    <div className="flex flex-col gap-4">
      {mediaUnavailable ? (
        <p className="rounded-lg bg-zinc-100 px-4 py-3 text-sm text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          Исходный файл удалён — медиа хранится 30 дней после загрузки. Текст ниже остаётся доступен.
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

      <div className="flex flex-col gap-1">
        {segments.map((segment, index) => (
          <p
            key={index}
            ref={(node) => {
              paragraphRefs.current[index] = node;
            }}
            onClick={() => handleSeek(segment.start_ms)}
            className={`cursor-pointer rounded px-2 py-1 transition-colors ${
              index === activeIndex
                ? "bg-foreground/10 text-black dark:bg-zinc-100/10 dark:text-zinc-50"
                : "text-zinc-700 dark:text-zinc-300"
            }`}
          >
            <span className="mr-2 font-mono text-sm text-zinc-400">{formatTimestamp(segment.start_ms)}</span>
            {segment.text}
          </p>
        ))}
      </div>
    </div>
  );
}
