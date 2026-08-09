const UNITS = ["Б", "КБ", "МБ", "ГБ"];

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} ${UNITS[0]}`;

  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < UNITS.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const formatted = value < 10 ? value.toFixed(1).replace(/\.0$/, "") : value.toFixed(0);
  return `${formatted} ${UNITS[unitIndex]}`;
}
