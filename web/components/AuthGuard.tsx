"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getMe, type CurrentUser } from "@/lib/api";
import { clearToken, loadToken } from "@/lib/auth";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!loadToken()) {
      router.replace("/login");
      return;
    }
    getMe()
      .then((data) => {
        setUser(data);
        setLoading(false);
      })
      .catch(() => {
        clearToken();
        router.replace("/login");
      });
  }, [router]);

  if (loading || !user) {
    return <main className="mx-auto max-w-3xl px-6 py-12 text-zinc-500">Загрузка…</main>;
  }

  if (user.status === "pending") {
    return (
      <main className="mx-auto flex max-w-md flex-col items-center gap-3 px-6 py-24 text-center">
        <h1 className="text-xl font-semibold text-black dark:text-zinc-50">Ожидает одобрения</h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          Регистрация прошла успешно. Администратор ещё не одобрил ваш аккаунт — попробуйте зайти позже.
        </p>
      </main>
    );
  }

  if (user.status === "blocked") {
    return (
      <main className="mx-auto flex max-w-md flex-col items-center gap-3 px-6 py-24 text-center">
        <h1 className="text-xl font-semibold text-black dark:text-zinc-50">Доступ заблокирован</h1>
        <p className="text-zinc-600 dark:text-zinc-400">Обратитесь к администратору.</p>
      </main>
    );
  }

  return <>{children}</>;
}
