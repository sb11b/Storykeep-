import type { Shelf } from "@/lib/types";

export function listRangeLabel(loaded: number, total: number, kind: Shelf["kind"]): string {
  const noun = kind === "notes" ? "notes" : "articles";
  if (total === 0) return `No ${noun}`;
  if (loaded === 0) return `${total} ${noun}`;
  return `Showing 1–${loaded} of ${total}`;
}

export type ListDebug = { offset: number; startIndex: number; count: number };

export const initialListDebug: ListDebug = { offset: 0, startIndex: 0, count: 0 };
