"use client";

import { type Dispatch, type SetStateAction } from "react";
import { toast } from "sonner";
import { ApiError, api } from "@/lib/api";
import type {
  Article,
  ArticleListItem,
  Category,
  Feed,
  Folder,
  FolderShelfKind,
  RssShelf,
  Shelf,
} from "@/lib/types";

type FilingDestination = string;
type NoteShelf = { id: string; name: string };

type UseFeedManagementOptions = {
  feeds: Feed[];
  setFeeds: Dispatch<SetStateAction<Feed[]>>;
  categories: Category[];
  rssShelves: RssShelf[];
  folders: Folder[];
  customNoteShelves: NoteShelf[];
  setCustomNoteShelves: Dispatch<SetStateAction<NoteShelf[]>>;
  setItems: Dispatch<SetStateAction<ArticleListItem[]>>;
  selectedIds: string[];
  setSelectedIds: Dispatch<SetStateAction<string[]>>;
  feedToRemove: Feed | null;
  setFeedToRemove: Dispatch<SetStateAction<Feed | null>>;
  articleToDelete: ArticleListItem | null;
  refreshing: boolean;
  setRefreshing: Dispatch<SetStateAction<boolean>>;
  shelf: Shelf;
  setShelf: Dispatch<SetStateAction<Shelf>>;
  article: Article | null;
  setArticle: Dispatch<SetStateAction<Article | null>>;
  selectedId: string | null;
  setSelectedId: Dispatch<SetStateAction<string | null>>;
  selectedIdRef: { current: string | null };
  activeRssShelfId: string | null;
  setActiveRssShelfId: Dispatch<SetStateAction<string | null>>;
  loadNav: (rssShelfId?: string | null) => Promise<unknown>;
  loadList: () => Promise<unknown>;
  RSS_SHELF_KEY: string;
  isFeedId: (value: string | null | undefined) => boolean;
  comparePinned: (a: ArticleListItem, b: ArticleListItem) => number;
  uniqueShelfId: (name: string, shelves: NoteShelf[]) => string;
  parseCustomNoteShelves: (preferences: Record<string, unknown> | undefined) => NoteShelf[];
  destinationLabel: (value: string, shelves: NoteShelf[]) => string;
  isFolderShelf: (shelf: Shelf) => shelf is Extract<Shelf, { kind: FolderShelfKind | "custom" }>;
};

