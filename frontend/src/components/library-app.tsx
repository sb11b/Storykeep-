"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Archive,
  BookOpen,
  Bookmark,
  BookmarkCheck,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronUp,
  FilePlus,
  GraduationCap,
  Inbox,
  Library,
  LoaderCircle,
  Maximize2,
  Menu,
  Minimize2,
  NotebookPen,
  Plus,
  RefreshCw,
  Search,
  Star,
  StarOff,
  Trash2,
  Volume2,
} from "lucide-react";
import { toast } from "sonner";
import { ListenControls, type ListenControlsHandle } from "@/components/listen-controls";
import { GrokBubble } from "@/components/grok-bubble";
import { CorrectionCheck, DestinationSelect } from "@/components/destination-controls";
import { NoteComposer } from "@/components/note-composer";
import { ShelfScroller } from "@/components/shelf-scroller";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import { formatRelative, sanitizeHtml, stripHtml } from "@/lib/format";
import { applyHighlights, HIGHLIGHT_COLORS, selectionInRoot } from "@/lib/highlights";
import { noteMarkdownHtml } from "@/lib/markdown";
import {
  ARTICLE_TEXT_SIZE_OPTIONS,
  articleTextSizeClass,
  readArticleTextSize,
  writeArticleTextSize,
  type ArticleTextSize,
} from "@/lib/reader-text-size";
import { asDestination, type NoteDestination } from "@/lib/destinations";
import { countWords, spokenTitle, wordIndexFromSelection, wrapHtmlWords, wrapPlainWords } from "@/lib/tts-words";
import type {
  Article,
  ArticleListItem,
  Backup,
  Category,
  Feed,
  Shelf,
  Stats,
  Tag,
  User,
} from "@/lib/types";
import { cn } from "@/lib/utils";

function isStoryKeepNote(article: Article): boolean {
  return (article.guid || "").startsWith("storykeep-note:");
}

function composedNoteMarkdown(article: Article): string {
  const fromArticle = (article.content_text || "").trim();
  if (fromArticle) return fromArticle;
  const fromOverlay = (article.overlay_additions?.[0]?.markdown || "").trim();
  if (fromOverlay) return fromOverlay;
  return "";
}

function composedNoteHtml(article: Article): string {
  const markdown = composedNoteMarkdown(article);
  if (markdown) return sanitizeHtml(noteMarkdownHtml(markdown));
  if (article.content_html) return sanitizeHtml(article.content_html);
  return "";
}

function shelfTitle(shelf: Shelf, feeds: Feed[], categories: Category[], tags: Tag[]): string {
  switch (shelf.kind) {
    case "inbox":
      return "All stories";
    case "unread":
      return "Unread";
    case "saved":
      return "Saved for life";
    case "starred":
      return "Starred";
    case "notes":
      return "Notes";
    case "vault":
      return "Vault";
    case "additions":
      return "Additions";
    case "books":
      return "Books";
    case "schoolwork":
      return "Schoolwork";
    case "search":
      return `Search: ${shelf.q}`;
    case "feed":
      return feeds.find((feed) => feed.id === shelf.id)?.title ?? "Feed";
    case "category":
      return categories.find((category) => category.id === shelf.id)?.name ?? "Category";
    case "tag":
      return tags.find((tag) => tag.id === shelf.id)?.name ?? "Tag";
  }
}

function shelfKey(shelf: Shelf): string {
  switch (shelf.kind) {
    case "feed":
    case "category":
    case "tag":
      return `${shelf.kind}:${shelf.id}`;
    case "search":
      return `search:${shelf.q}`;
    default:
      return shelf.kind;
  }
}

const LIST_PAGE = 40;

