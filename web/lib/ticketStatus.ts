export const TICKET_STATUS_LABELS: Record<string, string> = {
  new: "Новый",
  investigating: "Разбираемся",
  fix_ready: "Решение готово",
  deployed: "Исправлено",
  rejected: "Отклонён",
  need_info: "Нужны детали",
};

export function statusLabel(status: string): string {
  return TICKET_STATUS_LABELS[status] ?? status;
}
