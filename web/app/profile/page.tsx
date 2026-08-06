"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AuthGuard } from "@/components/AuthGuard";
import { createTelegramLinkCode, getMe, type CurrentUser, type TelegramLinkCode } from "@/lib/api";

export default function ProfilePage() {
  return (
    <AuthGuard>
      <ProfilePageContent />
    </AuthGuard>
  );
}

function ProfilePageContent() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [linkCode, setLinkCode] = useState<TelegramLinkCode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getMe()
      .then(setUser)
      .catch(() => {
        // AuthGuard already handles the unauthenticated case
      });
  }, []);

  async function handleRequestCode() {
    setLoading(true);
    setError(null);
    try {
      const code = await createTelegramLinkCode();
      setLinkCode(code);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось получить код");
    } finally {
      setLoading(false);
    }
  }

  const deepLink = linkCode?.bot_username ? `https://t.me/${linkCode.bot_username}?start=${linkCode.code}` : null;

  return (
    <main className="mx-auto flex max-w-xl flex-col gap-6 px-6 py-12">
      <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">Профиль</h1>

      {user && <p className="text-zinc-600 dark:text-zinc-400">{user.email}</p>}

      {user?.role === "admin" && (
        <Link href="/admin" className="w-fit text-sm text-zinc-500 underline">
          Админка
        </Link>
      )}

      <section className="flex flex-col gap-3 rounded-2xl border border-solid border-black/[.08] p-6 dark:border-white/[.145]">
        <h2 className="font-medium text-black dark:text-zinc-50">Telegram-уведомления</h2>

        {user?.telegram_linked ? (
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Telegram привязан — уведомления о готовых Записях будут приходить сюда и на почту.
          </p>
        ) : (
          <>
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              Необязательно: привяжите Telegram, чтобы получать уведомление о готовности Записи и в боте, а не
              только на почту.
            </p>
            {!linkCode && (
              <button
                onClick={handleRequestCode}
                disabled={loading}
                className="w-fit rounded-full bg-foreground px-5 py-2 text-sm text-background transition-colors hover:bg-[#383838] disabled:opacity-50 dark:hover:bg-[#ccc]"
              >
                {loading ? "Запрашиваем код…" : "Получить код привязки"}
              </button>
            )}
            {linkCode && (
              <div className="flex flex-col gap-2 text-sm">
                {deepLink ? (
                  <a href={deepLink} target="_blank" rel="noreferrer" className="text-blue-600 underline">
                    Открыть бота и привязать автоматически
                  </a>
                ) : (
                  <p className="text-zinc-600 dark:text-zinc-400">
                    Напишите боту команду: <code className="font-mono">/start {linkCode.code}</code>
                  </p>
                )}
                <p className="text-xs text-zinc-500">Код действует 15 минут.</p>
              </div>
            )}
          </>
        )}

        {error && <p className="text-sm text-red-600">{error}</p>}
      </section>
    </main>
  );
}
