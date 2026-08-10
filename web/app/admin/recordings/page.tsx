"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AuthGuard } from "@/components/AuthGuard";
import { adminDeleteRecording, adminListRecordings, adminListUsers, type AdminRecording, type AdminUser } from "@/lib/api";
import { formatDate } from "@/lib/date";
import { STATUS_LABELS, modeLabel, statusLabel } from "@/lib/recordingStatus";

export default function AdminRecordingsPage() {
  return (
    <AuthGuard requireAdmin>
      <AdminRecordingsPageContent />
    </AuthGuard>
  );
}

function AdminRecordingsPageContent() {
  const [recordings, setRecordings] = useState<AdminRecording[] | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [userFilter, setUserFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    adminListUsers()
      .then(setUsers)
      .catch(() => {
        // filter dropdown just stays empty — not fatal
      });
  }, []);

  function load() {
    adminListRecordings({ userId: userFilter || undefined, status: statusFilter || undefined })
      .then(setRecordings)
      .catch((err) => setError(err instanceof Error ? err.message : "Не удалось загрузить Записи"));
  }

  useEffect(load, [userFilter, statusFilter]);

  async function handleDelete(recording: AdminRecording) {
    if (!confirm(`Удалить «${recording.original_filename}» вместе с файлом в S3? Это необратимо.`)) return;
    setDeletingId(recording.id);
    try {
      await adminDeleteRecording(recording.id);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось удалить Запись");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-12">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">Все Записи</h1>
        <Link href="/admin" className="shrink-0 text-sm text-zinc-500 underline">
          Назад в админку
        </Link>
      </div>

      <div className="flex gap-3">
        <select
          value={userFilter}
          onChange={(event) => setUserFilter(event.target.value)}
          className="rounded-lg border border-solid border-black/[.08] bg-transparent px-3 py-1.5 text-sm dark:border-white/[.145]"
        >
          <option value="">Все пользователи</option>
          {users.map((user) => (
            <option key={user.id} value={user.id}>
              {user.email}
            </option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value)}
          className="rounded-lg border border-solid border-black/[.08] bg-transparent px-3 py-1.5 text-sm dark:border-white/[.145]"
        >
          <option value="">Все статусы</option>
          {Object.entries(STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {error && <p className="text-red-600">{error}</p>}
      {recordings === null && !error && <p className="text-zinc-500">Загрузка…</p>}
      {recordings !== null && recordings.length === 0 && <p className="text-zinc-500">Записей не найдено.</p>}

      {recordings !== null && recordings.length > 0 && (
        <div className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800">
          {recordings.map((recording) => (
            <div key={recording.id} className="flex items-center justify-between gap-4 py-4">
              <div className="min-w-0">
                <Link
                  href={`/recordings/${recording.id}`}
                  className="block truncate font-medium text-black underline-offset-2 hover:underline dark:text-zinc-50"
                >
                  {recording.original_filename}
                </Link>
                <p className="text-sm text-zinc-500">
                  {recording.user_email ?? "без владельца"} · {formatDate(recording.created_at)} ·{" "}
                  {modeLabel(recording.mode)}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-4">
                <p className="text-sm text-zinc-700 dark:text-zinc-300">{statusLabel(recording.status)}</p>
                <button
                  onClick={() => handleDelete(recording)}
                  disabled={deletingId === recording.id}
                  className="rounded-full border border-solid border-red-600/30 px-4 py-1.5 text-sm text-red-600 transition-colors hover:bg-red-600/10 disabled:opacity-50"
                >
                  Удалить
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
