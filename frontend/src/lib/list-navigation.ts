import type { ArticleListItem, Shelf } from "./types";

const FOLDER_SHELVES = new Set(["vault", "additions", "books", "notes", "schoolwork"]);

/** Lists that may filter to unread-only in the API. */
export function shelfSupportsUnreadFilter(shelf: Shelf): boolean {
  return shelf.kind === "inbox" || shelf.kind === "category" || shelf.kind === "feed";
}

export function listShowsUnreadOnly(shelf: Shelf, unreadOnlyFilter: boolean): boolean {
  return shelf.kind === "unread" || (unreadOnlyFilter && shelfSupportsUnreadFilter(shelf));
}

/** After mark-read, remove the row from the visible list (Unread / RSS). */
export function listRemovesOnRead(shelf: Shelf): boolean {
  if (shelf.kind === "unread" || shelf.kind === "feed") return true;
  if (shelf.kind === "inbox" || shelf.kind === "saved" || shelf.kind === "starred") return false;
  if (shelf.kind === "category" || shelf.kind === "tag" || shelf.kind === "search") return false;
  if (FOLDER_SHELVES.has(shelf.kind)) return false;
  return false;
}

export function dedupeArticlesById(list: ArticleListItem[]): ArticleListItem[] {
  const seen = new Set<string>();
  const rows: ArticleListItem[] = [];
  for (const item of list) {
    if (!item?.id || seen.has(item.id)) continue;
    seen.add(item.id);
    rows.push(item);
  }
  return rows;
}

/** Next DISTINCT row in the current list. Never returns currentId. Never wraps. */
export function nextDistinctArticle(list: ArticleListItem[], currentId: string | null): ArticleListItem | null {
  const rows = dedupeArticlesById(list);
  if (!rows.length) return null;
  if (!currentId) return rows[0] ?? null;
  const index = rows.findIndex((row) => row.id === currentId);
  if (index === -1) {
    return rows.find((row) => row.id !== currentId) ?? null;
  }
  return rows[index + 1] ?? null;
}

export function prevDistinctArticle(list: ArticleListItem[], currentId: string | null): ArticleListItem | null {
  const rows = dedupeArticlesById(list);
  if (!rows.length || !currentId) return null;
  const index = rows.findIndex((row) => row.id === currentId);
  if (index <= 0) return null;
  return rows[index - 1] ?? null;
}

/**
 * API offset for the next page.
 * Unread queries shrink as rows are marked read — use the visible length.
 * Other lists keep read rows in the API — use how many were fetched, not spliced.
 */
export function listNextPageOffset(opts: {
  unreadApi: boolean;
  visibleCount: number;
  fetchedCount: number;
}): number {
  return opts.unreadApi ? Math.max(0, opts.visibleCount) : Math.max(0, opts.fetchedCount);
}

/** @deprecated index math wrapped after splice; use nextDistinctArticle. */
export function nextRowIndex(currentIndex: number, removeFromList: boolean): number {
  return removeFromList ? currentIndex : currentIndex + 1;
}

export function pickAdvanceTarget(
  list: ArticleListItem[],
  currentIndex: number,
  removeFromList: boolean,
): ArticleListItem | null {
  const rows = dedupeArticlesById(list);
  const current = rows[currentIndex];
  if (removeFromList) {
    return nextDistinctArticle(rows, current?.id ?? null);
  }
  return nextDistinctArticle(rows, current?.id ?? null);
}
