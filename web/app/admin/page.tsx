"use client";

import Link from "next/link";

import { AuthGuard } from "@/components/AuthGuard";

export default function AdminIndexPage() {
  return (
    <AuthGuard requireAdmin>
      <main className="mx-auto flex max-w-xl flex-col gap-6 px-6 py-12">
        <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">Админка</h1>
        <div className="flex flex-col divide-y divide-zinc-200 rounded-2xl border border-solid border-black/[.08] dark:divide-zinc-800 dark:border-white/[.145]">
          <Link href="/admin/users" className="px-6 py-4 transition-colors hover:bg-black/[.02] dark:hover:bg-white/[.03]">
            Пользователи
          </Link>
          <Link
            href="/admin/recordings"
            className="px-6 py-4 transition-colors hover:bg-black/[.02] dark:hover:bg-white/[.03]"
          >
            Все Записи
          </Link>
          <Link href="/admin/errors" className="px-6 py-4 transition-colors hover:bg-black/[.02] dark:hover:bg-white/[.03]">
            Логи ошибок
          </Link>
          <Link
            href="/admin/activity"
            className="px-6 py-4 transition-colors hover:bg-black/[.02] dark:hover:bg-white/[.03]"
          >
            Лог активности
          </Link>
          <Link
            href="/admin/tickets"
            className="px-6 py-4 transition-colors hover:bg-black/[.02] dark:hover:bg-white/[.03]"
          >
            Тикеты поддержки
          </Link>
        </div>
      </main>
    </AuthGuard>
  );
}
