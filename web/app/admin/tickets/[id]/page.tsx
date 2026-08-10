"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import {
  adminCreateHypothesis,
  adminCreateTicketEvent,
  adminGetTicket,
  adminUpdateHypothesis,
  type AdminTicketDetail,
} from "@/lib/api";
import { formatDate } from "@/lib/date";
import { statusLabel } from "@/lib/ticketStatus";
import { AuthGuard } from "@/components/AuthGuard";

export default function AdminTicketPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <AuthGuard requireAdmin>
      <AdminTicketPageContent params={params} />
    </AuthGuard>
  );
}

const NEXT_STATUSES = ["investigating", "fix_ready", "deployed", "need_info", "rejected"];

function AdminTicketPageContent({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [ticket, setTicket] = useState<AdminTicketDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [hypothesisText, setHypothesisText] = useState("");
  const [hypothesisError, setHypothesisError] = useState<string | null>(null);

  const [verdictDrafts, setVerdictDrafts] = useState<Record<string, { verdict: string; evidence: string }>>({});
  const [verdictError, setVerdictError] = useState<string | null>(null);

  const [nextStatus, setNextStatus] = useState(NEXT_STATUSES[0]);
  const [eventMessage, setEventMessage] = useState("");
  const [eventError, setEventError] = useState<string | null>(null);
  const [submittingEvent, setSubmittingEvent] = useState(false);

  function load() {
    adminGetTicket(id)
      .then(setTicket)
      .catch((err) => setError(err instanceof Error ? err.message : "Не удалось загрузить тикет"));
  }

  useEffect(load, [id]);

  async function handleAddHypothesis() {
    if (!hypothesisText.trim()) return;
    setHypothesisError(null);
    try {
      const updated = await adminCreateHypothesis(id, hypothesisText.trim());
      setTicket(updated);
      setHypothesisText("");
    } catch (err) {
      setHypothesisError(err instanceof Error ? err.message : "Не удалось добавить гипотезу");
    }
  }

  async function handleSetVerdict(hypothesisId: string, verdict: "confirmed" | "rejected") {
    const draft = verdictDrafts[hypothesisId];
    setVerdictError(null);
    try {
      const updated = await adminUpdateHypothesis(id, hypothesisId, verdict, draft?.evidence ?? "");
      setTicket(updated);
    } catch (err) {
      setVerdictError(err instanceof Error ? err.message : "Не удалось сохранить вердикт");
    }
  }

  async function handleCreateEvent() {
    if (!eventMessage.trim()) return;
    setSubmittingEvent(true);
    setEventError(null);
    try {
      const updated = await adminCreateTicketEvent(id, nextStatus, eventMessage.trim());
      setTicket(updated);
      setEventMessage("");
    } catch (err) {
      setEventError(err instanceof Error ? err.message : "Не удалось изменить статус");
    } finally {
      setSubmittingEvent(false);
    }
  }

  if (error) {
    return <main className="mx-auto max-w-3xl px-6 py-12 text-red-600">{error}</main>;
  }

  if (!ticket) {
    return <main className="mx-auto max-w-3xl px-6 py-12 text-zinc-500">Загрузка…</main>;
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-12">
      <div>
        <Link href="/admin/tickets" className="text-sm text-zinc-500 underline">
          ← Все тикеты
        </Link>
        <h1 className="mt-2 text-2xl font-semibold text-black dark:text-zinc-50">
          Тикет #{ticket.number} — {statusLabel(ticket.status)}
        </h1>
        <p className="mt-2 text-zinc-700 dark:text-zinc-300">{ticket.description}</p>
        <p className="mt-1 text-sm text-zinc-500">
          {ticket.user_email}
          {ticket.page_url && ` · страница: ${ticket.page_url}`}
        </p>
      </div>

      {ticket.screenshot_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={ticket.screenshot_url}
          alt="Скриншот к тикету"
          className="max-w-full rounded-lg border border-solid border-black/[.08] dark:border-white/[.145]"
        />
      )}

      {ticket.recent_activity.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="font-medium text-black dark:text-zinc-50">
            Действия пользователя вокруг момента жалобы
          </h2>
          <ul className="flex flex-col gap-1 text-sm text-zinc-600 dark:text-zinc-400">
            {ticket.recent_activity.map((a, index) => (
              <li key={index}>
                {formatDate(a.created_at)} — {a.action}
                {Object.keys(a.context).length > 0 && (
                  <span className="ml-2 font-mono text-xs text-zinc-500">{JSON.stringify(a.context)}</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="flex flex-col gap-3">
        <h2 className="font-medium text-black dark:text-zinc-50">Гипотезы</h2>
        <p className="text-sm text-zinc-500">
          В fix_ready нельзя перейти без минимум трёх гипотез, все проверены, минимум одна подтверждена, у
          каждой отклонённой заполнено обоснование.
        </p>
        {ticket.hypotheses.map((h) => (
          <div key={h.id} className="rounded-lg border border-solid border-black/[.08] p-3 text-sm dark:border-white/[.145]">
            <p className="text-zinc-700 dark:text-zinc-300">{h.text}</p>
            {h.verdict === "pending" ? (
              <div className="mt-2 flex flex-col gap-2">
                <textarea
                  placeholder="Чем проверялась и что показала"
                  value={verdictDrafts[h.id]?.evidence ?? ""}
                  onChange={(event) =>
                    setVerdictDrafts((prev) => ({ ...prev, [h.id]: { verdict: "", evidence: event.target.value } }))
                  }
                  rows={2}
                  className="rounded-lg border border-solid border-black/[.08] px-3 py-1.5 text-sm dark:border-white/[.145] dark:bg-zinc-900"
                />
                <div className="flex gap-2">
                  <button
                    onClick={() => handleSetVerdict(h.id, "confirmed")}
                    className="rounded-full border border-solid border-black/[.08] px-4 py-1.5 text-sm transition-colors hover:bg-black/[.04] dark:border-white/[.145] dark:hover:bg-[#1a1a1a]"
                  >
                    Подтвердить
                  </button>
                  <button
                    onClick={() => handleSetVerdict(h.id, "rejected")}
                    className="rounded-full border border-solid border-red-600/30 px-4 py-1.5 text-sm text-red-600 transition-colors hover:bg-red-600/10"
                  >
                    Отклонить
                  </button>
                </div>
              </div>
            ) : (
              <p className="mt-1 text-xs text-zinc-500">
                {h.verdict === "confirmed" ? "подтвердилась" : "отклонена"}
                {h.evidence && ` — ${h.evidence}`}
              </p>
            )}
          </div>
        ))}
        {verdictError && <p className="text-sm text-red-600">{verdictError}</p>}

        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Новая гипотеза"
            value={hypothesisText}
            onChange={(event) => setHypothesisText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") handleAddHypothesis();
            }}
            className="flex-1 rounded-full border border-solid border-black/[.08] px-4 py-2 text-sm dark:border-white/[.145] dark:bg-zinc-900"
          />
          <button
            onClick={handleAddHypothesis}
            disabled={!hypothesisText.trim()}
            className="shrink-0 rounded-full bg-foreground px-5 py-2 text-sm text-background transition-colors hover:bg-[#383838] disabled:opacity-50 dark:hover:bg-[#ccc]"
          >
            Добавить
          </button>
        </div>
        {hypothesisError && <p className="text-sm text-red-600">{hypothesisError}</p>}
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="font-medium text-black dark:text-zinc-50">Ход разбора</h2>
        <div className="flex flex-col gap-3">
          {ticket.events.map((event) => (
            <div key={event.id} className="rounded-lg border border-solid border-black/[.08] p-4 text-sm dark:border-white/[.145]">
              <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-zinc-500">
                <span className="font-medium text-black dark:text-zinc-50">{statusLabel(event.status)}</span>
                <span>
                  {formatDate(event.created_at)} · {event.author === "agent" ? "агент" : "пользователь"}
                </span>
              </div>
              <p className="mt-1 text-zinc-700 dark:text-zinc-300">{event.message}</p>
            </div>
          ))}
        </div>

        <div className="flex flex-col gap-2 rounded-lg border border-solid border-black/[.08] p-4 dark:border-white/[.145]">
          <select
            value={nextStatus}
            onChange={(event) => setNextStatus(event.target.value)}
            className="w-fit rounded-lg border border-solid border-black/[.08] bg-transparent px-3 py-1.5 text-sm dark:border-white/[.145]"
          >
            {NEXT_STATUSES.map((status) => (
              <option key={status} value={status}>
                {statusLabel(status)}
              </option>
            ))}
          </select>
          <textarea
            placeholder="Что произошло на этом этапе — проблема и/или решение"
            value={eventMessage}
            onChange={(event) => setEventMessage(event.target.value)}
            rows={3}
            className="rounded-lg border border-solid border-black/[.08] px-3 py-1.5 text-sm dark:border-white/[.145] dark:bg-zinc-900"
          />
          {eventError && <p className="text-sm text-red-600">{eventError}</p>}
          <button
            onClick={handleCreateEvent}
            disabled={submittingEvent || !eventMessage.trim()}
            className="w-fit rounded-full bg-foreground px-5 py-2 text-sm text-background transition-colors hover:bg-[#383838] disabled:opacity-50 dark:hover:bg-[#ccc]"
          >
            {submittingEvent ? "Сохраняем…" : "Обновить статус"}
          </button>
        </div>
      </section>
    </main>
  );
}
