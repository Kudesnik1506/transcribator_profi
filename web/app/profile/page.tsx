"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AuthGuard } from "@/components/AuthGuard";
import { changePassword, deleteAccount, getMe, type CurrentUser } from "@/lib/api";
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

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPasswordConfirm, setNewPasswordConfirm] = useState("");
  const [changingPassword, setChangingPassword] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordChanged, setPasswordChanged] = useState(false);

  useEffect(() => {
    getMe()
      .then(setUser)
      .catch(() => {
        // AuthGuard already handles the unauthenticated case
      });
  }, []);

  async function handleChangePassword(event: React.FormEvent) {
    event.preventDefault();
    setPasswordError(null);
    setPasswordChanged(false);
    if (newPassword !== newPasswordConfirm) {
      setPasswordError("Новые пароли не совпадают");
      return;
    }
    setChangingPassword(true);
    try {
      await changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setNewPasswordConfirm("");
      setPasswordChanged(true);
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : "Не удалось сменить пароль");
    } finally {
      setChangingPassword(false);
    }
  }

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

      <section className="flex flex-col gap-3 rounded-2xl border border-solid border-black/[.08] p-6 dark:border-white/[.145]">
        <h2 className="font-medium text-black dark:text-zinc-50">Сменить пароль</h2>
        <form onSubmit={handleChangePassword} className="flex flex-col gap-3">
          <input
            type="password"
            required
            placeholder="Текущий пароль"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            className="rounded-lg border border-solid border-black/[.08] px-4 py-2 text-sm dark:border-white/[.145] dark:bg-zinc-900"
          />
          <input
            type="password"
            required
            placeholder="Новый пароль"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            className="rounded-lg border border-solid border-black/[.08] px-4 py-2 text-sm dark:border-white/[.145] dark:bg-zinc-900"
          />
          <input
            type="password"
            required
            placeholder="Повторите новый пароль"
            value={newPasswordConfirm}
            onChange={(event) => setNewPasswordConfirm(event.target.value)}
            className="rounded-lg border border-solid border-black/[.08] px-4 py-2 text-sm dark:border-white/[.145] dark:bg-zinc-900"
          />
          {passwordError && <p className="text-sm text-red-600">{passwordError}</p>}
          {passwordChanged && <p className="text-sm text-green-600">Пароль обновлён.</p>}
          <button
            type="submit"
            disabled={changingPassword}
            className="w-fit rounded-full bg-foreground px-5 py-2.5 text-sm text-background transition-colors hover:bg-[#383838] disabled:opacity-50 dark:hover:bg-[#ccc]"
          >
            {changingPassword ? "Сохраняем…" : "Сменить пароль"}
          </button>
        </form>
      </section>

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
