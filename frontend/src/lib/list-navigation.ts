import type { ArticleListItem, Shelf } from "./types";

export function shelfSupportsUnreadFilter(shelf: Shelf): boolean {
  return shelf.kind === "inbox" || shelf.kind === "feed" || shelf.kind === "category";
}

export function listShowsUnreadOnly(shelf: Shelf, unreadOnlyFilter: boolean): boolean {
  return shelf.kind === "unread" || (unreadOnlyFilter && shelfSupportsUnreadFilter(shelf));
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
