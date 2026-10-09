"use client";

import { useCallback, type Dispatch, type SetStateAction } from "react";
import { toast } from "sonner";
import { ApiError, api } from "@/lib/api";
import { shelfKey } from "@/lib/library-utils";
import type {
  Article,
  ArticleListItem,
  Backup,
  Category,
  Feed,
  Folder,
  RssShelf,
  Shelf,
  Stats,
  Tag,
} from "@/lib/types";

const LIST_PAGE = 40;

type ListDebug = { offset: number; startIndex: number; count: number };

type UseLibraryListOptions<TCustomNoteShelves> = {
  shelf: Shelf;
  items: ArticleListItem[];
  setItems: Dispatch<SetStateAction<ArticleListItem[]>>;
  total: number;
  setTotal: Dispatch<SetStateAction<number>>;
  loadingList: boolean;
  loadingMore: boolean;
  setLoadingList: Dispatch<SetStateAction<boolean>>;
  setLoadingMore: Dispatch<SetStateAction<boolean>>;
  listError: string | null;
  setListError: Dispatch<SetStateAction<string | null>>;
  selectedId: string | null;
  setSelectedId: Dispatch<SetStateAction<string | null>>;
  article: Article | null;
  setArticle: Dispatch<SetStateAction<Article | null>>;
  query: string;
  unreadOnlyFilter: boolean;
  feeds: Feed[];
  categories: Category[];
  rssShelves: RssShelf[];
  folders: Folder[];
  customNoteShelves: TCustomNoteShelves;
  activeRssShelfId: string | null;
  setActiveRssShelfId: Dispatch<SetStateAction<string | null>>;
  listEpoch: number;
  listFirstOffset: number;
  listFirstPage: number;
  listFirstFetchUrl: string;
  listDebug: ListDebug;
  readerScrollToken: number;
  setReaderScrollToken: Dispatch<SetStateAction<number>>;
  itemsRef: { current: ArticleListItem[] };
  totalRef: { current: number };
  selectedIdRef: { current: string | null };
  listGenRef: { current: number };
  loadMoreGenRef: { current: number };
  firstPageReadyRef: { current: boolean };
  loadingMoreRef: { current: boolean };
  listFeedKeyRef: { current: string };
  shelfRef: { current: Shelf };
  loadListRef: { current: (() => Promise<void>) | null };
  fetchedCountRef: { current: number };
  unreadOnlyFilterRef: { current: boolean };
  setRssShelves: Dispatch<SetStateAction<RssShelf[]>>;
  setFeeds: Dispatch<SetStateAction<Feed[]>>;
  setCategories: Dispatch<SetStateAction<Category[]>>;
  setTags: Dispatch<SetStateAction<Tag[]>>;
  setFolders: Dispatch<SetStateAction<Folder[]>>;
  setStats: Dispatch<SetStateAction<Stats | null>>;
  setBackups: Dispatch<SetStateAction<Backup[]>>;
  setLoadingArticle: Dispatch<SetStateAction<boolean>>;
  setListEpoch: Dispatch<SetStateAction<number>>;
  setListFirstOffset: Dispatch<SetStateAction<number>>;
  setListFirstPage: Dispatch<SetStateAction<number>>;
  setListFirstFetchUrl: Dispatch<SetStateAction<string>>;
  setListDebug: Dispatch<SetStateAction<ListDebug>>;
  RSS_SHELF_KEY: string;
  articlePreviewFromListItem: (item: ArticleListItem) => Article;
  listShowsUnreadOnly: (shelf: Shelf, unreadOnlyFilter: boolean) => boolean;
  shelfFolderId: (shelf: Shelf) => string | undefined;
  dedupeArticlesById: (list: ArticleListItem[]) => ArticleListItem[];
  listNextPageOffset: (opts: { unreadApi: boolean; visibleCount: number; fetchedCount: number }) => number;
  initialListDebug: ListDebug;
};