export function LibraryApp({ user }: { user: User }) {
  const router = useRouter();
  const [feeds, setFeeds] = useState<Feed[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [backups, setBackups] = useState<Backup[]>([]);
  const [items, setItems] = useState<ArticleListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [shelf, setShelf] = useState<Shelf>({ kind: "unread" });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [article, setArticle] = useState<Article | null>(null);
  const [query, setQuery] = useState("");
  const [loadingList, setLoadingList] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadingArticle, setLoadingArticle] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [backupOpen, setBackupOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [feedToRemove, setFeedToRemove] = useState<Feed | null>(null);
  const [mobileNav, setMobileNav] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [tagsOpen, setTagsOpen] = useState(false);
  const [readerFull, setReaderFull] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const noteFocusRef = useRef<(() => void) | null>(null);
  const listenRef = useRef<ListenControlsHandle>(null);
  const caretWordRef = useRef<(() => number | null) | null>(null);
  const itemsRef = useRef<ArticleListItem[]>([]);
  const totalRef = useRef(0);
  const selectedIdRef = useRef<string | null>(null);
  const listGenRef = useRef(0);
  const loadingMoreRef = useRef(false);
  itemsRef.current = items;
  totalRef.current = total;
  selectedIdRef.current = selectedId;

  const loadNav = useCallback(async () => {
    const [nextFeeds, nextCategories, nextTags, nextStats, nextBackups] = await Promise.all([
      api.feeds(),
      api.categories(),
      api.tags(),
      api.stats(),
      api.backups(),
    ]);
    setFeeds(nextFeeds);
    setCategories(nextCategories);
    setTags(nextTags);
    setStats(nextStats);
    setBackups(nextBackups);
  }, []);

  const openArticle = useCallback(
    (id: string) => {
      setSelectedId(id);
      const row = itemsRef.current.find((item) => item.id === id);
      if (row?.is_read) return;
      if (row) {
        setItems((current) => current.map((item) => (item.id === id ? { ...item, is_read: true } : item)));
      }
      void api
        .patchArticle(id, { is_read: true })
        .then((next) => {
          setArticle((current) =>
            current && current.id === id ? { ...current, is_read: next.is_read, read_at: next.read_at } : current,
          );
          setItems((current) => current.map((item) => (item.id === id ? { ...item, is_read: next.is_read } : item)));
          void loadNav();
        })
        .catch(() => {
          if (row && !row.is_read) {
            setItems((current) => current.map((item) => (item.id === id ? { ...item, is_read: false } : item)));
          }
        });
    },
    [loadNav],
  );

  const fetchShelfPage = useCallback(async (offset: number) => {
    if (shelf.kind === "search") {
      const page = await api.search(shelf.q, { limit: LIST_PAGE, offset });
      return {
        items: page.items.map((hit) => ({ ...hit.article, summary: hit.headline ?? hit.article.summary })),
        total: page.total,
      };
    }
    const params: Record<string, string | number | boolean> = { limit: LIST_PAGE, offset };
    if (shelf.kind === "unread") params.read = false;
    if (shelf.kind === "saved") params.saved = true;
    if (shelf.kind === "starred") params.starred = true;
    if (shelf.kind === "vault") params.shelf = "vault";
    if (shelf.kind === "additions") params.shelf = "additions";
    if (shelf.kind === "books") params.shelf = "books";
    if (shelf.kind === "notes") params.shelf = "notes";
    if (shelf.kind === "schoolwork") params.shelf = "schoolwork";
    if (shelf.kind === "feed") params.feed_id = shelf.id;
    if (shelf.kind === "category") params.category_id = shelf.id;
    if (shelf.kind === "tag") params.tag_id = shelf.id;
    const page = await api.articles(params);
    return { items: page.items, total: page.total };
  }, [shelf]);

  const loadList = useCallback(async () => {
    const gen = ++listGenRef.current;
    loadingMoreRef.current = false;
    setLoadingMore(false);
    setLoadingList(true);
    setListError(null);
    setItems([]);
    try {
      const page = await fetchShelfPage(0);
      if (gen !== listGenRef.current) return;
      setItems(page.items);
      setTotal(page.total);
    } catch (error) {
      if (gen !== listGenRef.current) return;
      setListError(error instanceof ApiError ? error.message : "Could not load articles");
    } finally {
      if (gen === listGenRef.current) setLoadingList(false);
    }
  }, [fetchShelfPage]);

  const loadMore = useCallback(async () => {
    if (loadingMoreRef.current || loadingList) return;
    const loaded = itemsRef.current.length;
    const tot = totalRef.current;
    if (tot > 0 && loaded >= tot) return;
    if (loaded === 0) return;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    const gen = listGenRef.current;
    try {
      const page = await fetchShelfPage(loaded);
      if (gen !== listGenRef.current) return;
      if (!page.items.length) {
        setTotal(loaded);
        return;
      }
      setItems((current) => {
        const seen = new Set(current.map((item) => item.id));
        return [...current, ...page.items.filter((item) => !seen.has(item.id))];
      });
      setTotal(page.total);
    } catch (error) {
      if (gen !== listGenRef.current) return;
      toast.error(error instanceof ApiError ? error.message : "Could not load more articles");
    } finally {
      if (gen === listGenRef.current) {
        loadingMoreRef.current = false;
        setLoadingMore(false);
      }
    }
  }, [fetchShelfPage, loadingList, shelf.kind]);

  useEffect(() => {
    void loadNav().catch((error) => {
      toast.error(error instanceof ApiError ? error.message : "Could not load library");
    });
  }, [loadNav]);

  useEffect(() => {
    const save = new URLSearchParams(window.location.search).get("save");
    if (!save) return;
    window.history.replaceState({}, "", window.location.pathname);
    void api
      .saveUrl(save)
      .then((next) => {
        toast.success("Page extracted and snapshotted");
        openArticle(next.id);
        setShelf({ kind: "saved" });
        void loadNav();
      })
      .catch((error) => {
        toast.error(error instanceof ApiError ? error.message : "Could not save that URL");
      });
  }, [loadNav, openArticle]);

  const selectRelative = useCallback(
    (delta: number) => {
      void (async () => {
        let list = itemsRef.current;
        if (!list.length) return;
        const index = selectedIdRef.current ? list.findIndex((item) => item.id === selectedIdRef.current) : -1;
        let nextIndex = index < 0 ? 0 : Math.min(list.length - 1, Math.max(0, index + delta));
        if (delta > 0 && index >= list.length - 1 && list.length < totalRef.current) {
          await loadMore();
          list = itemsRef.current;
          nextIndex = Math.min(list.length - 1, (index < 0 ? 0 : index) + 1);
        }
        const next = list[nextIndex];
        if (next) openArticle(next.id);
      })();
    },
    [loadMore, openArticle],
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing = Boolean(target?.closest("input, textarea, select, [contenteditable='true']"));
      if (event.key === "/" && !event.metaKey && !event.ctrlKey && !event.altKey) {
        if (!typing) {
          event.preventDefault();
          searchRef.current?.focus();
          searchRef.current?.select();
        }
        return;
      }
      if (event.key === "Escape" && readerFull) {
        event.preventDefault();
        setReaderFull(false);
        return;
      }
      if (typing || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "j" || event.key === "k") {
        event.preventDefault();
        selectRelative(event.key === "j" ? 1 : -1);
        return;
      }
      if (event.key === "m") {
        if (!article) return;
        event.preventDefault();
        void patchSelected({ is_read: !article.is_read });
        return;
      }
      if (event.key === "s") {
        if (!article) return;
        event.preventDefault();
        void patchSelected({ is_saved: !article.is_saved });
        return;
      }
      if (event.key === "n") {
        event.preventDefault();
        noteFocusRef.current?.();
        return;
      }
      if (event.key === "f") {
        if (!article) return;
        event.preventDefault();
        setReaderFull((current) => !current);
        return;
      }
      if (event.shiftKey && event.key.toLowerCase() === "l") {
        event.preventDefault();
        listenRef.current?.listenFromHere();
        return;
      }
      if (event.key === "l") {
        event.preventDefault();
        listenRef.current?.togglePlay();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [article, items, readerFull, selectedId, selectRelative]);

  useEffect(() => {
    void loadList();
    setSelectedIds([]);
  }, [loadList]);

  useEffect(() => {
    if (!selectedId) {
      setArticle(null);
      setReaderFull(false);
      return;
    }
    let cancelled = false;
    setLoadingArticle(true);
    api
      .article(selectedId)
      .then((next) => {
        if (cancelled) return;
        const listed = itemsRef.current.find((item) => item.id === next.id);
        setArticle(listed?.is_read && !next.is_read ? { ...next, is_read: true } : next);
      })
      .catch((error) => {
        if (!cancelled) toast.error(error instanceof ApiError ? error.message : "Could not open article");
      })
      .finally(() => {
        if (!cancelled) setLoadingArticle(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const groupedFeeds = useMemo(() => {
    const groups = categories.map((category) => ({
      category,
      feeds: feeds.filter((feed) => feed.category_id === category.id),
    }));
    const uncategorized = feeds.filter((feed) => !feed.category_id);
    return { groups, uncategorized };
  }, [categories, feeds]);

  const visibleIds = items.map((item) => item.id);
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.includes(id));
  const someVisibleSelected = visibleIds.some((id) => selectedIds.includes(id));

  async function onRefresh() {
    setRefreshing(true);
    try {
      const result = await api.refreshAll();
      toast.success(result.created ? `${result.created} new articles` : "Feeds are up to date");
      await Promise.all([loadNav(), loadList()]);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Refresh failed");
    } finally {
      setRefreshing(false);
    }
  }

  async function patchSelected(body: Partial<Pick<Article, "is_read" | "is_saved" | "is_starred">>) {
    if (!selectedId) return;
    const next = await api.patchArticle(selectedId, body);
    setArticle(next);
    setItems((current) => current.map((item) => (item.id === next.id ? { ...item, ...next } : item)));
    void loadNav();
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

  async function onRemoveFeed(feed: Feed, force: boolean) {
    await api.deleteFeed(feed.id, force);
    toast.success(feed.title ? `Removed ${feed.title}` : "Feed removed");
    setFeedToRemove(null);
    if (article?.feed_id === feed.id) {
      setSelectedId(null);
      setArticle(null);
    }
    if (shelf.kind === "feed" && shelf.id === feed.id) {
      setShelf({ kind: "unread" });
      await loadNav();
      return;
    }
    await Promise.all([loadNav(), loadList()]);
  }

  const nav = (
    <Sidebar
      user={user}
      stats={stats}
      shelf={shelf}
      feeds={feeds}
      groupedFeeds={groupedFeeds}
      tags={tags}
      onShelf={(next) => {
        setShelf(next);
        setSelectedId(null);
        setMobileNav(false);
      }}
      onAdd={() => setAddOpen(true)}
      onManageTags={() => setTagsOpen(true)}
      onRemoveFeed={(feed) => {
        setFeedToRemove(feed);
        setMobileNav(false);
      }}
      onMarkFeedRead={(feed) => void onMarkFeedRead(feed)}
      onBackup={() => setBackupOpen(true)}
      onRefresh={() => void onRefresh()}
      refreshing={refreshing}
      onLogout={async () => {
        await api.logout();
        router.replace("/login");
      }}
    />
  );

  return (
    <div className="flex h-full min-h-0 overflow-hidden bg-background">
      <aside className={cn("hidden h-full min-h-0 w-72 shrink-0 flex-col overflow-hidden bg-sidebar text-sidebar-foreground md:flex", readerFull && "!hidden")}>{nav}</aside>
      <Sheet open={mobileNav} onOpenChange={setMobileNav}>
        <SheetContent side="left" className="w-80 overflow-hidden bg-sidebar p-0 text-sidebar-foreground">
          <SheetHeader className="sr-only">
            <SheetTitle>Library</SheetTitle>
          </SheetHeader>
          {nav}
        </SheetContent>
      </Sheet>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex min-h-14 shrink-0 flex-wrap items-center gap-2 border-b px-3 py-1.5">
          <Button variant="ghost" size="icon" className="md:hidden" onClick={() => setMobileNav(true)}>
            <Menu className="size-4" />
          </Button>
          <form
            className="min-w-40 flex-1 max-w-xl"
            onSubmit={(event) => {
              event.preventDefault();
              if (query.trim()) {
                setShelf({ kind: "search", q: query.trim() });
                setSelectedId(null);
              }
            }}
          >
            <div className="relative">
              <Search className="size-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input
                ref={searchRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search the archive…  (/)"
                className="pl-8 bg-card"
              />
            </div>
          </form>
          <div className="ml-auto flex flex-wrap items-center gap-1">
            <Button
              size="xs"
              variant="outline"
              disabled={!items.length}
              title="Previous article in this shelf"
              onClick={() => selectRelative(-1)}
            >
              <ChevronUp className="size-3" />
              Prev
              <kbd className="text-[10px] text-muted-foreground">k</kbd>
            </Button>
            <Button
              size="xs"
              variant="outline"
              disabled={!items.length}
              title="Next article in this shelf"
              onClick={() => selectRelative(1)}
            >
              <ChevronDown className="size-3" />
              Next
              <kbd className="text-[10px] text-muted-foreground">j</kbd>
            </Button>
            <Button
              size="xs"
              variant={article?.is_read ? "default" : "outline"}
              disabled={!article}
              title="Mark this article read or unread"
              onClick={() => void patchSelected({ is_read: !article!.is_read })}
            >
              <Check className="size-3" />
              {article?.is_read ? "Unread" : "Read"}
              <kbd className="text-[10px] opacity-70">m</kbd>
            </Button>
            <Button
              size="xs"
              variant={article?.is_saved ? "default" : "outline"}
              disabled={!article}
              title="Save this article in the archive"
              onClick={() => void patchSelected({ is_saved: !article!.is_saved })}
            >
              {article?.is_saved ? <BookmarkCheck className="size-3" /> : <Bookmark className="size-3" />}
              Save
              <kbd className="text-[10px] opacity-70">s</kbd>
            </Button>
            <Button
              size="xs"
              variant="outline"
              disabled={!article}
              title="Jump to notes on this article"
              onClick={() => noteFocusRef.current?.()}
            >
              <NotebookPen className="size-3" />
              Note
              <kbd className="text-[10px] text-muted-foreground">n</kbd>
            </Button>
            <Button
              size="xs"
              variant="outline"
              disabled={!article}
              title="Listen to this article from the beginning"
              onClick={() => listenRef.current?.togglePlay()}
            >
              <Volume2 className="size-3" />
              Listen
              <kbd className="text-[10px] text-muted-foreground">l</kbd>
            </Button>
            <Button
              size="xs"
              variant="outline"
              disabled={!article}
              title="Listen from the selected word"
              onClick={() => listenRef.current?.listenFromHere()}
            >
              From here
              <kbd className="text-[10px] text-muted-foreground">⇧L</kbd>
            </Button>
            <Button
              size="xs"
              variant={readerFull ? "default" : "outline"}
              disabled={!article}
              title="Read this article full screen with every option still available"
              onClick={() => setReaderFull((current) => !current)}
            >
              {readerFull ? <Minimize2 className="size-3" /> : <Maximize2 className="size-3" />}
              {readerFull ? "Exit" : "Full screen"}
              <kbd className="text-[10px] text-muted-foreground">f</kbd>
            </Button>
          </div>
        </header>

        <div className={cn("grid min-h-0 flex-1 grid-cols-1 grid-rows-1 overflow-hidden [grid-template-rows:minmax(0,1fr)] lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]", readerFull && "lg:grid-cols-1")}>
          <section className={cn("flex min-h-0 flex-col overflow-hidden border-r", selectedId && "hidden lg:flex", readerFull && "!hidden")}>
            <div className="shrink-0 px-4 py-3 space-y-3">
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <h1 className="font-[family-name:var(--font-serif)] text-xl">{shelfTitle(shelf, feeds, categories, tags)}</h1>
                  <p className="text-xs text-muted-foreground">
                    {items.length > 0 && items.length < total
                      ? `${items.length} of ${total} ${shelf.kind === "notes" ? "notes" : "articles"}`
                      : `${total} ${shelf.kind === "notes" ? "notes" : "articles"}`}
                  </p>
                </div>
                {shelf.kind === "feed" ? (
                  <div className="flex shrink-0 gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        const feed = feeds.find((item) => item.id === shelf.id);
                        if (feed) void onMarkFeedRead(feed);
                      }}
                    >
                      <CheckCheck className="size-3.5" />
                      Mark read
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        const feed = feeds.find((item) => item.id === shelf.id);
                        if (feed) setFeedToRemove(feed);
                      }}
                    >
                      <Trash2 className="size-3.5" />
                      Remove
                    </Button>
                  </div>
                ) : null}
              </div>
              {shelf.kind !== "notes" && items.length > 0 ? (
                <div className="flex flex-wrap items-center gap-2">
                  <label className="flex items-center gap-2 text-xs text-muted-foreground">
                    <button
                      type="button"
                      className={cn(
                        "flex size-5 items-center justify-center rounded-[5px] border border-foreground/40 bg-background",
                        allVisibleSelected && "border-primary bg-primary text-primary-foreground",
                      )}
                      aria-pressed={allVisibleSelected}
                      aria-label="Select all articles"
                      onClick={() => setSelectedIds(allVisibleSelected ? [] : visibleIds)}
                    >
                      {allVisibleSelected ? <Check className="size-3.5" /> : someVisibleSelected ? <span className="block h-0.5 w-2.5 bg-foreground/70" /> : null}
                    </button>
                    Select all
                  </label>
                  {someVisibleSelected ? (
                    <>
                      <span className="text-xs text-muted-foreground">{selectedIds.filter((id) => visibleIds.includes(id)).length} selected</span>
                      <Button size="xs" variant="outline" onClick={() => void onBulk({ is_read: true })}>
                        Mark read
                      </Button>
                      <Button size="xs" variant="outline" onClick={() => void onBulk({ is_read: false })}>
                        Mark unread
                      </Button>
                      <Button size="xs" variant="outline" onClick={() => void onBulk({ is_saved: true })}>
                        Save
                      </Button>
                    </>
                  ) : null}
                </div>
              ) : null}
            </div>
            <ShelfScroller
              shelfKey={shelfKey(shelf)}
              hasMore={!loadingList && items.length > 0 && items.length < total}
              loadingMore={loadingMore}
              loaded={items.length}
              total={total}
              onNearEnd={() => void loadMore()}
            >
              {loadingList ? (
                <EmptyState icon={<LoaderCircle className="size-5 animate-spin" />} title="Opening the shelf" body="Fetching the latest from your archive." />
              ) : listError ? (
                <EmptyState title="Could not load this shelf" body={listError} />
              ) : items.length === 0 ? (
                <EmptyState
                  title={
                    shelf.kind === "saved"
                      ? "Nothing kept yet"
                      : shelf.kind === "vault"
                        ? "Vault is empty"
                        : shelf.kind === "additions"
                          ? "No StoryKeep additions yet"
                          : shelf.kind === "books"
                            ? "No books imported yet"
                            : shelf.kind === "notes"
                              ? "No notes filed here yet"
                              : shelf.kind === "schoolwork"
                                ? "No schoolwork yet"
                                : "This shelf is empty"
                  }
                  body={
                    shelf.kind === "inbox" || shelf.kind === "unread"
                      ? "Add a feed to start collecting stories you want to keep."
                      : shelf.kind === "vault"
                        ? "Collect → Vault and zip Steve's Surface Vault, or file a StoryKeep note to Vault. Originals stay in Obsidian."
                        : shelf.kind === "additions"
                          ? "File a note to Additions from Collect → Vault or from an article's Notes section."
                          : shelf.kind === "books"
                            ? "Import _book_ notes from the vault, or file a StoryKeep note to Books."
                            : shelf.kind === "notes"
                              ? "Open an article and save a note with destination Notes."
                              : shelf.kind === "schoolwork"
                                ? "File a StoryKeep note to Schoolwork from Collect or from an article."
                                : "Try another shelf, or search the full text of saved articles."
                  }
                />
              ) : (
                items.map((item) => (
                  <ArticleRow
                    key={item.id}
                    item={item}
                    active={item.id === selectedId}
                    selected={selectedIds.includes(item.id)}
                    onToggleSelect={() => {
                      setSelectedIds((current) =>
                        current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id],
                      );
                    }}
                    onClick={() => openArticle(item.id)}
                  />
                ))
              )}
            </ShelfScroller>
          </section>

          <section className={cn("flex min-h-0 flex-col overflow-hidden bg-card", !selectedId && "hidden lg:flex", readerFull && "flex")}>
            {loadingArticle ? (
              <EmptyState icon={<LoaderCircle className="size-5 animate-spin" />} title="Opening article" body="Loading the stored text, not just the link." />
            ) : article ? (
              <Reader
                article={article}
                tags={tags}
                listenRef={listenRef}
                noteFocusRef={noteFocusRef}
                caretWordRef={caretWordRef}
                readerFull={readerFull}
                onToggleFull={() => setReaderFull((current) => !current)}
                onBack={() => {
                  setReaderFull(false);
                  setSelectedId(null);
                }}
                onToggleRead={() => void patchSelected({ is_read: !article.is_read })}
                onToggleSaved={() => void patchSelected({ is_saved: !article.is_saved })}
                onToggleStar={() => void patchSelected({ is_starred: !article.is_starred })}
                onExtract={async () => {
                  const next = await api.extract(article.id);
                  setArticle(next);
                  toast.success("Full text refreshed");
                }}
                onArchive={async () => {
                  await api.archive(article.id);
                  const next = await api.article(article.id);
                  setArticle(next);
                  toast.success("Snapshot stored in the archive");
                  void loadNav();
                }}
                onTag={async (name) => {
                  await api.attachTag(article.id, name);
                  const next = await api.article(article.id);
                  setArticle(next);
                  void loadNav();
                }}
                onNote={async (title, markdown, destination, isCorrection) => {
                  await api.addAddition(article.id, title, markdown, destination, isCorrection);
                  const next = await api.article(article.id);
                  setArticle(next);
                  toast.success("Note saved on that shelf. The vault original was not touched.");
                  void Promise.all([loadNav(), loadList()]);
                }}
                onHighlight={async (payload) => {
                  await api.addNote(article.id, payload.note || payload.quote, {
                    kind: "highlight",
                    quote: payload.quote,
                    color: payload.color,
                    prefix: payload.prefix,
                    suffix: payload.suffix,
                  });
                  const next = await api.article(article.id);
                  setArticle(next);
                  setItems((current) => current.map((item) => (item.id === next.id ? { ...item, ...next } : item)));
                  toast.success("Highlight saved in the overlay pack");
                  void Promise.all([loadNav(), loadList()]);
                }}
                onMoveNote={async (noteId, destination, isCorrection) => {
                  const next = await api.setNoteDestination(noteId, destination, isCorrection);
                  if (noteId === article.id) {
                    setArticle(next);
                  } else {
                    const parent = await api.article(article.id);
                    setArticle(parent);
                  }
                  toast.success("Note moved. It is not duplicated.");
                  void Promise.all([loadNav(), loadList()]);
                }}
                onEditComposed={async (title, markdown, destination, isCorrection) => {
                  const next = await api.updateComposedNote(article.id, title, markdown, destination, isCorrection);
                  setArticle(next);
                  setItems((current) => current.map((item) => (item.id === next.id ? { ...item, ...next } : item)));
                  toast.success("StoryKeep note updated");
                  void Promise.all([loadNav(), loadList()]);
                }}
                onDownloadPack={async () => {
                  await api.downloadObsidianPack();
                  toast.success("Obsidian pack downloaded");
                }}
                onDeleteAnnotation={async (id) => {
                  await api.deleteNote(id);
                  const next = await api.article(article.id);
                  setArticle(next);
                  void Promise.all([loadNav(), loadList()]);
                }}
              />
            ) : (
              <EmptyState
                title="Choose a story"
                body="Unread items land here. Saved items are the ones you intend to keep for years."
              />
            )}
          </section>
        </div>
      </div>

      <AddFeedDialog
        open={addOpen}
        categories={categories}
        onOpenChange={setAddOpen}
        onAdded={async () => {
          await Promise.all([loadNav(), loadList()]);
        }}
        onSavedPage={async (articleId) => {
          openArticle(articleId);
          setShelf({ kind: "saved" });
          await Promise.all([loadNav(), loadList()]);
        }}
        onCreatedNote={async (articleId, destination) => {
          openArticle(articleId);
          setShelf({ kind: destination });
          setReaderFull(true);
          await loadNav();
        }}
        onImportedVault={async () => {
          setShelf({ kind: "vault" });
          await Promise.all([loadNav(), loadList()]);
        }}
      />
      <TagsDialog
        open={tagsOpen}
        tags={tags}
        onOpenChange={setTagsOpen}
        onChanged={async () => {
          await Promise.all([loadNav(), loadList()]);
        }}
      />
      <RemoveFeedDialog
        feed={feedToRemove}
        onOpenChange={(open) => {
          if (!open) setFeedToRemove(null);
        }}
        onConfirm={onRemoveFeed}
      />
      <BackupDialog
        open={backupOpen}
        backups={backups}
        onOpenChange={setBackupOpen}
        onCreated={async () => {
          setBackups(await api.backups());
        }}
      />
      <GrokBubble
        articleId={article?.id ?? null}
        articleTitle={article?.title ?? null}
        articleGuid={article?.guid ?? null}
        sourceRef={article?.source_ref ?? null}
        articleBody={article?.content_text ?? null}
        onSavedNote={async (noteId) => {
          await loadNav();
          if (noteId && noteId !== article?.id) {
            setShelf({ kind: "additions" });
            openArticle(noteId);
            return;
          }
          if (article?.id) {
            const next = await api.article(article.id);
            setArticle(next);
          }
        }}
      />
    </div>
  );
}

function Sidebar({
  user,
  stats,
  shelf,
  feeds,
  groupedFeeds,
  tags,
  onShelf,
  onAdd,
  onManageTags,
  onRemoveFeed,
  onMarkFeedRead,
  onBackup,
  onRefresh,
  refreshing,
  onLogout,
}: {
  user: User;
  stats: Stats | null;
  shelf: Shelf;
  feeds: Feed[];
  groupedFeeds: { groups: { category: Category; feeds: Feed[] }[]; uncategorized: Feed[] };
  tags: Tag[];
  onShelf: (shelf: Shelf) => void;
  onAdd: () => void;
  onManageTags: () => void;
  onRemoveFeed: (feed: Feed) => void;
  onMarkFeedRead: (feed: Feed) => void;
  onBackup: () => void;
  onRefresh: () => void;
  refreshing: boolean;
  onLogout: () => void;
}) {
  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden">
      <div className="shrink-0 px-4 pt-5 pb-3">
        <p className="font-[family-name:var(--font-serif)] text-2xl tracking-tight">Storykeep</p>
        <p className="text-xs text-sidebar-foreground/70 mt-1">{user.display_name || user.email}</p>
      </div>
      <div className="flex shrink-0 gap-2 px-3 pb-3">
        <Button size="sm" className="flex-1" onClick={onAdd}>
          <Plus className="size-3.5" />
          Add
        </Button>
        <Button size="sm" variant="secondary" onClick={onRefresh} disabled={refreshing}>
          <RefreshCw className={cn("size-3.5", refreshing && "animate-spin")} />
        </Button>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-2">
        <NavButton active={shelf.kind === "unread"} onClick={() => onShelf({ kind: "unread" })} icon={<Inbox className="size-4" />} count={stats?.unread_count}>
          Unread
        </NavButton>
        <NavButton active={shelf.kind === "inbox"} onClick={() => onShelf({ kind: "inbox" })} icon={<Archive className="size-4" />} count={stats?.article_count}>
          All
        </NavButton>
        <NavButton active={shelf.kind === "saved"} onClick={() => onShelf({ kind: "saved" })} icon={<Bookmark className="size-4" />} count={stats?.saved_count}>
          Saved
        </NavButton>
        <NavButton active={shelf.kind === "vault"} onClick={() => onShelf({ kind: "vault" })} icon={<Library className="size-4" />} count={stats?.vault_count}>
          Vault
        </NavButton>
        <NavButton active={shelf.kind === "additions"} onClick={() => onShelf({ kind: "additions" })} icon={<FilePlus className="size-4" />} count={stats?.additions_count}>
          Additions
        </NavButton>
        <NavButton active={shelf.kind === "books"} onClick={() => onShelf({ kind: "books" })} icon={<BookOpen className="size-4" />} count={stats?.books_count}>
          Books
        </NavButton>
        <NavButton active={shelf.kind === "notes"} onClick={() => onShelf({ kind: "notes" })} icon={<NotebookPen className="size-4" />} count={stats?.annotation_count}>
          Notes
        </NavButton>
        <NavButton active={shelf.kind === "schoolwork"} onClick={() => onShelf({ kind: "schoolwork" })} icon={<GraduationCap className="size-4" />} count={stats?.schoolwork_count}>
          Schoolwork
        </NavButton>
        <NavButton active={shelf.kind === "starred"} onClick={() => onShelf({ kind: "starred" })} icon={<Star className="size-4" />}>
          Starred
        </NavButton>
        <p className="px-2 pt-5 pb-1 text-[11px] uppercase tracking-[0.14em] text-sidebar-foreground/50">Feeds</p>
        {feeds.length === 0 ? (
          <p className="px-2 text-xs text-sidebar-foreground/60">No feeds yet. Add one to begin the archive.</p>
        ) : (
          <>
            {groupedFeeds.groups.map(({ category, feeds: group }) =>
              group.length ? (
                <div key={category.id} className="mb-2">
                  <button
                    type="button"
                    onClick={() => onShelf({ kind: "category", id: category.id })}
                    className={cn(
                      "w-full text-left px-2 py-1 text-[11px] uppercase tracking-[0.12em]",
                      shelf.kind === "category" && shelf.id === category.id
                        ? "text-sidebar-primary"
                        : "text-sidebar-foreground/50",
                    )}
                  >
                    {category.name}
                  </button>
                  {group.map((feed) => (
                    <FeedNavItem
                      key={feed.id}
                      feed={feed}
                      active={shelf.kind === "feed" && shelf.id === feed.id}
                      onSelect={() => onShelf({ kind: "feed", id: feed.id })}
                      onRemove={() => onRemoveFeed(feed)}
                      onMarkRead={() => onMarkFeedRead(feed)}
                    />
                  ))}
                </div>
              ) : null,
            )}
            {groupedFeeds.uncategorized.map((feed) => (
              <FeedNavItem
                key={feed.id}
                feed={feed}
                active={shelf.kind === "feed" && shelf.id === feed.id}
                onSelect={() => onShelf({ kind: "feed", id: feed.id })}
                onRemove={() => onRemoveFeed(feed)}
                onMarkRead={() => onMarkFeedRead(feed)}
              />
            ))}
          </>
        )}
        {tags.length > 0 ? (
          <>
            <button
              type="button"
              onClick={onManageTags}
              className="px-2 pt-5 pb-1 text-[11px] uppercase tracking-[0.14em] text-sidebar-foreground/50 hover:text-sidebar-foreground"
            >
              Tags · rename
            </button>
            {tags.map((tag) => (
              <NavButton
                key={tag.id}
                active={shelf.kind === "tag" && shelf.id === tag.id}
                onClick={() => onShelf({ kind: "tag", id: tag.id })}
                count={tag.article_count}
              >
                {tag.name}
              </NavButton>
            ))}
          </>
        ) : null}
      </div>
      <div className="shrink-0 space-y-1 border-t border-sidebar-border p-3">
        <Button variant="ghost" className="w-full justify-start text-sidebar-foreground" onClick={onBackup}>
          Backup & export
        </Button>
        <Button variant="ghost" className="w-full justify-start text-sidebar-foreground/70" onClick={onLogout}>
          Sign out
        </Button>
      </div>
    </div>
  );
}

function FeedNavItem({
  feed,
  active,
  onSelect,
  onRemove,
  onMarkRead,
}: {
  feed: Feed;
  active?: boolean;
  onSelect: () => void;
  onRemove: () => void;
  onMarkRead: () => void;
}) {
  const fetched = feed.last_fetched_at ? formatRelative(feed.last_fetched_at) : "never fetched";
  return (
    <div className="flex items-start gap-0.5">
      <div className="min-w-0 flex-1">
        <NavButton active={active} onClick={onSelect} count={feed.unread_count}>
          {feed.title || feed.url}
        </NavButton>
        <p className={cn("px-2 pb-1 text-[11px] leading-tight", feed.last_error ? "text-destructive/80" : "text-sidebar-foreground/55")}>
          {feed.last_error ? `Error · ${fetched}` : fetched}
        </p>
      </div>
      <Button
        type="button"
        size="icon-xs"
        variant="ghost"
        className="shrink-0 text-sidebar-foreground/45 hover:text-sidebar-foreground"
        aria-label={`Mark ${feed.title || "feed"} read`}
        disabled={!feed.unread_count}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          onMarkRead();
        }}
      >
        <CheckCheck className="size-3.5" />
      </Button>
      <Button
        type="button"
        size="icon-xs"
        variant="ghost"
        className="shrink-0 text-sidebar-foreground/45 hover:text-destructive"
        aria-label={`Remove ${feed.title || "feed"}`}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          onRemove();
        }}
      >
        <Trash2 className="size-3.5" />
      </Button>
    </div>
  );
}

