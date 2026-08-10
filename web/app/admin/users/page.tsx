"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AuthGuard } from "@/components/AuthGuard";
import { adminApproveUser, adminBlockUser, adminListUsers, adminResetPassword, type AdminUser } from "@/lib/api";

const STATUS_LABELS: Record<string, string> = {
  pending: "ожидает одобрения",
  active: "активен",
  blocked: "заблокирован",
};

export default function AdminUsersPage() {
  return (
    <AuthGuard requireAdmin>
      <AdminUsersPageContent />
    </AuthGuard>
  );
}

function AdminUsersPageContent() {
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  function load() {
    adminListUsers()
      .then(setUsers)
      .catch((err) => setError(err instanceof Error ? err.message : "Не удалось загрузить пользователей"));
  }

  useEffect(load, []);

  async function handleApprove(id: string) {
    setBusyId(id);
    try {
      await adminApproveUser(id);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось одобрить пользователя");
    } finally {
      setBusyId(null);
    }
  }

  async function handleBlock(id: string) {
    setBusyId(id);
    try {
      await adminBlockUser(id);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось заблокировать пользователя");
    } finally {
      setBusyId(null);
    }
  }

  async function handleResetPassword(id: string) {
    const newPassword = window.prompt("Новый пароль для пользователя (не короче 8 символов):");
    if (!newPassword) return;
    setBusyId(id);
    setError(null);
    try {
      await adminResetPassword(id, newPassword);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сбросить пароль");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-12">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">Пользователи</h1>
        <Link href="/admin" className="shrink-0 text-sm text-zinc-500 underline">
          Назад в админку
        </Link>
      </div>

      {error && <p className="text-red-600">{error}</p>}
      {users === null && !error && <p className="text-zinc-500">Загрузка…</p>}

      {users !== null && (
        <div className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800">
          {users.map((user) => (
            <div key={user.id} className="flex items-center justify-between gap-4 py-4">
              <div className="min-w-0">
                <p className="truncate font-medium text-black dark:text-zinc-50">{user.email}</p>
                <p className="text-sm text-zinc-500">
                  {user.role} · {STATUS_LABELS[user.status] ?? user.status}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                <button
                  onClick={() => handleResetPassword(user.id)}
                  disabled={busyId === user.id}
                  className="rounded-full border border-solid border-black/[.08] px-4 py-1.5 text-sm transition-colors hover:bg-black/[.04] disabled:opacity-50 dark:border-white/[.145] dark:hover:bg-[#1a1a1a]"
                >
                  Сбросить пароль
                </button>
                {user.status !== "active" && (
                  <button
                    onClick={() => handleApprove(user.id)}
                    disabled={busyId === user.id}
                    className="rounded-full border border-solid border-black/[.08] px-4 py-1.5 text-sm transition-colors hover:bg-black/[.04] disabled:opacity-50 dark:border-white/[.145] dark:hover:bg-[#1a1a1a]"
                  >
                    Одобрить
                  </button>
                )}
                {user.status !== "blocked" && (
                  <button
                    onClick={() => handleBlock(user.id)}
                    disabled={busyId === user.id}
                    className="rounded-full border border-solid border-red-600/30 px-4 py-1.5 text-sm text-red-600 transition-colors hover:bg-red-600/10 disabled:opacity-50"
                  >
                    Заблокировать
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
