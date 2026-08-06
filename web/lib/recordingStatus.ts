export const STATUS_LABELS: Record<string, string> = {
  queued: "В очереди",
  extracting: "Извлекаем аудио",
  transcribing: "Распознаём речь",
  summarizing: "Готовим сводку",
  done: "Готово",
  partial: "Частично обработана",
  failed: "Ошибка обработки",
};

export const TERMINAL_STATUSES = new Set(["done", "partial", "failed"]);
export const IN_PROGRESS_STATUSES = new Set(["extracting", "transcribing"]);

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}