function NavButton({
  children,
  onClick,
  active,
  icon,
  count,
}: {
  children: React.ReactNode;
  onClick: () => void;
  active?: boolean;
  icon?: React.ReactNode;
  count?: number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-left",
        active ? "bg-sidebar-accent text-sidebar-accent-foreground" : "hover:bg-sidebar-accent/60",
      )}
    >
      {icon}
      <span className="truncate flex-1">{children}</span>
      {count ? <span className="text-[11px] text-sidebar-foreground/55">{count}</span> : null}
    </button>
  );
}

function ArticleRow({
  item,
  active,
  selected,
  onToggleSelect,
  onClick,
}: {
  item: ArticleListItem;
  active: boolean;
  selected: boolean;
  onToggleSelect: () => void;
  onClick: () => void;
}) {
  return (
    <div
      className={cn(
        "flex items-start gap-2 border-b px-3 py-3 hover:bg-accent/40",
        active && "bg-accent/70",
        !item.is_read && "bg-primary/4",
      )}
    >
      <button
        type="button"
        className={cn(
          "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-[5px] border border-foreground/40 bg-background",
          selected && "border-primary bg-primary text-primary-foreground",
        )}
        aria-pressed={selected}
        aria-label={`Select ${item.title}`}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          onToggleSelect();
        }}
      >
        {selected ? <Check className="size-3.5" /> : null}
      </button>
      <button type="button" onClick={onClick} className="min-w-0 flex-1 text-left">
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-muted-foreground">
          {!item.is_read ? (
            <span className="size-1.5 shrink-0 rounded-full bg-primary" aria-hidden />
          ) : (
            <span className="size-1.5 shrink-0" aria-hidden />
          )}
          <span className="truncate">{item.feed_title || "Feed"}</span>
          <span>·</span>
          <span>{formatRelative(item.published_at)}</span>
          {item.is_saved ? <Bookmark className="size-3 ml-auto text-primary" /> : null}
        </div>
        <p className={cn("mt-1 leading-snug", item.is_read ? "font-medium text-foreground" : "font-semibold text-foreground")}>{item.title}</p>
        <p className="mt-1 text-sm text-muted-foreground line-clamp-2">{stripHtml(item.summary)}</p>
      </button>
    </div>
  );
}

