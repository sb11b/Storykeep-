"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Archive,
  Bookmark,
  BookmarkCheck,
  Check,
  CheckCheck,
  Inbox,
  LoaderCircle,
  Menu,
  NotebookPen,
  Plus,
  RefreshCw,
  Search,
  Star,
  StarOff,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { ListenControls, type ListenControlsHandle } from "@/components/listen-controls";
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
import { renderMarkdown } from "@/lib/markdown";
import { countWords, spokenTitle, wordIndexFromCaret, wrapHtmlWords, wrapPlainWords } from "@/lib/tts-words";
import type {
  Annotation,
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

export function LibraryApp({ user }: { user: User }) {
  const router = useRouter();
  const [feeds, setFeeds] = useState<Feed[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [notes, setNotes] = useState<Annotation[]>([]);
  const [backups, setBackups] = useState<Backup[]>([]);
  const [items, setItems] = useState<ArticleListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [shelf, setShelf] = useState<Shelf>({ kind: "unread" });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [article, setArticle] = useState<Article | null>(null);
  const [query, setQuery] = useState("");
  const [loadingList, setLoadingList] = useState(true);
  const [loadingArticle, setLoadingArticle] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [backupOpen, setBackupOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [feedToRemove, setFeedToRemove] = useState<Feed | null>(null);
  const [mobileNav, setMobileNav] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [tagsOpen, setTagsOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const noteFocusRef = useRef<(() => void) | null>(null);
  const listenRef = useRef<ListenControlsHandle>(null);
  const caretWordRef = useRef<(() => number | null) | null>(null);

  const loadNav = useCallback(async () => {
    const [nextFeeds, nextCategories, nextTags, nextStats, nextNotes, nextBackups] = await Promise.all([
      api.feeds(),
      api.categories(),
      api.tags(),
      api.stats(),
      api.notes(),
      api.backups(),
    ]);
    setFeeds(nextFeeds);
    setCategories(nextCategories);
    setTags(nextTags);
    setStats(nextStats);
    setNotes(nextNotes);
    setBackups(nextBackups);
  }, []);

  const loadList = useCallback(async () => {
    setLoadingList(true);
    setListError(null);
    try {
      if (shelf.kind === "notes") {
        const nextNotes = await api.notes();
        setNotes(nextNotes);
        setItems([]);
        setTotal(nextNotes.length);
        return;
      }
      if (shelf.kind === "search") {
        const page = await api.search(shelf.q);
        setItems(page.items.map((hit) => ({ ...hit.article, summary: hit.headline ?? hit.article.summary })));
        setTotal(page.total);
        return;
      }
      const params: Record<string, string | number | boolean> = { limit: 50 };
      if (shelf.kind === "unread") params.read = false;
      if (shelf.kind === "saved") params.saved = true;
      if (shelf.kind === "starred") params.starred = true;
      if (shelf.kind === "feed") params.feed_id = shelf.id;
      if (shelf.kind === "category") params.category_id = shelf.id;
      if (shelf.kind === "tag") params.tag_id = shelf.id;
      const page = await api.articles(params);
      setItems(page.items);
      setTotal(page.total);
    } catch (error) {
      setListError(error instanceof ApiError ? error.message : "Could not load articles");
    } finally {
      setLoadingList(false);
    }
  }, [shelf]);

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
        setSelectedId(next.id);
        setShelf({ kind: "saved" });
        void loadNav();
      })
      .catch((error) => {
        toast.error(error instanceof ApiError ? error.message : "Could not save that URL");
      });
  }, [loadNav]);

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
      if (typing || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "j" || event.key === "k") {
        event.preventDefault();
        if (!items.length) return;
        const index = selectedId ? items.findIndex((item) => item.id === selectedId) : -1;
        const nextIndex = event.key === "j" ? Math.min(items.length - 1, index + 1) : Math.max(0, index <= 0 ? 0 : index - 1);
        const next = items[index < 0 ? 0 : nextIndex];
        if (next) setSelectedId(next.id);
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
      if (event.key === "l") {
        event.preventDefault();
        const caret = caretWordRef.current?.();
        if (caret != null) listenRef.current?.playFromWord(caret);
        else listenRef.current?.togglePlay();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [article, items, selectedId]);

  useEffect(() => {
    void loadList();
    setSelectedIds([]);
  }, [loadList]);

  useEffect(() => {
    if (!selectedId) {
      setArticle(null);
      return;
    }
    let cancelled = false;
    setLoadingArticle(true);
    api
      .article(selectedId)
      .then((next) => {
        if (!cancelled) setArticle(next);
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
      <aside className="hidden h-full min-h-0 w-72 shrink-0 flex-col overflow-hidden bg-sidebar text-sidebar-foreground md:flex">{nav}</aside>
      <Sheet open={mobileNav} onOpenChange={setMobileNav}>
        <SheetContent side="left" className="w-80 overflow-hidden bg-sidebar p-0 text-sidebar-foreground">
          <SheetHeader className="sr-only">
            <SheetTitle>Library</SheetTitle>
          </SheetHeader>
          {nav}
        </SheetContent>
      </Sheet>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b px-3">
          <Button variant="ghost" size="icon" className="md:hidden" onClick={() => setMobileNav(true)}>
            <Menu className="size-4" />
          </Button>
          <form
            className="flex-1 max-w-xl"
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
          <div className="ml-auto text-xs text-muted-foreground hidden sm:block">
            {stats ? `${stats.saved_count} kept · ${stats.unread_count} unread` : ""}
            <span className="ml-3 hidden md:inline">j/k m s n / l</span>
          </div>
        </header>

        <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-1 overflow-hidden lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
          <section className={cn("flex h-full min-h-0 flex-col overflow-hidden border-r", selectedId && "hidden lg:flex")}>
            <div className="shrink-0 px-4 py-3 space-y-3">
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <h1 className="font-[family-name:var(--font-serif)] text-xl">{shelfTitle(shelf, feeds, categories, tags)}</h1>
                  <p className="text-xs text-muted-foreground">{total} {shelf.kind === "notes" ? "notes" : "articles"}</p>
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
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
              {loadingList ? (
                <EmptyState icon={<LoaderCircle className="size-5 animate-spin" />} title="Opening the shelf" body="Fetching the latest from your archive." />
              ) : listError ? (
                <EmptyState title="Could not load this shelf" body={listError} />
              ) : shelf.kind === "notes" ? (
                notes.length === 0 ? (
                  <EmptyState title="No notes yet" body="Open an article and write a margin note. Those thoughts stay with the story." />
                ) : (
                  notes.map((note) => (
                    <button
                      key={note.id}
                      type="button"
                      onClick={() => setSelectedId(note.article_id)}
                      className="w-full text-left px-4 py-3 border-b hover:bg-accent/50"
                    >
                      <p className="text-xs text-muted-foreground">{note.article_title}</p>
                      <div className="text-sm mt-1 note-md line-clamp-3" dangerouslySetInnerHTML={{ __html: renderMarkdown(note.body) }} />
                      <p className="text-[11px] text-muted-foreground mt-1">
                        {formatRelative(note.updated_at || note.created_at)}
                      </p>
                    </button>
                  ))
                )
              ) : items.length === 0 ? (
                <EmptyState
                  title={shelf.kind === "saved" ? "Nothing kept yet" : "This shelf is empty"}
                  body={
                    shelf.kind === "inbox" || shelf.kind === "unread"
                      ? "Add a feed to start collecting stories you want to keep."
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
                    onClick={() => setSelectedId(item.id)}
                  />
                ))
              )}
            </div>
          </section>

          <section className={cn("flex h-full min-h-0 flex-col overflow-hidden bg-card", !selectedId && "hidden lg:flex")}>
            {loadingArticle ? (
              <EmptyState icon={<LoaderCircle className="size-5 animate-spin" />} title="Opening article" body="Loading the stored text, not just the link." />
            ) : article ? (
              <Reader
                article={article}
                tags={tags}
                listenRef={listenRef}
                noteFocusRef={noteFocusRef}
                caretWordRef={caretWordRef}
                onBack={() => setSelectedId(null)}
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
                onNote={async (body) => {
                  await api.addNote(article.id, body);
                  const next = await api.article(article.id);
                  setArticle(next);
                  void loadNav();
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
          setSelectedId(articleId);
          setShelf({ kind: "saved" });
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
        <NavButton active={shelf.kind === "starred"} onClick={() => onShelf({ kind: "starred" })} icon={<Star className="size-4" />}>
          Starred
        </NavButton>
        <NavButton active={shelf.kind === "notes"} onClick={() => onShelf({ kind: "notes" })} icon={<NotebookPen className="size-4" />} count={stats?.annotation_count}>
          Notes
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
          <span className="truncate">{item.feed_title || "Feed"}</span>
          <span>·</span>
          <span>{formatRelative(item.published_at)}</span>
          {item.is_saved ? <Bookmark className="size-3 ml-auto text-primary" /> : null}
        </div>
        <p className={cn("mt-1 font-medium leading-snug", !item.is_read && "text-foreground")}>{item.title}</p>
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
  onBack,
  onToggleRead,
  onToggleSaved,
  onToggleStar,
  onExtract,
  onArchive,
  onTag,
  onNote,
}: {
  article: Article;
  tags: Tag[];
  listenRef: React.RefObject<ListenControlsHandle | null>;
  noteFocusRef: React.MutableRefObject<(() => void) | null>;
  caretWordRef: React.MutableRefObject<(() => number | null) | null>;
  onBack: () => void;
  onToggleRead: () => void;
  onToggleSaved: () => void;
  onToggleStar: () => void;
  onExtract: () => Promise<void>;
  onArchive: () => Promise<void>;
  onTag: (name: string) => Promise<void>;
  onNote: (body: string) => Promise<void>;
}) {
  const [note, setNote] = useState("");
  const [tag, setTag] = useState("");
  const [busy, setBusy] = useState(false);
  const [activeWord, setActiveWord] = useState<number | null>(null);
  const articleRef = useRef<HTMLElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const noteRef = useRef<HTMLTextAreaElement>(null);
  const html = article.content_html ? sanitizeHtml(article.content_html) : "";
  const titleSpoken = spokenTitle(article.title);
  const titleWordCount = countWords(titleSpoken);
  const fallbackBody = article.content_text || stripHtml(article.summary) || "";
  const [bodyHtml, setBodyHtml] = useState(html || "");
  const suggestions = tags
    .filter((item) => !article.tags.some((attached) => attached.id === item.id))
    .filter((item) => !tag.trim() || item.name.toLowerCase().includes(tag.trim().toLowerCase()))
    .slice(0, 8);

  useEffect(() => {
    if (html) {
      setBodyHtml(wrapHtmlWords(html, titleWordCount));
      return;
    }
    if (fallbackBody) {
      setBodyHtml(wrapPlainWords(fallbackBody, titleWordCount));
      return;
    }
    setBodyHtml("");
  }, [article.id, fallbackBody, html, titleWordCount]);

  useEffect(() => {
    setActiveWord(null);
    setNote("");
    setTag("");
  }, [article.id]);

  useEffect(() => {
    noteFocusRef.current = () => noteRef.current?.focus();
    caretWordRef.current = () => wordIndexFromCaret(articleRef.current);
    return () => {
      noteFocusRef.current = null;
      caretWordRef.current = null;
    };
  }, [caretWordRef, noteFocusRef]);

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
        className="max-w-3xl mx-auto px-5 py-6"
        onClick={(event) => {
          const word = (event.target as HTMLElement).closest("[data-tts-word]");
          if (word instanceof HTMLElement) {
            const index = Number(word.dataset.ttsWord);
            if (Number.isFinite(index)) setActiveWord(index);
          }
        }}
      >
        <Button variant="ghost" className="lg:hidden mb-3 -ml-2" onClick={onBack}>
          Back to list
        </Button>
        <p className="text-xs uppercase tracking-[0.14em] text-muted-foreground">
          {article.feed_title} · {formatRelative(article.published_at)}
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
            getCaretWord={() => wordIndexFromCaret(articleRef.current) ?? (activeWord != null ? activeWord : null)}
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
        {bodyHtml ? (
          <div className="article-body" dangerouslySetInnerHTML={{ __html: bodyHtml }} />
        ) : (
          <EmptyState
            title="Only the feed snippet is stored"
            body="The original page has not been extracted yet. Use Re-extract to pull the full article, or Snapshot to keep a copy."
          />
        )}
        <Separator className="my-8" />
        <section className="space-y-4 pb-10">
          <h2 className="font-[family-name:var(--font-serif)] text-xl">Keep it findable</h2>
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
          <form
            className="space-y-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (!note.trim()) return;
              void onNote(note.trim()).then(() => setNote(""));
            }}
          >
            <Textarea
              ref={noteRef}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Markdown note to your future self… (n)"
              rows={4}
            />
            <Button type="submit">Save note</Button>
          </form>
          {article.annotations.length === 0 ? (
            <p className="text-sm text-muted-foreground">No notes on this story yet.</p>
          ) : (
            <ul className="space-y-3">
              {article.annotations.map((item) => (
                <li key={item.id} className="rounded-lg border bg-background px-3 py-2">
                  {item.quote ? <p className="text-sm italic text-muted-foreground">“{item.quote}”</p> : null}
                  <div className="text-sm mt-1 note-md" dangerouslySetInnerHTML={{ __html: renderMarkdown(item.body) }} />
                  <p className="text-[11px] text-muted-foreground mt-1">
                    Added {formatRelative(item.created_at)}
                    {item.updated_at && item.updated_at !== item.created_at ? ` · edited ${formatRelative(item.updated_at)}` : ""}
                  </p>
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
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  categories: Category[];
  onAdded: () => Promise<void>;
  onSavedPage: (articleId: string) => Promise<void>;
}) {
  const [tab, setTab] = useState<"feed" | "page" | "opml">("feed");
  const [url, setUrl] = useState("");
  const [pageUrl, setPageUrl] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [busy, setBusy] = useState(false);
  const [candidates, setCandidates] = useState<{ url: string; title: string | null }[]>([]);
  const bookmarklet =
    typeof window === "undefined"
      ? ""
      : `javascript:void(location='${window.location.origin}/?save='+encodeURIComponent(location.href))`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Collect</DialogTitle>
          <DialogDescription>
            Subscribe to a site, save a single page, or bring in an OPML list of feeds.
          </DialogDescription>
        </DialogHeader>
        <div className="flex gap-1 rounded-lg bg-muted p-1">
          {(
            [
              ["feed", "Feed"],
              ["page", "Save URL"],
              ["opml", "OPML"],
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
            JSON export is always local. Database dumps use pg_dump. If S3 is configured, a copy is uploaded automatically.
          </DialogDescription>
        </DialogHeader>
        <div className="flex gap-2">
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
