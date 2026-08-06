"use client";

import { use, useEffect, useState } from "react";

import { getRecording, type RecordingDetail } from "@/lib/api";

const STATUS_LABELS: Record<string, string> = {
  queued: "В очереди",
  extracting: "Извлекаем аудио",
  transcribing: "Распознаём речь",
  summarizing: "Готовим сводку",
  done: "Готово",
  partial: "Частично обработана",
  failed: "Ошибка обработки",
};

const TERMINAL_STATUSES = new Set(["done", "partial", "failed"]);

function formatTimestamp(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export default function RecordingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [recording, setRecording] = useState<RecordingDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const data = await getRecording(id);
        if (cancelled) return;
        setRecording(data);
        if (!TERMINAL_STATUSES.has(data.status)) {
          timer = setTimeout(poll, 3000);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Не удалось загрузить Запись");
      }
    }

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [id]);

  if (error) {
    return <main className="mx-auto max-w-3xl px-6 py-12 text-red-600">{error}</main>;
  }

  if (!recording) {
    return <main className="mx-auto max-w-3xl px-6 py-12 text-zinc-500">Загрузка…</main>;
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-12">
      <div>
        <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">{recording.original_filename}</h1>
        <p className="mt-1 text-zinc-500">{STATUS_LABELS[recording.status] ?? recording.status}</p>
        {recording.status === "failed" && recording.error_message && (
          <p className="mt-2 text-sm text-red-600">{recording.error_message}</p>
        )}
      </div>

      {recording.summary && (
        <section>
          <h2 className="mb-3 text-lg font-medium text-black dark:text-zinc-50">Сводка</h2>
          <ul className="list-disc space-y-1 pl-5 text-zinc-700 dark:text-zinc-300">
            {recording.summary.items.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      {recording.segments.length > 0 && (
        <section>
          <h2 className="mb-3 text-lg font-medium text-black dark:text-zinc-50">Транскрипт</h2>
          <div className="flex flex-col gap-2">
            {recording.segments.map((segment, index) => (
              <p key={index} className="text-zinc-700 dark:text-zinc-300">
                <span className="mr-2 font-mono text-sm text-zinc-400">{formatTimestamp(segment.start_ms)}</span>
                {segment.text}
              </p>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
