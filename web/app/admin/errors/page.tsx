"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AuthGuard } from "@/components/AuthGuard";
import { adminListErrorLogs, type AdminErrorLog } from "@/lib/api";
import { formatDate } from "@/lib/date";

export default function AdminErrorsPage() {
  return (
    <AuthGuard requireAdmin>
      <AdminErrorsPageContent />
    </AuthGuard>
  );
}

function AdminErrorsPageContent() {
  const [logs, setLogs] = useState<AdminErrorLog[] | null>(null);
  const [levelFilter, setLevelFilter] = useState("");
  const [recordingIdFilter, setRecordingIdFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminListErrorLogs({ level: levelFilter || undefined, recordingId: recordingIdFilter || undefined })
      .then(setLogs)
      .catch((err) => setError(err instanceof Error ? err.message : "Не удалось загрузить логи"));
  }, [levelFilter, recordingIdFilter]);

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-12">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">Логи ошибок</h1>
        <Link href="/admin" className="text-sm text-zinc-500 underline">
          Назад в админку
        </Link>
      </div>

      <div className="flex gap-3">
        <select
          value={levelFilter}
          onChange={(event) => setLevelFilter(event.target.value)}
          className="rounded-lg border border-solid border-black/[.08] bg-transparent px-3 py-1.5 text-sm dark:border-white/[.145]"
        >
          <option value="">Все уровни</option>
          <option value="error">error</option>
          <option value="warning">warning</option>
        </select>
        <input
          type="text"
          placeholder="ID Записи"
          value={recordingIdFilter}
          onChange={(event) => setRecordingIdFilter(event.target.value)}
          className="rounded-lg border border-solid border-black/[.08] bg-transparent px-3 py-1.5 text-sm dark:border-white/[.145]"
        />
      </div>

      {error && <p className="text-red-600">{error}</p>}
      {logs === null && !error && <p className="text-zinc-500">Загрузка…</p>}
      {logs !== null && logs.length === 0 && <p className="text-zinc-500">Логов не найдено.</p>}

      {logs !== null && logs.length > 0 && (
        <div className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800">
          {logs.map((log) => (
            <div key={log.id} className="flex flex-col gap-1 py-4">
              <div className="flex items-center gap-2 text-sm text-zinc-500">
                <span className={log.level === "error" ? "text-red-600" : "text-amber-600"}>{log.level}</span>
                <span>{formatDate(log.created_at)}</span>
                {log.recording_id && (
                  <Link href={`/recordings/${log.recording_id}`} className="underline">
                    Запись {log.recording_id.slice(0, 8)}
                  </Link>
                )}
              </div>
              <p className="text-black dark:text-zinc-50">{log.message}</p>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
