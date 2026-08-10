"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getMe, type CurrentUser } from "@/lib/api";
import { clearToken, loadToken } from "@/lib/auth";
import { hasSeenOnboarding, markOnboardingSeen } from "@/lib/onboarding";
import { getOnboardingSteps } from "@/lib/onboardingSteps";
import { AppHeader } from "@/components/AppHeader";
import { OnboardingTour } from "@/components/OnboardingTour";

export function AuthGuard({
  children,
  requireAdmin = false,
}: {
  children: React.ReactNode;
  requireAdmin?: boolean;
}) {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [tourOpen, setTourOpen] = useState(false);

  useEffect(() => {
    if (!loadToken()) {
      router.replace("/login");
      return;
    }
    getMe()
      .then((data) => {
        setUser(data);
        setLoading(false);
        if (data.status === "active" && !hasSeenOnboarding(data.id)) setTourOpen(true);
      })
      .catch(() => {
        clearToken();
        router.replace("/login");
      });
  }, [router]);

  if (loading || !user) {
    return <main className="mx-auto max-w-3xl px-6 py-12 text-zinc-500">Загрузка…</main>;
  }

  return (
    <>
      <AppHeader user={user} onOpenTour={() => setTourOpen(true)} />
      {tourOpen && (
        <OnboardingTour
          steps={getOnboardingSteps(user.role)}
          onFinish={() => {
            markOnboardingSeen(user.id);
            setTourOpen(false);
          }}
        />
      )}
      {user.status === "pending" ? (
        <main className="mx-auto flex max-w-md flex-col items-center gap-3 px-6 py-24 text-center">
          <h1 className="text-xl font-semibold text-black dark:text-zinc-50">Ожидает одобрения</h1>
          <p className="text-zinc-600 dark:text-zinc-400">
            Регистрация прошла успешно. Администратор ещё не одобрил ваш аккаунт — попробуйте зайти позже.
          </p>
        </main>
      ) : user.status === "blocked" ? (
        <main className="mx-auto flex max-w-md flex-col items-center gap-3 px-6 py-24 text-center">
          <h1 className="text-xl font-semibold text-black dark:text-zinc-50">Доступ заблокирован</h1>
          <p className="text-zinc-600 dark:text-zinc-400">Обратитесь к администратору.</p>
        </main>
      ) : requireAdmin && user.role !== "admin" ? (
        <main className="mx-auto flex max-w-md flex-col items-center gap-3 px-6 py-24 text-center">
          <h1 className="text-xl font-semibold text-black dark:text-zinc-50">Доступ только для администраторов</h1>
          <p className="text-zinc-600 dark:text-zinc-400">У вас недостаточно прав для просмотра этой страницы.</p>
        </main>
      ) : (
        children
      )}
    </>
  );
}