export function useFeedManagement({
  feeds,
  setFeeds,
  categories,
  rssShelves,
  folders,
  customNoteShelves,
  setCustomNoteShelves,
  setItems,
  selectedIds,
  setSelectedIds,
  feedToRemove,
  setFeedToRemove,
  articleToDelete,
  refreshing,
  setRefreshing,
  shelf,
  setShelf,
  article,
  setArticle,
  selectedId,
  setSelectedId,
  selectedIdRef,
  activeRssShelfId,
  setActiveRssShelfId,
  loadNav,
  loadList,
  RSS_SHELF_KEY,
  isFeedId,
  comparePinned,
  uniqueShelfId,
  parseCustomNoteShelves,
  destinationLabel,
  isFolderShelf,
}: UseFeedManagementOptions) {
  async function onRefresh() {
    setRefreshing(true);
    try {
      let created = 0;
      if (shelf.kind === "feed") {
        if (!isFeedId(shelf.id)) {
          toast.error("Invalid feed");
          return;
        }
        const result = await api.refreshFeed(shelf.id);
        created = result.created;
      } else {
        const result = await api.refreshAll();
        created = result.created;
      }
      toast.success(created ? `${created} new articles` : "Feeds are up to date");
      await Promise.all([loadNav(), loadList()]);
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "Refresh failed";
      if (error instanceof ApiError && (error.status === 400 || error.status === 422)) {
        toast.error(/invalid feed|valid uuid/i.test(message) ? "Invalid feed" : "Refresh failed");
      } else {
        toast.error(message);
      }
    } finally {
      setRefreshing(false);
    }
  }

  async function pinListItem(item: ArticleListItem) {
    const pinned = !item.pinned;
    try {
      const next = await api.patchArticle(item.id, { pinned });
      setItems((current) => {
        const mapped = current.map((row) => (row.id === item.id ? { ...row, ...next, pinned } : row));
        mapped.sort((a, b) => comparePinned(a, b));
        return mapped;
      });
      if (article?.id === item.id) setArticle((current) => (current ? { ...current, pinned } : current));
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not pin that note");
    }
  }

  async function patchSelected(body: Partial<Pick<Article, "is_read" | "is_saved" | "is_starred">>) {
    if (!selectedId || !article) return;
    const id = selectedId;
    const previous = article;
    const optimistic = { ...previous, ...body };
    setArticle(optimistic);
    setItems((current) => current.map((item) => (item.id === previous.id ? { ...item, ...body } : item)));
    try {
      const next = await api.patchArticle(id, body);
      if (selectedIdRef.current === id) {
        setArticle(next);
      }
      setItems((current) => current.map((item) => (item.id === next.id ? { ...item, ...next } : item)));
      if (body.is_saved !== undefined) {
        toast.success(next.is_saved ? "Saved for life" : "Removed from saved");
      } else if (body.is_starred !== undefined) {
        toast.success(next.is_starred ? "Starred" : "Unstarred");
      } else if (body.is_read !== undefined) {
        toast.success(next.is_read ? "Marked read" : "Marked unread");
      }
      void loadNav();
    } catch (error) {
      if (selectedIdRef.current === id) {
        setArticle(previous);
      }
      setItems((current) => current.map((item) => (item.id === previous.id ? { ...item, ...previous } : item)));
      toast.error(error instanceof ApiError ? error.message : "Could not update that article");
    }
  }

  async function deleteArticleItem(item: ArticleListItem) {
    try {
      await api.deleteArticle(item.id);
      setItems((current) => current.filter((row) => row.id !== item.id));
      setSelectedIds((current) => current.filter((id) => id !== item.id));
      if (selectedId === item.id) {
        setSelectedId(null);
        setArticle(null);
      }
      toast.success("Removed from StoryKeep");
      await Promise.all([loadNav(), loadList()]);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not delete that item");
    }
  }

  async function onBulk(body: { is_read?: boolean; is_saved?: boolean }) {
    if (!selectedIds.length) return;
    try {
      const result = await api.bulkArticles(selectedIds, body);
      const label = body.is_saved
        ? "saved"
        : body.is_read
          ? "marked read"
          : "marked unread";
      toast.success(`${result.updated} ${label}`);
      const chosen = new Set(selectedIds);
      setSelectedIds([]);
      if (selectedId && chosen.has(selectedId) && article) {
        setArticle({
          ...article,
          ...(body.is_read !== undefined ? { is_read: body.is_read } : {}),
          ...(body.is_saved !== undefined ? { is_saved: body.is_saved } : {}),
        });
      }
      await Promise.all([loadNav(), loadList()]);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not update articles");
    }
  }

  async function onMarkFeedRead(feed: Feed) {
    try {
      const result = await api.markFeedRead(feed.id);
      toast.success(result.updated ? `Marked ${result.updated} articles read` : "This feed is already read");
      await Promise.all([loadNav(), loadList()]);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not mark feed read");
    }
  }

  async function onAddRssShelf(): Promise<string | null> {
    const name = window.prompt("New shelf name:")?.trim();
    if (!name) return null;
    try {
      const row = await api.createRssShelf(name);
      await loadNav(row.id);
      toast.success(`Added shelf ${row.name}`);
      return row.id;
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not add that shelf");
      return null;
    }
  }

  async function onCreateNoteShelf(): Promise<string | null> {
    const name = window.prompt("New shelf name:")?.trim();
    if (!name) return null;
    const id = uniqueShelfId(name, customNoteShelves);
    const next = [...customNoteShelves, { id, name }];
    try {
      const prefs = await api.updatePreferences({ custom_note_shelves: next });
      setCustomNoteShelves(parseCustomNoteShelves(prefs));
      await loadNav();
      toast.success(`Added shelf ${name}`);
      return id;
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not add that shelf");
      return null;
    }
  }

  async function onAddCategory() {
    if (!activeRssShelfId) return;
    const name = window.prompt("Category name on this shelf:")?.trim();
    if (!name) return;
    try {
      const category = await api.createCategory(name, activeRssShelfId);
      await loadNav(activeRssShelfId);
      toast.success(`Added ${category.name}`);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not add that category");
    }
  }

  async function onRenameCategory(category: Category) {
    try {
      await api.updateCategory(category.id, { name: category.name, color: category.color, sort_order: category.sort_order });
      await loadNav(activeRssShelfId);
      toast.success("Category renamed");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not rename that category");
    }
  }

  async function onDeleteCategory(category: Category) {
    if (!window.confirm(`Delete "${category.name}"? Its feeds move to Uncategorized.`)) return;
    try {
      await api.deleteCategory(category.id);
      await loadNav(activeRssShelfId);
      toast.success("Category deleted");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not delete that category");
    }
  }

  async function onChangeFeedCategory(feed: Feed) {
    const shelfCategories = categories.filter((row) => row.shelf_id === feed.shelf_id);
    const label = shelfCategories.map((row, index) => `${index + 1}. ${row.name}`).join("\n");
    const pick = window.prompt(`Change category for ${feed.title || "feed"}:\n${label}\nEnter number:`)?.trim();
    if (!pick) return;
    const index = Number(pick) - 1;
    const target = shelfCategories[index];
    if (!target) {
      toast.error("Pick a category number from the list");
      return;
    }
    try {
      await api.updateFeed(feed.id, { category_id: target.id });
      await loadNav(activeRssShelfId);
      toast.success(`Moved to ${target.name}`);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not move that feed");
    }
  }

  async function onRssShelfChange(nextShelfId: string) {
    setActiveRssShelfId(nextShelfId);
    if (typeof window !== "undefined") window.localStorage.setItem(RSS_SHELF_KEY, nextShelfId);
    await loadNav(nextShelfId);
    if (shelf.kind === "feed") {
      const feed = feeds.find((row) => row.id === shelf.id);
      if (feed && feed.shelf_id !== nextShelfId) setShelf({ kind: "unread" });
    }
    if (shelf.kind === "category") {
      const category = categories.find((row) => row.id === shelf.id);
      if (category && category.shelf_id !== nextShelfId) setShelf({ kind: "unread" });
    }
  }

  async function onRemoveFeed(feed: Feed, force: boolean) {
    await api.deleteFeed(feed.id, force);
    toast.success(feed.title ? `Removed ${feed.title}` : "Feed removed");
    setFeedToRemove(null);
    setFeeds((current) => current.filter((row) => row.id !== feed.id));
    if (article?.feed_id === feed.id) {
      setSelectedId(null);
      setArticle(null);
    }
    if (shelf.kind === "feed" && shelf.id === feed.id) {
      setShelf({ kind: "unread" });
    }
    await Promise.all([loadNav(), loadList()]);
  }

  async function createFolderOnShelf(shelfKind: FilingDestination) {
    const label = destinationLabel(shelfKind, customNoteShelves);
    const name = window.prompt(`New folder on ${label}:`)?.trim();
    if (!name) return null;
    try {
      const row = await api.createFolder(shelfKind, name);
      await loadNav();
      toast.success(`Folder “${name}” created.`);
      return row.id;
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not create that folder");
      return null;
    }
  }

  async function pinFolderRow(folder: Folder) {
    try {
      await api.pinFolder(folder.id, !folder.pinned);
      await loadNav();
      toast.success(folder.pinned ? "Folder unpinned." : "Folder pinned to the top of this shelf.");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not pin that folder");
    }
  }

  async function renameFolderRow(folder: Folder) {
    const name = window.prompt("Rename folder:", folder.name)?.trim();
    if (!name || name === folder.name) return;
    try {
      await api.renameFolder(folder.id, folder.shelf, name);
      await loadNav();
      toast.success("Folder renamed.");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not rename that folder");
    }
  }

  async function deleteFolderRow(folder: Folder) {
    const shelfLabel = destinationLabel(folder.shelf, customNoteShelves);
    if (!window.confirm(`Delete folder “${folder.name}”? Notes stay on ${shelfLabel}.`)) return;
    try {
      await api.deleteFolder(folder.id);
      if (isFolderShelf(shelf) && shelf.folderId === folder.id) {
        if (shelf.kind === "custom") setShelf({ kind: "custom", id: shelf.id });
        else setShelf({ kind: shelf.kind });
      }
      await Promise.all([loadNav(), loadList()]);
      toast.success("Folder deleted. Notes moved to the shelf root.");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not delete that folder");
    }
  }


  return {
    onRefresh,
    pinListItem,
    patchSelected,
    deleteArticleItem,
    onBulk,
    onMarkFeedRead,
    onAddRssShelf,
    onCreateNoteShelf,
    onAddCategory,
    onRenameCategory,
    onDeleteCategory,
    onChangeFeedCategory,
    onRssShelfChange,
    onRemoveFeed,
    createFolderOnShelf,
    pinFolderRow,
    renameFolderRow,
    deleteFolderRow,
    feeds,
    categories,
    rssShelves,
    folders,
    customNoteShelves,
    selectedIds,
    feedToRemove,
    articleToDelete,
    refreshing,
  };
}
