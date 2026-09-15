/** Week starts Sunday (US). */

export function startOfDay(date: Date): Date {
  const next = new Date(date);
  next.setHours(0, 0, 0, 0);
  return next;
}

export function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

export function startOfWeek(date: Date): Date {
  const start = startOfDay(date);
  return addDays(start, -start.getDay());
}

export function startOfMonth(date: Date): Date {
  const start = startOfDay(date);
  start.setDate(1);
  return start;
}

export function weekRange(anchor: Date): { start: Date; end: Date } {
  const start = startOfWeek(anchor);
  return { start, end: addDays(start, 7) };
}

export function monthGridRange(anchor: Date): { start: Date; end: Date } {
  const monthStart = startOfMonth(anchor);
  const start = startOfWeek(monthStart);
  const end = addDays(start, 42);
  return { start, end };
}

export function toRfc3339(date: Date): string {
  return date.toISOString();
}

export function formatEventWhen(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function localInputValue(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}T${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`;
}

export function fromLocalInput(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toISOString();
}

export function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}
