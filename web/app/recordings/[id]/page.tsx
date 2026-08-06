"use client";

import { use, useEffect, useState } from "react";

import { getRecording, retryRecording, type RecordingDetail } from "@/lib/api";
import { IN_PROGRESS_STATUSES, TERMINAL_STATUSES, statusLabel } from "@/lib/recordingStatus";

import { Dialog } from "./Dialog";
import { PlayerTranscript } from "./PlayerTranscript";

export default function RecordingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [recording, setRecording] = useState<RecordingDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);

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

  async function handleRetry() {
    setRetrying(true);
    try {
      await retryRecording(id);
      const data = await getRecording(id);
      setRecording(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось запустить повтор");
    } finally {
      setRetrying(false);
    }
  }

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
        <p className="mt-1 text-zinc-500">{statusLabel(recording.status)}</p>

        {IN_PROGRESS_STATUSES.has(recording.status) && (
          <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
            <div
              className="h-full rounded-full bg-foreground transition-all"
              style={{ width: `${recording.progress_percent}%` }}
            />
          </div>
        )}

        {recording.status === "failed" && recording.error_message && (
          <p className="mt-2 text-sm text-red-600">{recording.error_message}</p>
        )}

        {recording.status === "partial" && (
          <div className="mt-3 flex items-center gap-3">
            <p className="text-sm text-amber-600">
              Часть записи не удалось распознать — ниже показано то, что получилось.
            </p>
            <button
              onClick={handleRetry}
              disabled={retrying}
              className="shrink-0 rounded-full border border-solid border-black/[.08] px-4 py-1.5 text-sm transition-colors hover:bg-black/[.04] disabled:opacity-50 dark:border-white/[.145] dark:hover:bg-[#1a1a1a]"
            >
              {retrying ? "Запускаем…" : "Допровести"}
            </button>
          </div>
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
          <PlayerTranscript
            mediaUrl={recording.media_url}
            contentType={recording.content_type}
            segments={recording.segments}
          />
        </section>
      )}

      {(recording.status === "done" || recording.status === "partial") && recording.segments.length > 0 && (
        <Dialog recordingId={recording.id} />
      )}
    </main>
  );
}
