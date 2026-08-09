import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto flex max-w-md flex-1 flex-col items-center justify-center gap-3 px-6 py-24 text-center">
      <h1 className="text-xl font-semibold text-black dark:text-zinc-50">Страница не найдена</h1>
      <p className="text-zinc-600 dark:text-zinc-400">Такой страницы не существует или она была перемещена.</p>
      <Link
        href="/"
        className="mt-2 rounded-full bg-foreground px-5 py-2.5 text-sm text-background transition-colors hover:bg-[#383838] dark:hover:bg-[#ccc]"
      >
        На главную
      </Link>
    </main>
  );
}
