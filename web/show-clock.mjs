export function formatStatusTimeUsec(value) {
  if (!Number.isSafeInteger(value) || value < 0) return '--';
  return `${(value / 1_000_000).toFixed(2)} s`;
}
