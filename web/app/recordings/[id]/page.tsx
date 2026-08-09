"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import {
  downloadExport,
  getRecording,
  listShares,
  retryRecording,
  revokeShare,
  shareRecording,
  type ExportFormat,
  type RecordingDetail,
  type RecordingShare,
} from "@/lib/api";
import { IN_PROGRESS_STATUSES, TERMINAL_STATUSES, statusLabel } from "@/lib/recordingStatus";
import { AuthGuard } from "@/components/AuthGuard";

import { Dialog } from "./Dialog";
import { PlayerTranscript } from "./PlayerTranscript";

export default function RecordingPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <AuthGuard>
      <RecordingPageContent params={params} />
    </AuthGuard>
  );
}

type Tab = "summary" | "transcript" | "dialog";

function RecordingPageContent({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [recording, setRecording] = useState<RecordingDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [selectedTab, setSelectedTab] = useState<Tab | null>(null);
  const [shares, setShares] = useState<RecordingShare[]>([]);
  const [shareEmail, setShareEmail] = useState("");
  const [sharing, setSharing] = useState(false);
  const [shareError, setShareError] = useState<string | null>(null);

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

  useEffect(() => {
    if (!recording?.is_owner) return;
    listShares(recording.id)
      .then(setShares)
      .catch(() => {
        // не критично для остального функционала страницы
      });
  }, [recording?.is_owner, recording?.id]);

  async function handleShare() {
    const email = shareEmail.trim();
    if (!email || !recording) return;
    setSharing(true);
    setShareError(null);
    try {
      await shareRecording(recording.id, email);
      setShareEmail("");
      const updated = await listShares(recording.id);
      setShares(updated);
    } catch (err) {
      setShareError(err instanceof Error ? err.message : "Не удалось поделиться записью");
    } finally {
      setSharing(false);
    }
  }

  async function handleRevokeShare(shareId: string) {
    if (!recording) return;
    try {
      await revokeShare(recording.id, shareId);
      setShares((prev) => prev.filter((share) => share.id !== shareId));
    } catch (err) {
      setShareError(err instanceof Error ? err.message : "Не удалось отозвать доступ");
    }
  }

  async function handleExport(format: ExportFormat) {
    if (!recording) return;
    try {
      await downloadExport(recording.id, format, recording.original_filename);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось скачать файл");
    }
  }

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
        <Link href="/recordings" className="text-sm text-zinc-500 underline">
          ← К списку записей
        </Link>
        <h1 className="mt-2 text-2xl font-semibold text-black dark:text-zinc-50">{recording.original_filename}</h1>
        <p className="mt-1 text-zinc-500">{statusLabel(recording.status)}</p>
        {!recording.is_owner && recording.owner_email && (
          <p className="mt-1 text-sm text-zinc-500">Поделился: {recording.owner_email}</p>
        )}

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

        {recording.status === "partial" && recording.is_owner && (
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

      {recording.is_owner && (
        <section className="flex flex-col gap-3 rounded-2xl border border-solid border-black/[.08] p-6 dark:border-white/[.145]">
          <h2 className="font-medium text-black dark:text-zinc-50">Поделиться записью</h2>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Доступ на чтение — зарегистрированный аккаунт увидит транскрипт, сводку и диалог, но не сможет
            задавать новые вопросы или повторять обработку.
          </p>
          <div className="flex gap-2">
            <input
              value={shareEmail}
              onChange={(event) => setShareEmail(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") handleShare();
              }}
              placeholder="email@example.com"
              className="flex-1 rounded-full border border-solid border-black/[.08] px-4 py-2 text-sm dark:border-white/[.145] dark:bg-zinc-900"
            />
            <button
              onClick={handleShare}
              disabled={sharing || !shareEmail.trim()}
              className="shrink-0 rounded-full bg-foreground px-5 py-2 text-sm text-background transition-colors hover:bg-[#383838] disabled:opacity-50 dark:hover:bg-[#ccc]"
            >
              {sharing ? "Делимся…" : "Дать доступ"}
            </button>
          </div>
          {shareError && <p className="text-sm text-red-600">{shareError}</p>}
          {shares.length > 0 && (
            <ul className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800">
              {shares.map((share) => (
                <li key={share.id} className="flex items-center justify-between gap-4 py-2">
                  <span className="text-sm text-zinc-700 dark:text-zinc-300">{share.email}</span>
                  <button
                    onClick={() => handleRevokeShare(share.id)}
                    className="text-sm text-red-600 underline"
                  >
                    Отозвать
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {(() => {
        const showDialog =
          (recording.status === "done" || recording.status === "partial") && recording.segments.length > 0;
        const tabs: { id: Tab; label: string }[] = [
          ...(recording.summary ? [{ id: "summary" as const, label: "Сводка" }] : []),
          ...(recording.segments.length > 0 ? [{ id: "transcript" as const, label: "Транскрипт" }] : []),
          ...(showDialog ? [{ id: "dialog" as const, label: "Диалог" }] : []),
        ];
        const activeTab = tabs.find((tab) => tab.id === selectedTab)?.id ?? tabs[0]?.id;

        if (tabs.length === 0) return null;

        return (
          <section>
            <div className="flex gap-1 border-b border-solid border-black/[.08] dark:border-white/[.145]">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setSelectedTab(tab.id)}
                  className={[
                    "-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors",
                    activeTab === tab.id
                      ? "border-foreground text-black dark:text-zinc-50"
                      : "border-transparent text-zinc-500 hover:text-black dark:hover:text-zinc-50",
                  ].join(" ")}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div className="pt-6">
              {activeTab === "summary" && recording.summary && (
                <ul className="list-disc space-y-1 pl-5 text-zinc-700 dark:text-zinc-300">
                  {recording.summary.items.map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              )}

              {activeTab === "transcript" && recording.segments.length > 0 && (
                <>
                  <div className="mb-3 flex justify-end gap-2">
                    {(["txt", "srt", "docx"] as const).map((format) => (
                      <button
                        key={format}
                        onClick={() => handleExport(format)}
                        className="rounded-full border border-solid border-black/[.08] px-3 py-1 text-xs transition-colors hover:bg-black/[.04] dark:border-white/[.145] dark:hover:bg-[#1a1a1a]"
                      >
                        .{format}
                      </button>
                    ))}
                  </div>
                  <PlayerTranscript
                    recordingId={recording.id}
                    mediaUrl={recording.media_url}
                    mediaDeletedAt={recording.media_deleted_at}
                    contentType={recording.content_type}
                    segments={recording.segments}
                  />
                </>
              )}

              {activeTab === "dialog" && showDialog && (
                <Dialog recordingId={recording.id} readOnly={!recording.is_owner} />
              )}
            </div>
          </section>
        );
      })()}
    </main>
  );
}
