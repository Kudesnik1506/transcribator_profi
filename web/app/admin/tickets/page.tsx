"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AuthGuard } from "@/components/AuthGuard";
import { adminListTickets, type AdminTicketListItem } from "@/lib/api";
import { formatDate } from "@/lib/date";
import { statusLabel } from "@/lib/ticketStatus";

export default function AdminTicketsPage() {
  return (
    <AuthGuard requireAdmin>
      <AdminTicketsPageContent />
    </AuthGuard>
  );
}

const STATUSES = ["new", "investigating", "fix_ready", "deployed", "rejected", "need_info"];

function AdminTicketsPageContent() {
  const [tickets, setTickets] = useState<AdminTicketListItem[] | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminListTickets(statusFilter || undefined)
      .then(setTickets)
      .catch((err) => setError(err instanceof Error ? err.message : "Не удалось загрузить тикеты"));
  }, [statusFilter]);

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-12">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">Тикеты поддержки</h1>
        <Link href="/admin" className="shrink-0 text-sm text-zinc-500 underline">
          Назад в админку
        </Link>
      </div>

      <select
        value={statusFilter}
        onChange={(event) => setStatusFilter(event.target.value)}
        className="w-fit rounded-lg border border-solid border-black/[.08] bg-transparent px-3 py-1.5 text-sm dark:border-white/[.145]"
      >
        <option value="">Все статусы</option>
        {STATUSES.map((status) => (
          <option key={status} value={status}>
            {statusLabel(status)}
          </option>
        ))}
      </select>

      {error && <p className="text-red-600">{error}</p>}
      {tickets === null && !error && <p className="text-zinc-500">Загрузка…</p>}
      {tickets !== null && tickets.length === 0 && <p className="text-zinc-500">Тикетов не найдено.</p>}

      {tickets !== null && tickets.length > 0 && (
        <div className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800">
          {tickets.map((ticket) => (
            <Link
              key={ticket.id}
              href={`/admin/tickets/${ticket.id}`}
              className="flex items-center justify-between gap-4 py-4 transition-colors hover:bg-black/[.02] dark:hover:bg-white/[.03]"
            >
              <div className="min-w-0">
                <p className="truncate font-medium text-black dark:text-zinc-50">
                  #{ticket.number} — {ticket.description}
                </p>
                <p className="text-sm text-zinc-500">
                  {ticket.user_email} · {formatDate(ticket.created_at)}
                </p>
              </div>
              <p className="shrink-0 text-sm text-zinc-700 dark:text-zinc-300">{statusLabel(ticket.status)}</p>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