export function useLibraryList<TCustomNoteShelves>({
  shelf,
  items,
  setItems,
  total,
  setTotal,
  loadingList,
  loadingMore,
  setLoadingList,
  setLoadingMore,
  listError,
  setListError,
  selectedId,
  setSelectedId,
  article,
  setArticle,
  query,
  unreadOnlyFilter,
  feeds,
  categories,
  rssShelves,
  folders,
  customNoteShelves,
  activeRssShelfId,
  setActiveRssShelfId,
  listEpoch,
  listFirstOffset,
  listFirstPage,
  listFirstFetchUrl,
  listDebug,
  readerScrollToken,
  setReaderScrollToken,
  itemsRef,
  totalRef,
  selectedIdRef,
  listGenRef,
  loadMoreGenRef,
  firstPageReadyRef,
  loadingMoreRef,
  listFeedKeyRef,
  shelfRef,
  loadListRef,
  fetchedCountRef,
  unreadOnlyFilterRef,
  setRssShelves,
  setFeeds,
  setCategories,
  setTags,
  setFolders,
  setStats,
  setBackups,
  setLoadingArticle,
  setListEpoch,
  setListFirstOffset,
  setListFirstPage,
  setListFirstFetchUrl,
  setListDebug,
  RSS_SHELF_KEY,
  articlePreviewFromListItem,
  listShowsUnreadOnly,
  shelfFolderId,
  dedupeArticlesById,
  listNextPageOffset,
  initialListDebug,
}: UseLibraryListOptions<TCustomNoteShelves>) {
  const loadNav = useCallback(async (rssShelfId?: string | null) => {
    const shelves = await api.rssShelves();
    setRssShelves(shelves);
    const stored = typeof window !== "undefined" ? window.localStorage.getItem(RSS_SHELF_KEY) : null;
    const resolved =
      (rssShelfId && shelves.some((row) => row.id === rssShelfId) && rssShelfId) ||
      (stored && shelves.some((row) => row.id === stored) ? stored : null) ||
      shelves[0]?.id ||
      null;
    setActiveRssShelfId(resolved);
    if (resolved && typeof window !== "undefined") window.localStorage.setItem(RSS_SHELF_KEY, resolved);
    const [nextFeeds, nextCategories, nextTags, nextFolders, nextStats, nextBackups] = await Promise.all([
      api.feeds(resolved ? { shelfId: resolved } : undefined),
      api.categories(resolved ?? undefined),
      api.tags(),
      api.folders(),
      api.stats(),
      api.backups(),
    ]);
    setFeeds(nextFeeds);
    setCategories(nextCategories);
    setTags(nextTags);
    setFolders(nextFolders);
    setStats(nextStats);
    setBackups(nextBackups);
    return resolved;
  }, []);

  const loadArticleById = useCallback(async (id: string, preview?: Article) => {
    if (preview) {
      setArticle(preview);
    }
    setLoadingArticle(true);
    try {
      const next = await api.article(id);
      if (selectedIdRef.current !== id) return;
      const listed = itemsRef.current.find((item) => item.id === next.id);
      setArticle(listed?.is_read && !next.is_read ? { ...next, is_read: true } : next);
      setReaderScrollToken((current) => current + 1);
    } catch (error) {
      if (selectedIdRef.current === id) {
        toast.error(error instanceof ApiError ? error.message : "Could not open article");
      }
    } finally {
      if (selectedIdRef.current === id) {
        setLoadingArticle(false);
      }
    }
  }, []);

  const selectArticle = useCallback(
    (item: ArticleListItem) => {
      const id = item.id;
      const preview = articlePreviewFromListItem(item);
      selectedIdRef.current = id;
      setSelectedId(id);
      setArticle(preview);
      void loadArticleById(id, preview);
      if (item.is_read) return;
      setItems((current) => {
        const rows = current.map((row) => (row.id === id ? { ...row, is_read: true } : row));
        itemsRef.current = itemsRef.current.map((row) => (row.id === id ? { ...row, is_read: true } : row));
        return rows;
      });
      void api
        .patchArticle(id, { is_read: true })
        .then((next) => {
          if (selectedIdRef.current !== id) return;
          setArticle((current) =>
            current && current.id === id ? { ...current, is_read: next.is_read, read_at: next.read_at } : current,
          );
          setItems((current) => {
            const rows = current.map((row) => (row.id === id ? { ...row, is_read: next.is_read, read_at: next.read_at } : row));
            itemsRef.current = itemsRef.current.map((row) =>
              row.id === id ? { ...row, is_read: next.is_read, read_at: next.read_at } : row,
            );
            return rows;
          });
          void loadNav();
        })
        .catch(() => {
          setItems((current) => {
            const rows = current.map((row) => (row.id === id ? { ...row, is_read: false } : row));
            itemsRef.current = itemsRef.current.map((row) => (row.id === id ? { ...row, is_read: false } : row));
            return rows;
          });
        });
    },
    [loadArticleById, loadNav],
  );

  const openArticle = useCallback(
    (id: string) => {
      const row = itemsRef.current.find((item) => item.id === id);
      if (row) {
        selectArticle(row);
        return;
      }
      selectedIdRef.current = id;
      setSelectedId(id);
      void loadArticleById(id);
    },
    [loadArticleById, selectArticle],
  );

  const fetchShelfPage = useCallback(async (offset: number, firstPage = false) => {
    const page = Math.floor(offset / LIST_PAGE) + 1;
    if (firstPage && offset !== 0) {
      console.error("[StoryKeep] first shelf page requested with non-zero offset", { offset, shelf: shelfKey(shelf) });
    }
    if (shelf.kind === "search") {
      const url = `/api/v1/search?q=${encodeURIComponent(shelf.q)}&limit=${LIST_PAGE}&offset=${offset}`;
      console.info("[StoryKeep] list fetch", { url, offset, page, firstPage, feed: shelfKey(shelf) });
      const result = await api.search(shelf.q, { limit: LIST_PAGE, offset });
      return {
        items: result.items.map((hit) => ({ ...hit.article, summary: hit.headline ?? hit.article.summary })),
        total: result.total,
        offset,
        page,
        url,
      };
    }
    const params: Record<string, string | number | boolean> = { limit: LIST_PAGE, offset };
    if (listShowsUnreadOnly(shelf, unreadOnlyFilter)) params.read = false;
    if (shelf.kind === "saved") params.saved = true;
    if (shelf.kind === "starred") params.starred = true;
    if (shelf.kind === "vault") params.shelf = "vault";
    if (shelf.kind === "additions") params.shelf = "additions";
    if (shelf.kind === "books") params.shelf = "books";
    if (shelf.kind === "notes") params.shelf = "notes";
    if (shelf.kind === "schoolwork") params.shelf = "schoolwork";
    if (shelf.kind === "custom") params.shelf = shelf.id;
    const folderId = shelfFolderId(shelf);
    if (folderId) params.folder_id = folderId;
    if (shelf.kind === "feed") params.feed_id = shelf.id;
    if (shelf.kind === "category") params.category_id = shelf.id;
    if (shelf.kind === "tag") params.tag_id = shelf.id;
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") search.set(key, String(value));
    }
    const url = `/api/v1/articles?${search.toString()}`;
    console.info("[StoryKeep] list fetch", { url, offset, page, firstPage, feed: shelfKey(shelf) });
    const result = await api.articles(params);
    return { items: result.items, total: result.total, offset, page, url };
  }, [shelf, unreadOnlyFilter]);

  const loadList = useCallback(async () => {
    const feed = shelfKey(shelf);
    listFeedKeyRef.current = feed;
    const gen = ++listGenRef.current;
    loadMoreGenRef.current += 1;
    firstPageReadyRef.current = false;
    loadingMoreRef.current = false;
    itemsRef.current = [];
    fetchedCountRef.current = 0;
    setLoadingMore(false);
    setLoadingList(true);
    setListError(null);
    setListFirstOffset(0);
    setListFirstPage(1);
    setListFirstFetchUrl("");
    setListDebug(initialListDebug);
    setItems([]);
    try {
      const result = await fetchShelfPage(0, true);
      const unique = dedupeArticlesById(result.items);
      if (gen !== listGenRef.current) return;
      itemsRef.current = unique;
      fetchedCountRef.current = result.items.length;
      setItems(unique);
      setTotal(result.total);
      setListFirstOffset(result.offset);
      setListFirstPage(result.page);
      setListFirstFetchUrl(result.url);
      firstPageReadyRef.current = true;
      setListEpoch((current) => current + 1);
    } catch (error) {
      if (gen !== listGenRef.current) return;
      setListError(error instanceof ApiError ? error.message : "Could not load articles");
    } finally {
      if (gen === listGenRef.current) setLoadingList(false);
    }
  }, [fetchShelfPage]);
  loadListRef.current = loadList;

  const loadMore = useCallback(async () => {
    if (!firstPageReadyRef.current || loadingMoreRef.current || loadingList) return;
    const visible = itemsRef.current.length;
    const tot = totalRef.current;
    if (tot > 0 && visible >= tot && fetchedCountRef.current >= tot) return;
    const unreadApi = listShowsUnreadOnly(shelfRef.current, unreadOnlyFilterRef.current);
    const offset = listNextPageOffset({
      unreadApi,
      visibleCount: visible,
      fetchedCount: fetchedCountRef.current,
    });
    if (offset > 0 && tot > 0 && offset >= tot) return;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    const listGen = listGenRef.current;
    const loadMoreGen = loadMoreGenRef.current;
    try {
      const result = await fetchShelfPage(offset);
      if (listGen !== listGenRef.current || loadMoreGen !== loadMoreGenRef.current) return;
      if (!result.items.length) {
        setTotal(itemsRef.current.length);
        return;
      }
      setItems(() => {
        const next = dedupeArticlesById([...itemsRef.current, ...result.items]);
        itemsRef.current = next;
        if (unreadApi) {
          fetchedCountRef.current = next.length;
        } else {
          fetchedCountRef.current += result.items.length;
        }
        return next;
      });
      setTotal(result.total);
    } catch (error) {
      if (listGen !== listGenRef.current || loadMoreGen !== loadMoreGenRef.current) return;
      toast.error(error instanceof ApiError ? error.message : "Could not load more articles");
    } finally {
      if (listGen === listGenRef.current && loadMoreGen === loadMoreGenRef.current) {
        loadingMoreRef.current = false;
        setLoadingMore(false);
      }
    }
  }, [fetchShelfPage, loadingList]);

  return {
    loadNav,
    loadArticleById,
    selectArticle,
    openArticle,
    fetchShelfPage,
    loadList,
    loadMore,
    items,
    total,
    loadingList,
    loadingMore,
    listError,
    selectedId,
    article,
    query,
    unreadOnlyFilter,
    listEpoch,
    listFirstOffset,
    listFirstPage,
    listFirstFetchUrl,
    listDebug,
    readerScrollToken,
    feeds,
    categories,
    rssShelves,
    folders,
    customNoteShelves,
    activeRssShelfId,
  };
}
