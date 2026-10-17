export function formatDuration(totalSeconds: number): string {
  const s = Math.round(totalSeconds);
  const minutes = Math.floor(s / 60);
  const seconds = s % 60;
  if (minutes === 0) return `${seconds} s`;
  if (seconds === 0) return `${minutes} min`;
  return `${minutes} min ${seconds} s`;
}

export function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many;
}
