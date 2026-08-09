"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { getTicket, type TicketDetail } from "@/lib/api";
import { formatDate } from "@/lib/date";
import { statusLabel } from "@/lib/ticketStatus";
import { AuthGuard } from "@/components/AuthGuard";

export default function TicketPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <AuthGuard>
      <TicketPageContent params={params} />
    </AuthGuard>
  );
}

const VERDICT_LABELS: Record<string, string> = {
  pending: "проверяется",
  confirmed: "подтвердилась",
  rejected: "отклонена",
};

function TicketPageContent({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const data = await getTicket(id);
        if (cancelled) return;
        setTicket(data);
        if (data.status !== "deployed" && data.status !== "rejected") {
          timer = setTimeout(poll, 5000);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Не удалось загрузить тикет");
      }
    }

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [id]);

  if (error) {
    return <main className="mx-auto max-w-2xl px-6 py-12 text-red-600">{error}</main>;
  }

  if (!ticket) {
    return <main className="mx-auto max-w-2xl px-6 py-12 text-zinc-500">Загрузка…</main>;
  }

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-8 px-6 py-12">
      <div>
        <Link href="/tickets" className="text-sm text-zinc-500 underline">
          ← К тикетам
        </Link>
        <h1 className="mt-2 text-2xl font-semibold text-black dark:text-zinc-50">
          Тикет #{ticket.number} — {statusLabel(ticket.status)}
        </h1>
        <p className="mt-2 text-zinc-700 dark:text-zinc-300">{ticket.description}</p>
        {ticket.page_url && <p className="mt-1 text-sm text-zinc-500">Страница: {ticket.page_url}</p>}
      </div>

      {ticket.screenshot_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={ticket.screenshot_url}
          alt="Скриншот к тикету"
          className="max-w-full rounded-lg border border-solid border-black/[.08] dark:border-white/[.145]"
        />
      )}

      <section className="flex flex-col gap-3">
        <h2 className="font-medium text-black dark:text-zinc-50">Ход разбора</h2>
        <div className="flex flex-col gap-3">
          {ticket.events.map((event) => (
            <div
              key={event.id}
              className="rounded-lg border border-solid border-black/[.08] p-4 text-sm dark:border-white/[.145]"
            >
              <div className="flex items-center justify-between text-zinc-500">
                <span className="font-medium text-black dark:text-zinc-50">{statusLabel(event.status)}</span>
                <span>{formatDate(event.created_at)}</span>
              </div>
              <p className="mt-1 text-zinc-700 dark:text-zinc-300">{event.message}</p>
            </div>
          ))}
        </div>
      </section>

      {ticket.hypotheses.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="font-medium text-black dark:text-zinc-50">Проверенные версии</h2>
          <ul className="flex flex-col gap-2">
            {ticket.hypotheses.map((h) => (
              <li key={h.id} className="rounded-lg border border-solid border-black/[.08] p-3 text-sm dark:border-white/[.145]">
                <p className="text-zinc-700 dark:text-zinc-300">{h.text}</p>
                <p className="mt-1 text-xs text-zinc-500">
                  {VERDICT_LABELS[h.verdict] ?? h.verdict}
                  {h.evidence && ` — ${h.evidence}`}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
