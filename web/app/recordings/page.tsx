"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { listRecordings, type RecordingListItem } from "@/lib/api";
import { TERMINAL_STATUSES, statusLabel } from "@/lib/recordingStatus";
import { AuthGuard } from "@/components/AuthGuard";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function RecordingsListPage() {
  return (
    <AuthGuard>
      <RecordingsListPageContent />
    </AuthGuard>
  );
}

function RecordingsListPageContent() {
  const [recordings, setRecordings] = useState<RecordingListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const data = await listRecordings();
        if (cancelled) return;
        setRecordings(data);
        const hasActiveRecording = data.some((r) => !TERMINAL_STATUSES.has(r.status));
        if (hasActiveRecording) {
          timer = setTimeout(poll, 3000);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Не удалось загрузить список");
      }
    }

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-12">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">Мои Записи</h1>
        <Link
          href="/"
          className="rounded-full border border-solid border-black/[.08] px-4 py-1.5 text-sm transition-colors hover:bg-black/[.04] dark:border-white/[.145] dark:hover:bg-[#1a1a1a]"
        >
          Загрузить
        </Link>
      </div>

      {error && <p className="text-red-600">{error}</p>}

      {recordings === null && !error && <p className="text-zinc-500">Загрузка…</p>}

      {recordings !== null && recordings.length === 0 && (
        <p className="text-zinc-500">
          Записей пока нет.{" "}
          <Link href="/" className="underline">
            Загрузите первую
          </Link>
          , чтобы получить Транскрипт и Сводку.
        </p>
      )}

      {recordings !== null && recordings.length > 0 && (
        <div className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800">
          {recordings.map((recording) => (
            <Link
              key={recording.id}
              href={`/recordings/${recording.id}`}
              className="flex items-center justify-between gap-4 py-4 transition-colors hover:bg-black/[.02] dark:hover:bg-white/[.03]"
            >
              <div className="min-w-0">
                <p className="truncate font-medium text-black dark:text-zinc-50">{recording.original_filename}</p>
                <p className="text-sm text-zinc-500">{formatDate(recording.created_at)}</p>
              </div>
              <div className="shrink-0 text-right">
                <p className="text-sm text-zinc-700 dark:text-zinc-300">{statusLabel(recording.status)}</p>
                <p className="text-xs text-zinc-400">{recording.progress_percent}%</p>
              </div>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