function SpokenWords({ text, offset }: { text: string; offset: number }) {
  const parts = text.split(/(\s+)/);
  let index = offset;
  return (
    <>
      {parts.map((part, key) => {
        if (!part) return null;
        if (/^\s+$/.test(part)) return <span key={key}>{part}</span>;
        const wordIndex = index;
        index += 1;
        return (
          <span key={key} className="tts-word" data-tts-word={wordIndex}>
            {part}
          </span>
        );
      })}
    </>
  );
}

function Reader({
  article,
  tags,
  listenRef,
  noteFocusRef,
  caretWordRef,
  readerFull,
  onToggleFull,
  onBack,
  onToggleRead,
  onToggleSaved,
  onToggleStar,
  onExtract,
  onArchive,
  onTag,
  onNote,
  onHighlight,
  onDeleteAnnotation,
  onMoveNote,
  onEditComposed,
  onDownloadPack,
}: {
  article: Article;
  tags: Tag[];
  listenRef: React.RefObject<ListenControlsHandle | null>;
  noteFocusRef: React.MutableRefObject<(() => void) | null>;
  caretWordRef: React.MutableRefObject<(() => number | null) | null>;
  readerFull: boolean;
  onToggleFull: () => void;
  onBack: () => void;
  onToggleRead: () => void;
  onToggleSaved: () => void;
  onToggleStar: () => void;
  onExtract: () => Promise<void>;
  onArchive: () => Promise<void>;
  onTag: (name: string) => Promise<void>;
  onNote: (title: string, markdown: string, destination: NoteDestination, isCorrection: boolean) => Promise<void>;
  onHighlight: (payload: { quote: string; color: string; prefix: string; suffix: string; note?: string }) => Promise<void>;
  onDeleteAnnotation: (id: string) => Promise<void>;
  onMoveNote: (noteId: string, destination: NoteDestination, isCorrection: boolean) => Promise<void>;
  onEditComposed: (title: string, markdown: string, destination: NoteDestination, isCorrection: boolean) => Promise<void>;
  onDownloadPack: () => Promise<void>;
}) {
  const [note, setNote] = useState("");
  const [noteTitle, setNoteTitle] = useState("");
  const [noteDest, setNoteDest] = useState<NoteDestination>("notes");
  const [noteCorrection, setNoteCorrection] = useState(false);
  const [editTitle, setEditTitle] = useState(article.title);
  const [editBody, setEditBody] = useState(article.content_text || "");
  const [editDest, setEditDest] = useState<NoteDestination>(asDestination(article.destination, "additions"));
  const [editCorrection, setEditCorrection] = useState(Boolean(article.is_correction));
  const [highlightNote, setHighlightNote] = useState("");
  const [tag, setTag] = useState("");
  const [busy, setBusy] = useState(false);
  const [activeWord, setActiveWord] = useState<number | null>(null);
  const articleRef = useRef<HTMLElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const noteRef = useRef<HTMLTextAreaElement>(null);
  const clickedWordRef = useRef<number | null>(null);
  const [picker, setPicker] = useState<{ quote: string; prefix: string; suffix: string; top: number; left: number } | null>(
    null,
  );
  const bodyRef = useRef<HTMLDivElement>(null);
  const composed = isStoryKeepNote(article);
  const html = composed ? composedNoteHtml(article) : article.content_html ? sanitizeHtml(article.content_html) : "";
  const titleSpoken = spokenTitle(article.title);
  const titleWordCount = countWords(titleSpoken);
  const fallbackBody = composed
    ? composedNoteMarkdown(article)
    : article.content_text || stripHtml(article.summary) || "";
  const [bodyHtml, setBodyHtml] = useState(html || "");
  const [articleTextSize, setArticleTextSize] = useState<ArticleTextSize>("md");
  const suggestions = tags
    .filter((item) => !article.tags.some((attached) => attached.id === item.id))
    .filter((item) => !tag.trim() || item.name.toLowerCase().includes(tag.trim().toLowerCase()))
    .slice(0, 8);
  const highlightKey = article.annotations
    .filter((item) => item.kind === "highlight")
    .map((item) => `${item.id}:${item.color}:${item.quote}`)
    .join("|");
  const highlights = article.annotations.filter((item) => item.kind === "highlight" && item.quote);
  const filedNotes = article.filed_notes || [];

  useEffect(() => {
    const marks = article.annotations
      .filter((item) => item.kind === "highlight" && item.quote)
      .map((item) => ({
        id: item.id,
        quote: item.quote || "",
        color: item.color || "yellow",
        prefix: item.prefix,
        suffix: item.suffix,
      }));
    if (html) {
      setBodyHtml(applyHighlights(wrapHtmlWords(html, titleWordCount), marks));
      return;
    }
    if (fallbackBody) {
      const rendered = composed
        ? sanitizeHtml(noteMarkdownHtml(fallbackBody))
        : wrapPlainWords(fallbackBody, titleWordCount);
      setBodyHtml(applyHighlights(wrapHtmlWords(rendered, titleWordCount), marks));
      return;
    }
    setBodyHtml("");
  }, [article.id, composed, fallbackBody, html, highlightKey, titleWordCount]);

  useEffect(() => {
    setActiveWord(null);
    clickedWordRef.current = null;
    setNote("");
    setNoteTitle("");
    setNoteDest("notes");
    setNoteCorrection(false);
    setTag("");
    setEditTitle(article.title);
    setEditBody(composedNoteMarkdown(article) || article.content_text || "");
    setEditDest(asDestination(article.destination, "additions"));
    setEditCorrection(Boolean(article.is_correction));
    setHighlightNote("");
  }, [article.id, article.content_text, article.destination, article.is_correction, article.title]);

  useEffect(() => {
    noteFocusRef.current = () => noteRef.current?.focus();
    caretWordRef.current = () => wordIndexFromSelection(articleRef.current) ?? clickedWordRef.current;
    return () => {
      noteFocusRef.current = null;
      caretWordRef.current = null;
    };
  }, [caretWordRef, noteFocusRef]);

  useEffect(() => {
    setArticleTextSize(readArticleTextSize());
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const key = `storykeep-scroll:${article.id}`;
    const saved = Number(window.localStorage.getItem(key) || 0);
    const frame = window.requestAnimationFrame(() => {
      el.scrollTop = Number.isFinite(saved) ? saved : 0;
    });
    const onScroll = () => {
      window.localStorage.setItem(key, String(el.scrollTop));
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.cancelAnimationFrame(frame);
      el.removeEventListener("scroll", onScroll);
      window.localStorage.setItem(key, String(el.scrollTop));
    };
  }, [article.id]);

  useEffect(() => {
    const root = articleRef.current;
    if (!root) return;
    root.querySelectorAll(".tts-word-active").forEach((node) => node.classList.remove("tts-word-active"));
    if (activeWord == null) return;
    const current = root.querySelector(`[data-tts-word="${activeWord}"]`);
    if (!(current instanceof HTMLElement)) return;
    current.classList.add("tts-word-active");
    const holder = current.closest(".overflow-y-auto");
    if (holder instanceof HTMLElement) {
      const wordBox = current.getBoundingClientRect();
      const holdBox = holder.getBoundingClientRect();
      if (wordBox.top < holdBox.top + 72 || wordBox.bottom > holdBox.bottom - 72) {
        current.scrollIntoView({ block: "center", behavior: "auto" });
      }
    }
  }, [activeWord]);

  return (
    <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
      <article
        ref={articleRef}
        className={cn("mx-auto px-5 py-6", readerFull ? "max-w-4xl" : "max-w-3xl")}
        onClick={(event) => {
          const word = (event.target as HTMLElement).closest("[data-tts-word]");
          if (word instanceof HTMLElement) {
            const index = Number(word.dataset.ttsWord);
            if (Number.isFinite(index)) {
              clickedWordRef.current = index;
              setActiveWord(index);
            }
          }
        }}
      >
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <Button variant="ghost" className="lg:hidden -ml-2" onClick={onBack}>
            Back to list
          </Button>
          {readerFull ? (
            <Button variant="outline" size="sm" className="hidden lg:inline-flex" onClick={onToggleFull}>
              <Minimize2 className="size-3.5" />
              Exit full screen
            </Button>
          ) : (
            <Button variant="outline" size="sm" className="hidden lg:inline-flex" onClick={onToggleFull}>
              <Maximize2 className="size-3.5" />
              Full screen
            </Button>
          )}
        </div>
        <p className="text-xs uppercase tracking-[0.14em] text-muted-foreground">
          {article.source_kind === "obsidian" || article.source_kind === "textbook"
            ? "Vault"
            : article.source_kind === "file"
              ? "File"
              : article.feed_title}{" "}
          · {formatRelative(article.published_at)}
          {article.source_ref ? ` · ${article.source_ref}` : ""}
        </p>
        <h1 className="font-[family-name:var(--font-serif)] text-3xl md:text-4xl leading-tight mt-2">
          <SpokenWords text={titleSpoken || article.title} offset={0} />
        </h1>
        {article.author ? <p className="mt-2 text-sm text-muted-foreground">{article.author}</p> : null}
        <div className="flex flex-wrap gap-2 mt-4">
          <Button size="sm" variant={article.is_saved ? "default" : "outline"} onClick={onToggleSaved}>
            {article.is_saved ? <BookmarkCheck className="size-3.5" /> : <Bookmark className="size-3.5" />}
            {article.is_saved ? "Saved" : "Save"}
          </Button>
          <Button size="sm" variant="outline" onClick={onToggleStar}>
            {article.is_starred ? <Star className="size-3.5 fill-current" /> : <StarOff className="size-3.5" />}
            Star
          </Button>
          <Button size="sm" variant="outline" onClick={onToggleRead}>
            {article.is_read ? "Mark unread" : "Mark read"}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => {
              setBusy(true);
              void onExtract().finally(() => setBusy(false));
            }}
          >
            Re-extract
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => {
              setBusy(true);
              void onArchive().finally(() => setBusy(false));
            }}
          >
            Snapshot
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => void onDownloadPack()}
          >
            Download Obsidian pack
          </Button>
          {article.source_kind === "file" ? (
            <a
              href={`/api/v1/articles/${article.id}/file`}
              className="inline-flex h-7 items-center rounded-md border px-2.5 text-[0.8rem] hover:bg-muted"
            >
              Download original
            </a>
          ) : null}
          <a
            href={article.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-7 items-center rounded-md px-2.5 text-[0.8rem] hover:bg-muted"
          >
            Original
          </a>
        </div>
        <div className="mt-3">
          <ListenControls
            ref={listenRef}
            articleId={article.id}
            hasText={Boolean(article.content_text || article.content_html || article.summary)}
            onCue={setActiveWord}
            getCaretWord={() => wordIndexFromSelection(articleRef.current) ?? clickedWordRef.current}
          />
        </div>
        {article.tags.length > 0 ? (
          <div className="flex flex-wrap gap-1.5 mt-4">
            {article.tags.map((item) => (
              <Badge key={item.id} variant="secondary">
                {item.name}
              </Badge>
            ))}
          </div>
        ) : null}
        <Separator className="my-6" />
        <div className="mb-4 flex justify-end">
          <label className="inline-flex items-center gap-2 text-[0.8rem] text-muted-foreground">
            <span>Text size</span>
            <select
              aria-label="Article text size"
              value={articleTextSize}
              onChange={(event) => {
                const next = event.target.value as ArticleTextSize;
                setArticleTextSize(next);
                writeArticleTextSize(next);
              }}
              className="h-7 rounded-md border border-input bg-background px-2 text-[0.8rem] text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              {ARTICLE_TEXT_SIZE_OPTIONS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        {bodyHtml ? (
          <div
            ref={bodyRef}
            className={cn("article-body", composed && "note-md", articleTextSizeClass(articleTextSize))}
            dangerouslySetInnerHTML={{ __html: bodyHtml }}
            onMouseUp={() => {
              const next = selectionInRoot(bodyRef.current);
              setPicker(next);
            }}
          />
        ) : (
          <EmptyState
            title="Only the feed snippet is stored"
            body="The original page has not been extracted yet. Use Re-extract to pull the full article, or Snapshot to keep a copy."
          />
        )}
        <Separator className="my-8" />
        <section className="space-y-4 pb-10">
          <h2 className="font-[family-name:var(--font-serif)] text-xl">Notes</h2>
          <form
            className="flex gap-2 relative"
            onSubmit={(event) => {
              event.preventDefault();
              if (!tag.trim()) return;
              void onTag(tag.trim()).then(() => setTag(""));
            }}
          >
            <Input
              value={tag}
              onChange={(event) => setTag(event.target.value)}
              placeholder="Add a tag, e.g. fusion"
              autoComplete="off"
            />
            <Button type="submit" variant="secondary">
              Tag
            </Button>
            {tag.trim() && suggestions.length > 0 ? (
              <ul className="absolute left-0 right-20 top-9 z-10 rounded-md border bg-popover shadow-md">
                {suggestions.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className="w-full px-3 py-1.5 text-left text-sm hover:bg-accent"
                      onClick={() => {
                        void onTag(item.name).then(() => setTag(""));
                      }}
                    >
                      {item.name}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </form>
          {isStoryKeepNote(article) ? null : (
          <form
            className="space-y-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (!note.trim()) return;
              const title = noteTitle.trim() || note.trim().split("\n")[0]?.slice(0, 80) || "Note";
              void onNote(title, note.trim(), noteDest, noteCorrection).then(() => {
                setNote("");
                setNoteTitle("");
                setNoteCorrection(false);
              });
            }}
          >
            <Label>Notes</Label>
            <p className="text-xs text-muted-foreground">
              One workspace. Destination files the note to that sidebar shelf. Vault here is a StoryKeep shelf, not a write into Steve&apos;s Surface Vault.
            </p>
            <NoteComposer
              textareaRef={noteRef}
              value={note}
              onChange={setNote}
              placeholder="Markdown note…"
              rows={4}
              header={
                <Input value={noteTitle} onChange={(event) => setNoteTitle(event.target.value)} placeholder="Title (optional)" />
              }
              toolbarExtra={
                <>
                  <DestinationSelect value={noteDest} onChange={setNoteDest} />
                  <CorrectionCheck checked={noteCorrection} onChange={setNoteCorrection} />
                </>
              }
              actions={<Button type="submit">Save note</Button>}
            />
          </form>
          )}
          <p className="text-xs text-muted-foreground">
            Select a passage, pick a color, optionally add a comment. Highlights land in StoryKeep/Highlights of the pack. They never rewrite the original vault file.
          </p>
          {highlights.length > 0 ? (
            <ul className="flex flex-wrap gap-2">
              {highlights.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={cn("max-w-xs truncate rounded-md px-2 py-1 text-left text-xs", `hl hl-${item.color || "yellow"}`)}
                    title="Remove highlight"
                    onClick={() => void onDeleteAnnotation(item.id)}
                  >
                    {item.quote}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          {isStoryKeepNote(article) ? (
            <form
              className="space-y-2 rounded-md border p-3"
              onSubmit={(event) => {
                event.preventDefault();
                if (!editTitle.trim() || !editBody.trim()) return;
                void onEditComposed(editTitle.trim(), editBody.trim(), editDest, editCorrection);
              }}
            >
              <NoteComposer
                value={editBody}
                onChange={setEditBody}
                placeholder="Full note, with ==highlights== and images…"
                rows={10}
                header={
                  <>
                    <Label>This StoryKeep note</Label>
                    <p className="text-xs text-muted-foreground">
                      Changing destination moves this note to that shelf. Imported vault files stay read-only.
                    </p>
                    <Input value={editTitle} onChange={(event) => setEditTitle(event.target.value)} placeholder="Title" />
                  </>
                }
                toolbarExtra={
                  <>
                    <DestinationSelect
                      value={editDest}
                      onChange={(next) => {
                        setEditDest(next);
                        void onMoveNote(article.id, next, editCorrection);
                      }}
                    />
                    <CorrectionCheck
                      checked={editCorrection}
                      onChange={(next) => {
                        setEditCorrection(next);
                        void onMoveNote(article.id, editDest, next);
                      }}
                    />
                  </>
                }
                actions={
                  <Button type="submit" variant="secondary">
                    Update note
                  </Button>
                }
              />
            </form>
          ) : null}
          {filedNotes.length === 0 ? (
            isStoryKeepNote(article) ? null : (
              <p className="text-sm text-muted-foreground">No filed notes on this story yet.</p>
            )
          ) : (
            <ul className="space-y-3">
              {filedNotes.map((item) => (
                <li key={item.id} className="rounded-lg border bg-background px-3 py-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium min-w-0 flex-1">{item.title}</p>
                    <DestinationSelect
                      value={asDestination(item.destination, "notes")}
                      onChange={(next) => void onMoveNote(item.id, next, Boolean(item.is_correction))}
                    />
                    <CorrectionCheck
                      checked={Boolean(item.is_correction)}
                      onChange={(next) => void onMoveNote(item.id, asDestination(item.destination, "notes"), next)}
                    />
                  </div>
                  <div
                    className="text-sm mt-1 note-md"
                    dangerouslySetInnerHTML={{ __html: sanitizeHtml(noteMarkdownHtml(item.markdown)) }}
                  />
                  <p className="text-[11px] text-muted-foreground mt-1">{formatRelative(item.updated_at || item.created_at)}</p>
                </li>
              ))}
            </ul>
          )}
          {article.archives.length > 0 ? (
            <p className="text-xs text-muted-foreground">
              {article.archives.length} snapshot{article.archives.length === 1 ? "" : "s"} stored if the original link dies.
            </p>
          ) : null}
        </section>
      </article>
      {picker ? (
        <div
          className="fixed z-50 flex w-72 -translate-x-1/2 -translate-y-full flex-col gap-2 rounded-lg border bg-background p-2 shadow-md"
          style={{ top: Math.max(48, picker.top - 8), left: picker.left }}
        >
          <div className="flex justify-center gap-1">
            {HIGHLIGHT_COLORS.map((color) => (
              <button
                key={color}
                type="button"
                className={cn("size-7 rounded-full border border-black/10", `hl-${color}`)}
                title={`Highlight ${color}`}
                aria-label={`Highlight ${color}`}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => {
                  void onHighlight({
                    quote: picker.quote,
                    color,
                    prefix: picker.prefix,
                    suffix: picker.suffix,
                    note: highlightNote.trim() || undefined,
                  }).finally(() => {
                    setPicker(null);
                    setHighlightNote("");
                    window.getSelection()?.removeAllRanges();
                  });
                }}
              />
            ))}
          </div>
          <input
            className="h-7 rounded-md border bg-background px-2 text-xs"
            placeholder="Optional comment for Highlights/"
            value={highlightNote}
            onChange={(event) => setHighlightNote(event.target.value)}
            onMouseDown={(event) => event.stopPropagation()}
          />
        </div>
      ) : null}
    </div>
  );
}

function EmptyState({
  title,
  body,
  icon,
}: {
  title: string;
  body: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="h-full min-h-64 flex flex-col items-center justify-center text-center px-8 py-16">
      {icon}
      <p className="font-[family-name:var(--font-serif)] text-xl mt-3">{title}</p>
      <p className="text-sm text-muted-foreground mt-2 max-w-sm">{body}</p>
    </div>
  );
}

function RemoveFeedDialog({
  feed,
  onOpenChange,
  onConfirm,
}: {
  feed: Feed | null;
  onOpenChange: (open: boolean) => void;
  onConfirm: (feed: Feed, force: boolean) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [force, setForce] = useState(false);

  useEffect(() => {
    setForce(false);
  }, [feed?.id]);

  const saved = feed?.saved_count ?? 0;

  return (
    <Dialog open={Boolean(feed)} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Remove this feed?</DialogTitle>
          <DialogDescription>
            {feed
              ? `Storykeep will stop importing ${feed.title || feed.url}. Unread copies of its articles will be deleted.`
              : "Storykeep will stop importing this feed."}
          </DialogDescription>
        </DialogHeader>
        {saved > 0 ? (
          <p className="text-sm text-muted-foreground">
            This feed has {saved} saved {saved === 1 ? "article" : "articles"}. Removing it can delete those kept copies too.
          </p>
        ) : null}
        {force || saved > 0 ? (
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={force}
              onChange={(event) => setForce(event.target.checked)}
            />
            <span>Also delete saved articles from this feed</span>
          </label>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Keep feed
          </Button>
          <Button
            variant="destructive"
            disabled={busy || (saved > 0 && !force)}
            onClick={async () => {
              if (!feed) return;
              setBusy(true);
              try {
                await onConfirm(feed, force || saved > 0);
              } catch (error) {
                if (error instanceof ApiError && error.status === 409) {
                  setForce(true);
                  toast.error("This feed has saved articles. Confirm deletion of those copies to continue.");
                } else {
                  toast.error(error instanceof ApiError ? error.message : "Could not remove feed");
                }
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? "Removing…" : "Remove feed"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AddFeedDialog({
  open,
  onOpenChange,
  categories,
  onAdded,
  onSavedPage,
  onCreatedNote,
  onImportedVault,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  categories: Category[];
  onAdded: () => Promise<void>;
  onSavedPage: (articleId: string) => Promise<void>;
  onCreatedNote: (articleId: string, destination: NoteDestination) => Promise<void>;
  onImportedVault: () => Promise<void>;
}) {
  const [tab, setTab] = useState<"feed" | "page" | "opml" | "vault" | "file">("feed");
  const [url, setUrl] = useState("");
  const [pageUrl, setPageUrl] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [busy, setBusy] = useState(false);
  const [candidates, setCandidates] = useState<{ url: string; title: string | null }[]>([]);
  const [additionTitle, setAdditionTitle] = useState("");
  const [additionSubject, setAdditionSubject] = useState("");
  const [additionBody, setAdditionBody] = useState("");
  const [composeDest, setComposeDest] = useState<NoteDestination>("vault");
  const [composeCorrection, setComposeCorrection] = useState(false);
  const [composeFull, setComposeFull] = useState(false);
  const [fileTitle, setFileTitle] = useState("");
  const [fileTags, setFileTags] = useState("");
  const bookmarklet =
    typeof window === "undefined"
      ? ""
      : `javascript:void(location='${window.location.origin}/?save='+encodeURIComponent(location.href))`;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setComposeFull(false);
        onOpenChange(next);
      }}
    >
      <DialogContent
        className={cn(
          "max-h-[90vh]",
          tab === "vault" && !composeFull
            ? "!flex h-[min(90vh,52rem)] w-[min(96vw,72rem)] sm:max-w-6xl flex-col overflow-hidden"
            : tab !== "vault"
              ? "overflow-y-auto"
              : "",
          composeFull &&
            "!top-0 !left-0 !flex h-[100dvh] !max-h-none w-[100vw] !max-w-none sm:!max-w-none !translate-x-0 !translate-y-0 flex-col overflow-hidden rounded-none p-3",
        )}
      >
        {composeFull ? null : (
          <>
        <DialogHeader className="shrink-0">
          <DialogTitle>Collect</DialogTitle>
          <DialogDescription>
            Subscribe to a site, save a page, upload a file, import OPML, or add vault notes.
          </DialogDescription>
        </DialogHeader>
        <div className="flex shrink-0 flex-wrap gap-1 rounded-lg bg-muted p-1">
          {(
            [
              ["feed", "Feed"],
              ["page", "Save URL"],
              ["file", "File"],
              ["opml", "OPML"],
              ["vault", "Vault"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={cn(
                "flex-1 rounded-md px-2 py-1.5 text-sm",
                tab === id ? "bg-background shadow-sm" : "text-muted-foreground",
              )}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>
          </>
        )}
        {tab === "feed" ? (
          <form
            className="space-y-3"
            onSubmit={async (event) => {
              event.preventDefault();
              setBusy(true);
              try {
                await api.addFeed(url, categoryId || null);
                toast.success("Feed added. Articles are importing.");
                setUrl("");
                setCandidates([]);
                onOpenChange(false);
                await onAdded();
              } catch (error) {
                toast.error(error instanceof ApiError ? error.message : "Could not add feed");
              } finally {
                setBusy(false);
              }
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="feed-url">Site or feed URL</Label>
              <Input
                id="feed-url"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="https://example.com"
                required
              />
            </div>
            {categories.length > 0 ? (
              <div className="space-y-1.5">
                <Label htmlFor="feed-category">Category</Label>
                <select
                  id="feed-category"
                  className="w-full h-9 rounded-md border bg-background px-3 text-sm"
                  value={categoryId}
                  onChange={(event) => setCategoryId(event.target.value)}
                >
                  <option value="">Uncategorized</option>
                  {categories.map((category) => (
                    <option key={category.id} value={category.id}>
                      {category.name}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={busy || !url.trim()}
                onClick={async () => {
                  setBusy(true);
                  try {
                    const found = await api.discoverFeeds(url.trim());
                    setCandidates(found.candidates);
                    if (!found.candidates.length) toast.message("No feeds found on that page.");
                    else if (found.candidates[0]) setUrl(found.candidates[0].url);
                  } catch (error) {
                    toast.error(error instanceof ApiError ? error.message : "Could not discover feeds");
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Find feed
              </Button>
              <Button type="submit" disabled={busy}>
                {busy ? "Fetching…" : "Add feed"}
              </Button>
            </div>
            {candidates.length > 0 ? (
              <ul className="space-y-1 rounded-md border p-2">
                {candidates.map((item) => (
                  <li key={item.url}>
                    <button
                      type="button"
                      className="w-full rounded px-2 py-1 text-left text-sm hover:bg-accent"
                      onClick={() => setUrl(item.url)}
                    >
                      <span className="font-medium">{item.title || "Untitled feed"}</span>
                      <span className="block truncate text-xs text-muted-foreground">{item.url}</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </form>
        ) : null}
        {tab === "page" ? (
          <form
            className="space-y-3"
            onSubmit={async (event) => {
              event.preventDefault();
              setBusy(true);
              try {
                const article = await api.saveUrl(pageUrl.trim());
                toast.success("Page extracted and snapshotted");
                setPageUrl("");
                onOpenChange(false);
                await onSavedPage(article.id);
              } catch (error) {
                toast.error(error instanceof ApiError ? error.message : "Could not save that URL");
              } finally {
                setBusy(false);
              }
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="page-url">Page URL</Label>
              <Input
                id="page-url"
                value={pageUrl}
                onChange={(event) => setPageUrl(event.target.value)}
                placeholder="https://example.com/article"
                required
              />
            </div>
            <Button type="submit" disabled={busy}>
              {busy ? "Extracting…" : "Save URL"}
            </Button>
            <div className="space-y-1.5">
              <Label>Bookmarklet</Label>
              <p className="text-xs text-muted-foreground">
                Drag this to your bookmarks bar. On any page, click it to extract and snapshot into Storykeep.
              </p>
              <a
                className="inline-flex h-8 items-center rounded-md border px-3 text-sm"
                href={bookmarklet}
                onClick={(event) => event.preventDefault()}
              >
                Save to Storykeep
              </a>
            </div>
          </form>
        ) : null}
        {tab === "file" ? (
          <form
            className="space-y-3"
            onSubmit={async (event) => {
              event.preventDefault();
              const input = event.currentTarget.elements.namedItem("upload-file") as HTMLInputElement | null;
              const chosen = input?.files?.[0];
              if (!chosen) {
                toast.error("Choose a PDF, Word, PowerPoint, or text file.");
                return;
              }
              setBusy(true);
              try {
                const article = await api.uploadDocument(chosen, fileTitle, fileTags);
                toast.success("File extracted into the archive");
                setFileTitle("");
                setFileTags("");
                if (input) input.value = "";
                onOpenChange(false);
                await onSavedPage(article.id);
              } catch (error) {
                toast.error(error instanceof ApiError ? error.message : "Could not upload that file");
              } finally {
                setBusy(false);
              }
            }}
          >
            <p className="text-sm text-muted-foreground">
              Upload a PDF, Word (.docx), PowerPoint (.pptx), markdown, HTML, CSV, RTF, ODT, or EPUB. StoryKeep stores the
              extracted text so you can read, search, tag, listen, and highlight. The original file stays downloadable. This does
              not write into Steve&apos;s Surface Vault.
            </p>
            <div className="space-y-1.5">
              <Label htmlFor="upload-file">File</Label>
              <Input
                id="upload-file"
                name="upload-file"
                type="file"
                accept=".pdf,.docx,.pptx,.txt,.md,.markdown,.html,.htm,.csv,.rtf,.odt,.epub,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.presentationml.presentation,text/plain,text/markdown,text/html,text/csv"
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="file-title">Title (optional)</Label>
              <Input
                id="file-title"
                value={fileTitle}
                onChange={(event) => setFileTitle(event.target.value)}
                placeholder="Defaults to the filename"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="file-tags">Subjects / tags (optional)</Label>
              <Input
                id="file-tags"
                value={fileTags}
                onChange={(event) => setFileTags(event.target.value)}
                placeholder="e.g. DAT-200, syllabus"
              />
            </div>
            <Button type="submit" disabled={busy}>
              {busy ? "Extracting…" : "Upload file"}
            </Button>
          </form>
        ) : null}
        {tab === "vault" ? (
          <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden">
            {composeFull ? null : (
            <div className="shrink-0 space-y-2">
            <p className="text-sm text-muted-foreground">
              Zip Steve&apos;s Surface Vault and import it here. StoryKeep never writes back into that folder. Highlights,
              additions, and corrections download as a separate overlay pack you unzip at the vault root on Windows.
            </p>
            <label className="inline-flex h-8 cursor-pointer items-center rounded-md bg-primary px-3 text-sm text-primary-foreground">
              Import vault zip
              <input
                type="file"
                accept=".zip,application/zip"
                className="hidden"
                onChange={async (event) => {
                  const file = event.target.files?.[0];
                  event.target.value = "";
                  if (!file) return;
                  setBusy(true);
                  try {
                    const result = await api.importVault(file);
                    toast.success(
                      `Imported ${result.imported}, updated ${result.updated}, skipped ${result.skipped}${
                        result.attachments ? `, ${result.attachments} attachments ignored` : ""
                      }${result.errors.length ? `, ${result.errors.length} errors` : ""}`,
                    );
                    await onImportedVault();
                    onOpenChange(false);
                  } catch (error) {
                    toast.error(error instanceof ApiError ? error.message : "Vault import failed");
                  } finally {
                    setBusy(false);
                  }
                }}
              />
            </label>
            <p className="text-xs text-muted-foreground">
              Skips <code>.obsidian</code>, does not turn png/jpg into articles, and tags book / course / clipping / daily from
              the path. Merge Corrections by hand in Obsidian; do not let StoryKeep overwrite originals.
            </p>
            </div>
            )}
            <form
              className={cn(
                "flex min-h-0 flex-1 flex-col gap-2 overflow-hidden",
                composeFull ? "p-0" : "rounded-md border p-3",
              )}
              onSubmit={async (event) => {
                event.preventDefault();
                if (!additionTitle.trim() || !additionBody.trim()) return;
                setBusy(true);
                try {
                  const tags = additionSubject
                    .split(/[,#]/)
                    .map((part) => part.trim())
                    .filter(Boolean);
                  const article = await api.composeVaultNote(
                    additionTitle.trim(),
                    additionBody.trim(),
                    tags,
                    composeDest,
                    composeCorrection,
                  );
                  toast.success("Note saved on that StoryKeep shelf. Steve's Surface Vault was not overwritten.");
                  setAdditionTitle("");
                  setAdditionSubject("");
                  setAdditionBody("");
                  setComposeCorrection(false);
                  setComposeFull(false);
                  onOpenChange(false);
                  await onCreatedNote(article.id, composeDest);
                } catch (error) {
                  toast.error(error instanceof ApiError ? error.message : "Could not save the note");
                } finally {
                  setBusy(false);
                }
              }}
            >
              <NoteComposer
                value={additionBody}
                onChange={setAdditionBody}
                placeholder="Paste or write the full markdown: lecture notes, a paper, a chapter…"
                rows={12}
                required
                fill
                onExpandedChange={setComposeFull}
                header={
                  <>
                    <Label>Type a new article or paper</Label>
                    <p className="text-xs text-muted-foreground">
                      StoryKeep overlay note. Destination chooses the sidebar shelf. This never writes Steve&apos;s Surface Vault.
                      Pack path is StoryKeep/Additions unless you mark it a correction.
                    </p>
                    <Input
                      value={additionTitle}
                      onChange={(event) => setAdditionTitle(event.target.value)}
                      placeholder="Title"
                      required
                    />
                    <Input
                      value={additionSubject}
                      onChange={(event) => setAdditionSubject(event.target.value)}
                      placeholder="Subjects / tags, comma-separated (e.g. calculus, DAT-200)"
                    />
                  </>
                }
                toolbarExtra={
                  <>
                    <DestinationSelect value={composeDest} onChange={setComposeDest} />
                    <CorrectionCheck checked={composeCorrection} onChange={setComposeCorrection} />
                  </>
                }
                actions={
                  <Button type="submit" disabled={busy}>
                    {busy ? "Saving…" : "Save complete note"}
                  </Button>
                }
              />
            </form>
          </div>
        ) : null}
        {tab === "opml" ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Import subscriptions from another reader, or export the feeds you already keep here.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  void api.exportOpml().then(() => toast.success("OPML downloaded"));
                }}
              >
                Export OPML
              </Button>
              <label className="inline-flex h-8 cursor-pointer items-center rounded-md bg-primary px-3 text-sm text-primary-foreground">
                Import OPML
                <input
                  type="file"
                  accept=".opml,.xml,text/xml"
                  className="hidden"
                  onChange={async (event) => {
                    const file = event.target.files?.[0];
                    event.target.value = "";
                    if (!file) return;
                    setBusy(true);
                    try {
                      const result = await api.importOpml(file);
                      toast.success(
                        `Imported ${result.imported}, skipped ${result.skipped}${result.errors.length ? `, ${result.errors.length} errors` : ""}`,
                      );
                      await onAdded();
                    } catch (error) {
                      toast.error(error instanceof ApiError ? error.message : "OPML import failed");
                    } finally {
                      setBusy(false);
                    }
                  }}
                />
              </label>
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function TagsDialog({
  open,
  tags,
  onOpenChange,
  onChanged,
}: {
  open: boolean;
  tags: Tag[];
  onOpenChange: (open: boolean) => void;
  onChanged: () => Promise<void>;
}) {
  const [names, setNames] = useState<Record<string, string>>({});
  const [mergeInto, setMergeInto] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    const next: Record<string, string> = {};
    for (const tag of tags) next[tag.id] = tag.name;
    setNames(next);
  }, [tags, open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Rename or merge tags</DialogTitle>
          <DialogDescription>Merging moves every article onto the target tag, then deletes the source.</DialogDescription>
        </DialogHeader>
        {tags.length === 0 ? (
          <p className="text-sm text-muted-foreground">No tags yet. Add one from an article.</p>
        ) : (
          <ul className="space-y-3">
            {tags.map((tag) => (
              <li key={tag.id} className="space-y-2 rounded-md border p-3">
                <div className="flex gap-2">
                  <Input
                    value={names[tag.id] ?? tag.name}
                    onChange={(event) => setNames((current) => ({ ...current, [tag.id]: event.target.value }))}
                  />
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={busy === tag.id || !(names[tag.id] || "").trim()}
                    onClick={async () => {
                      setBusy(tag.id);
                      try {
                        await api.renameTag(tag.id, (names[tag.id] || "").trim());
                        toast.success("Tag renamed");
                        await onChanged();
                      } catch (error) {
                        toast.error(error instanceof ApiError ? error.message : "Could not rename tag");
                      } finally {
                        setBusy(null);
                      }
                    }}
                  >
                    Rename
                  </Button>
                </div>
                {tags.length > 1 ? (
                  <div className="flex gap-2">
                    <select
                      className="h-8 flex-1 rounded-md border bg-background px-2 text-sm"
                      value={mergeInto[tag.id] || ""}
                      onChange={(event) => setMergeInto((current) => ({ ...current, [tag.id]: event.target.value }))}
                    >
                      <option value="">Merge into…</option>
                      {tags
                        .filter((other) => other.id !== tag.id)
                        .map((other) => (
                          <option key={other.id} value={other.id}>
                            {other.name}
                          </option>
                        ))}
                    </select>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!mergeInto[tag.id] || busy === tag.id}
                      onClick={async () => {
                        const dest = mergeInto[tag.id];
                        if (!dest) return;
                        setBusy(tag.id);
                        try {
                          await api.mergeTag(tag.id, dest);
                          toast.success("Tags merged");
                          await onChanged();
                        } catch (error) {
                          toast.error(error instanceof ApiError ? error.message : "Could not merge tags");
                        } finally {
                          setBusy(null);
                        }
                      }}
                    >
                      Merge
                    </Button>
                  </div>
                ) : null}
                <p className="text-[11px] text-muted-foreground">{tag.article_count} articles</p>
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}

function BackupDialog({
  open,
  onOpenChange,
  backups,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  backups: Backup[];
  onCreated: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Backup the archive</DialogTitle>
          <DialogDescription>
            The Obsidian pack is the only thing that goes back to the vault: Highlights, Additions, Corrections, and Index.md.
            JSON export is a full archive dump. Database dumps use pg_dump.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await api.downloadObsidianPack();
                toast.success("Obsidian pack downloaded");
              } catch (error) {
                toast.error(error instanceof ApiError ? error.message : "Pack download failed");
              } finally {
                setBusy(false);
              }
            }}
          >
            Download Obsidian pack
          </Button>
          <Button
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await api.createBackup("export_json");
                toast.success("JSON export ready");
                await onCreated();
              } catch (error) {
                toast.error(error instanceof ApiError ? error.message : "Export failed");
              } finally {
                setBusy(false);
              }
            }}
          >
            Export JSON
          </Button>
          <Button
            variant="secondary"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                const row = await api.createBackup("db_dump");
                toast[row.status === "success" ? "success" : "error"](
                  row.status === "success" ? "Database dump saved" : row.error || "Dump failed",
                );
                await onCreated();
              } catch (error) {
                toast.error(error instanceof ApiError ? error.message : "Dump failed");
              } finally {
                setBusy(false);
              }
            }}
          >
            Dump database
          </Button>
        </div>
        {backups.length === 0 ? (
          <p className="text-sm text-muted-foreground">No backups yet. Create one before you trust this as a lifelong archive.</p>
        ) : (
          <ul className="max-h-56 overflow-auto space-y-2 text-sm">
            {backups.map((row) => (
              <li key={row.id} className="rounded-md border px-3 py-2">
                <div className="flex justify-between gap-2">
                  <span>
                    {row.backup_type} · {row.destination} · {row.status}
                  </span>
                  {row.status === "success" && row.location && !row.location.startsWith("s3://") ? (
                    <a className="text-primary underline" href={`/api/v1/backups/${row.id}/download`}>
                      Download
                    </a>
                  ) : null}
                </div>
                <p className="text-xs text-muted-foreground mt-1">{formatRelative(row.started_at)}</p>
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}
