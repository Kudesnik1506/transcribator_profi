"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { type CurrentUser } from "@/lib/api";
import { clearToken } from "@/lib/auth";

type NavItem = {
  href: string;
  label: string;
  exact?: boolean;
};

const BASE_NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Новая запись", exact: true },
  { href: "/recordings", label: "Мои записи" },
  { href: "/tickets", label: "Поддержка" },
  { href: "/profile", label: "Профиль" },
];

function isActive(pathname: string, item: NavItem): boolean {
  if (item.exact) return pathname === item.href;
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

function navLinkClassName(active: boolean): string {
  return [
    "whitespace-nowrap border-b-2 px-1 py-1 text-sm font-medium transition-colors",
    active
      ? "border-foreground text-black dark:text-zinc-50"
      : "border-transparent text-zinc-500 hover:text-black dark:hover:text-zinc-50",
  ].join(" ");
}

export function AppHeader({ user, onOpenTour }: { user: CurrentUser; onOpenTour?: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);

  const navItems: NavItem[] = user.role === "admin" ? [...BASE_NAV_ITEMS, { href: "/admin", label: "Админка" }] : BASE_NAV_ITEMS;

  function handleLogout() {
    clearToken();
    router.push("/login");
  }

  return (
    <header className="border-b border-solid border-black/[.08] px-6 dark:border-white/[.145]">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4">
        <div className="flex items-center gap-6">
          <Link href="/" className="shrink-0 font-semibold text-black dark:text-zinc-50">
            Транскрибатор
          </Link>
          <nav className="hidden items-center gap-5 lg:flex">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                data-tour-nav={item.href}
                className={navLinkClassName(isActive(pathname, item))}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>

        <div className="hidden shrink-0 items-center gap-4 lg:flex">
          <span className="max-w-[220px] truncate text-sm text-zinc-500" title={user.email}>
            {user.email}
          </span>
          {onOpenTour && (
            <button
              onClick={onOpenTour}
              aria-label="Показать обучение"
              title="Показать обучение"
              className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-solid border-black/[.15] text-xs text-zinc-500 transition-colors hover:bg-black/[.04] dark:border-white/[.2] dark:hover:bg-white/[.06]"
            >
              ?
            </button>
          )}
          <button
            onClick={handleLogout}
            className="shrink-0 text-sm text-zinc-500 underline hover:text-black dark:hover:text-zinc-50"
          >
            Выйти
          </button>
        </div>

        <button
          onClick={() => setMenuOpen((open) => !open)}
          aria-label={menuOpen ? "Закрыть меню" : "Открыть меню"}
          aria-expanded={menuOpen}
          className="flex h-9 w-9 items-center justify-center rounded-lg text-zinc-500 hover:bg-black/[.04] lg:hidden dark:hover:bg-white/[.06]"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} className="h-5 w-5">
            {menuOpen ? (
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5M3.75 17.25h16.5" />
            )}
          </svg>
        </button>
      </div>

      {menuOpen && (
        <nav className="flex flex-col gap-1 border-t border-solid border-black/[.08] py-3 lg:hidden dark:border-white/[.145]">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setMenuOpen(false)}
              className={[
                "rounded-lg px-3 py-2 text-sm font-medium",
                isActive(pathname, item)
                  ? "bg-black/[.04] text-black dark:bg-white/[.06] dark:text-zinc-50"
                  : "text-zinc-500",
              ].join(" ")}
            >
              {item.label}
            </Link>
          ))}
          <div className="mt-2 flex items-center justify-between gap-3 border-t border-solid border-black/[.08] px-3 pt-3 dark:border-white/[.145]">
            <span className="min-w-0 truncate text-sm text-zinc-500" title={user.email}>
              {user.email}
            </span>
            <div className="flex shrink-0 items-center gap-3">
              {onOpenTour && (
                <button
                  onClick={() => {
                    setMenuOpen(false);
                    onOpenTour();
                  }}
                  className="text-sm text-zinc-500 underline"
                >
                  Обучение
                </button>
              )}
              <button onClick={handleLogout} className="text-sm text-zinc-500 underline">
                Выйти
              </button>
            </div>
          </div>
        </nav>
      )}
    </header>
  );
}
