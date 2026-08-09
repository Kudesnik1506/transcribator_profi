"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AuthGuard } from "@/components/AuthGuard";
import { deleteAccount, getMe, type CurrentUser } from "@/lib/api";
import { clearToken } from "@/lib/auth";

export default function ProfilePage() {
  return (
    <AuthGuard>
      <ProfilePageContent />
    </AuthGuard>
  );
}

function ProfilePageContent() {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    getMe()
      .then(setUser)
      .catch(() => {
        // AuthGuard already handles the unauthenticated case
      });
  }, []);

  async function handleDeleteAccount() {
    if (!confirm("Точно удалить аккаунт без возможности восстановления? Все записи будут удалены безвозвратно.")) {
      return;
    }
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteAccount();
      clearToken();
      router.push("/login");
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Не удалось удалить аккаунт");
      setDeleting(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-xl flex-col gap-6 px-6 py-12">
      <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">Профиль</h1>

      {user && <p className="text-zinc-600 dark:text-zinc-400">{user.email}</p>}

      <section className="flex flex-col gap-3 rounded-2xl border border-solid border-red-600/30 p-6">
        <h2 className="font-medium text-black dark:text-zinc-50">Удалить аккаунт</h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Аккаунт и все ваши записи (транскрипты, сводки, диалоги) будут удалены безвозвратно.
        </p>
        <label className="flex w-fit items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
          <input
            type="checkbox"
            checked={confirmDelete}
            onChange={(event) => setConfirmDelete(event.target.checked)}
          />
          Я понимаю, что все мои записи будут безвозвратно удалены
        </label>
        <button
          onClick={handleDeleteAccount}
          disabled={!confirmDelete || deleting}
          className="w-fit rounded-full border border-solid border-red-600/30 px-4 py-1.5 text-sm text-red-600 transition-colors hover:bg-red-600/10 disabled:opacity-50"
        >
          {deleting ? "Удаляем…" : "Удалить аккаунт"}
        </button>
        {deleteError && <p className="text-sm text-red-600">{deleteError}</p>}
      </section>
    </main>
  );
}
