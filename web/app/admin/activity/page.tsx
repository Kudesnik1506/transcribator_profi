"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AuthGuard } from "@/components/AuthGuard";
import { adminListActivityLogs, type AdminActivityLog } from "@/lib/api";
import { formatDate } from "@/lib/date";

export default function AdminActivityPage() {
  return (
    <AuthGuard requireAdmin>
      <AdminActivityPageContent />
    </AuthGuard>
  );
}

function AdminActivityPageContent() {
  const [logs, setLogs] = useState<AdminActivityLog[] | null>(null);
  const [userIdFilter, setUserIdFilter] = useState("");
  const [actionFilter, setActionFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminListActivityLogs({ userId: userIdFilter || undefined, action: actionFilter || undefined })
      .then(setLogs)
      .catch((err) => setError(err instanceof Error ? err.message : "Не удалось загрузить логи"));
  }, [userIdFilter, actionFilter]);

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-12">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">Лог активности</h1>
        <Link href="/admin" className="text-sm text-zinc-500 underline">
          Назад в админку
        </Link>
      </div>

      <div className="flex gap-3">
        <input
          type="text"
          placeholder="ID Пользователя"
          value={userIdFilter}
          onChange={(event) => setUserIdFilter(event.target.value)}
          className="rounded-lg border border-solid border-black/[.08] bg-transparent px-3 py-1.5 text-sm dark:border-white/[.145]"
        />
        <input
          type="text"
          placeholder="Действие (например login)"
          value={actionFilter}
          onChange={(event) => setActionFilter(event.target.value)}
          className="rounded-lg border border-solid border-black/[.08] bg-transparent px-3 py-1.5 text-sm dark:border-white/[.145]"
        />
      </div>

      {error && <p className="text-red-600">{error}</p>}
      {logs === null && !error && <p className="text-zinc-500">Загрузка…</p>}
      {logs !== null && logs.length === 0 && <p className="text-zinc-500">Записей не найдено.</p>}

      {logs !== null && logs.length > 0 && (
        <div className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800">
          {logs.map((log) => (
            <div key={log.id} className="flex flex-col gap-1 py-4">
              <div className="flex items-center gap-2 text-sm text-zinc-500">
                <span className="font-medium text-black dark:text-zinc-50">{log.action}</span>
                <span>{formatDate(log.created_at)}</span>
                <span>{log.user_email ?? "без пользователя"}</span>
                {log.ip && <span>{log.ip}</span>}
              </div>
              {Object.keys(log.context).length > 0 && (
                <p className="font-mono text-xs text-zinc-500">{JSON.stringify(log.context)}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
