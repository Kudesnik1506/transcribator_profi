import { beforeEach, describe, expect, it } from "vitest";

import { hasSeenOnboarding, markOnboardingSeen } from "@/lib/onboarding";

function createMemoryLocalStorage(): Storage {
  const store = new Map<string, string>();
  return {
    getItem: (key) => store.get(key) ?? null,
    setItem: (key, value) => void store.set(key, value),
    removeItem: (key) => void store.delete(key),
    clear: () => store.clear(),
    key: (index) => Array.from(store.keys())[index] ?? null,
    get length() {
      return store.size;
    },
  };
}

beforeEach(() => {
  globalThis.localStorage = createMemoryLocalStorage();
});

describe("hasSeenOnboarding / markOnboardingSeen", () => {
  it("is false for a user who hasn't seen the onboarding yet", () => {
    expect(hasSeenOnboarding("user-1")).toBe(false);
  });

  it("becomes true after marking as seen", () => {
    markOnboardingSeen("user-1");

    expect(hasSeenOnboarding("user-1")).toBe(true);
  });

  it("does not leak between different user ids", () => {
    markOnboardingSeen("user-1");

    expect(hasSeenOnboarding("user-2")).toBe(false);
  });
});
