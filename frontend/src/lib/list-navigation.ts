import type { ArticleListItem, Shelf } from "./types";

const FOLDER_SHELVES = new Set(["vault", "additions", "books", "notes", "schoolwork"]);

/** Lists that may filter to unread-only in the API (not feed reading queues). */
export function shelfSupportsUnreadFilter(shelf: Shelf): boolean {
  return shelf.kind === "inbox" || shelf.kind === "category";
}

export function listShowsUnreadOnly(shelf: Shelf, unreadOnlyFilter: boolean): boolean {
  return shelf.kind === "unread" || (unreadOnlyFilter && shelfSupportsUnreadFilter(shelf));
}

/** After mark-read, remove the row from the visible list (open or Next). */
export function listRemovesOnRead(shelf: Shelf): boolean {
  if (shelf.kind === "unread" || shelf.kind === "feed") return true;
  if (shelf.kind === "inbox" || shelf.kind === "saved" || shelf.kind === "starred") return false;
  if (shelf.kind === "category" || shelf.kind === "tag" || shelf.kind === "search") return false;
  if (FOLDER_SHELVES.has(shelf.kind)) return false;
  return false;
}

/** Index of the row to open after Next, given the current index in the visible list. */
export function nextRowIndex(currentIndex: number, removeFromList: boolean): number {
  return removeFromList ? currentIndex : currentIndex + 1;
}

export function pickAdvanceTarget(
  list: ArticleListItem[],
  currentIndex: number,
  removeFromList: boolean,
): ArticleListItem | null {
  const targetIndex = nextRowIndex(currentIndex, removeFromList);
  return list[targetIndex] ?? null;
}
