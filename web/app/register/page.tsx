"use client";

import Link from "next/link";
import { useState } from "react";

import { register } from "@/lib/api";

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await register(email, password);
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось зарегистрироваться");
    } finally {
      setSubmitting(false);
    }
  }

  if (done) {
    return (
      <div className="flex flex-col flex-1 items-center justify-center bg-zinc-50 font-sans dark:bg-black">
        <div className="flex w-full max-w-sm flex-col items-center gap-3 rounded-2xl bg-white p-10 text-center shadow-sm dark:bg-zinc-900">
          <h1 className="text-xl font-semibold text-black dark:text-zinc-50">Регистрация прошла успешно</h1>
          <p className="text-zinc-600 dark:text-zinc-400">
            Аккаунт ожидает одобрения администратором. После одобрения вы сможете войти.
          </p>
          <Link href="/login" className="mt-2 text-sm text-zinc-500 underline">
            К странице входа
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 items-center justify-center bg-zinc-50 font-sans dark:bg-black">
      <form
        onSubmit={handleSubmit}
        className="flex w-full max-w-sm flex-col gap-4 rounded-2xl bg-white p-10 shadow-sm dark:bg-zinc-900"
      >
        <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">Регистрация</h1>
        <input
          type="email"
          required
          placeholder="Email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          className="rounded-lg border border-solid border-black/[.08] px-4 py-2 text-sm dark:border-white/[.145] dark:bg-zinc-800"
        />
        <input
          type="password"
          required
          minLength={8}
          placeholder="Пароль (не короче 8 символов)"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className="rounded-lg border border-solid border-black/[.08] px-4 py-2 text-sm dark:border-white/[.145] dark:bg-zinc-800"
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={submitting}
          className="rounded-full bg-foreground px-5 py-2.5 text-background transition-colors hover:bg-[#383838] disabled:opacity-50 dark:hover:bg-[#ccc]"
        >
          {submitting ? "Регистрируем…" : "Зарегистрироваться"}
        </button>
        <Link href="/login" className="text-center text-sm text-zinc-500 underline">
          Уже есть аккаунт? Войти
        </Link>
      </form>
    </div>
  );
}
