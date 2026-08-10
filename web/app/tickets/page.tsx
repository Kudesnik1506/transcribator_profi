"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import {
  createTicket,
  createTicketScreenshotUrl,
  listMyTickets,
  uploadScreenshot,
  type TicketListItem,
} from "@/lib/api";
import { formatDate } from "@/lib/date";
import { statusLabel } from "@/lib/ticketStatus";
import { AuthGuard } from "@/components/AuthGuard";

export default function TicketsPage() {
  return (
    <AuthGuard>
      <TicketsPageContent />
    </AuthGuard>
  );
}

function TicketsPageContent() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [tickets, setTickets] = useState<TicketListItem[] | null>(null);
  const [description, setDescription] = useState("");
  const [pageUrl, setPageUrl] = useState("");
  const [screenshot, setScreenshot] = useState<File | null>(null);
  const [isDragActive, setIsDragActive] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleScreenshotFiles(fileList: FileList | null) {
    const file = fileList?.[0];
    if (file && !file.type.startsWith("image/")) return;
    setScreenshot(file ?? null);
  }

  function loadTickets() {
    listMyTickets()
      .then(setTickets)
      .catch((err) => setError(err instanceof Error ? err.message : "Не удалось загрузить тикеты"));
  }

  useEffect(loadTickets, []);

  useEffect(() => {
    if (typeof document !== "undefined" && document.referrer) {
      try {
        const referrer = new URL(document.referrer);
        if (referrer.origin === window.location.origin) setPageUrl(referrer.pathname);
      } catch {
        // document.referrer isn't a valid URL — leave the field empty
      }
    }
  }, []);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!description.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      let screenshotS3Key: string | undefined;
      if (screenshot) {
        const { upload_url, s3_key } = await createTicketScreenshotUrl(
          screenshot.name,
          screenshot.type,
          screenshot.size
        );
        await uploadScreenshot(upload_url, screenshot, screenshot.type);
        screenshotS3Key = s3_key;
      }
      await createTicket(description.trim(), pageUrl.trim() || undefined, screenshotS3Key);
      setDescription("");
      setScreenshot(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      loadTickets();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось отправить заявку");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-10 px-6 py-12">
      <section className="flex flex-col gap-4 rounded-2xl border border-solid border-black/[.08] p-6 dark:border-white/[.145]">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">Сообщить об ошибке</h1>
          <p className="text-sm text-zinc-500">
            Эта вкладка — не просто почта в один конец. Заявку разбирают автоматически: проверяют несколько
            независимых версий причины (а не одну догадку), подтверждённую версию исправляют и выкатывают. Статус
            каждого шага и итоговое решение видны в списке тикетов ниже.
          </p>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <textarea
            required
            placeholder="Опишите, что пошло не так…"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={4}
            className="rounded-lg border border-solid border-black/[.08] px-4 py-2 text-sm dark:border-white/[.145] dark:bg-zinc-900"
          />
          <input
            type="text"
            placeholder="Страница, где произошло (необязательно)"
            value={pageUrl}
            onChange={(event) => setPageUrl(event.target.value)}
            className="rounded-lg border border-solid border-black/[.08] px-4 py-2 text-sm dark:border-white/[.145] dark:bg-zinc-900"
          />
          <div
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(event) => {
              event.preventDefault();
              setIsDragActive(true);
            }}
            onDragLeave={() => setIsDragActive(false)}
            onDrop={(event) => {
              event.preventDefault();
              setIsDragActive(false);
              handleScreenshotFiles(event.dataTransfer.files);
            }}
            className={[
              "flex cursor-pointer flex-col items-center gap-1 rounded-xl border-2 border-dashed p-4 text-center transition-colors",
              isDragActive
                ? "border-foreground bg-black/[.04] dark:bg-white/[.06]"
                : "border-black/[.15] dark:border-white/[.2]",
            ].join(" ")}
          >
            {screenshot ? (
              <>
                <p className="text-sm font-medium text-black dark:text-zinc-50">{screenshot.name}</p>
                <p className="text-xs text-zinc-500">нажмите или перетащите другой файл, чтобы заменить</p>
              </>
            ) : (
              <>
                <p className="text-sm font-medium text-black dark:text-zinc-50">Нажмите или перетащите скриншот сюда</p>
                <p className="text-xs text-zinc-500">Необязательно, изображение</p>
              </>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={(event) => handleScreenshotFiles(event.target.files)}
              className="hidden"
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={submitting || !description.trim()}
            className="w-fit rounded-full bg-foreground px-5 py-2.5 text-sm text-background transition-colors hover:bg-[#383838] disabled:opacity-50 dark:hover:bg-[#ccc]"
          >
            {submitting ? "Отправляем…" : "Отправить"}
          </button>
        </form>
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-xl font-semibold text-black dark:text-zinc-50">Мои тикеты</h2>
        {tickets === null && !error && <p className="text-zinc-500">Загрузка…</p>}
        {tickets !== null && tickets.length === 0 && <p className="text-zinc-500">Тикетов пока нет.</p>}
        {tickets !== null && tickets.length > 0 && (
          <div className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800">
            {tickets.map((ticket) => (
              <Link
                key={ticket.id}
                href={`/tickets/${ticket.id}`}
                className="flex items-center justify-between gap-4 py-4 transition-colors hover:bg-black/[.02] dark:hover:bg-white/[.03]"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium text-black dark:text-zinc-50">
                    #{ticket.number} — {ticket.description}
                  </p>
                  <p className="text-sm text-zinc-500">{formatDate(ticket.created_at)}</p>
                </div>
                <p className="shrink-0 text-sm text-zinc-700 dark:text-zinc-300">{statusLabel(ticket.status)}</p>
              </Link>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
