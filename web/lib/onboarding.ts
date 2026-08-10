const KEY_PREFIX = "transcribator:onboarding-seen:";

export function hasSeenOnboarding(userId: string): boolean {
  return localStorage.getItem(KEY_PREFIX + userId) === "1";
}

export function markOnboardingSeen(userId: string): void {
  localStorage.setItem(KEY_PREFIX + userId, "1");
}
