"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Archive,
  Bookmark,
  BookmarkCheck,
  Inbox,
  LoaderCircle,
  Menu,
  NotebookPen,
  Plus,
  RefreshCw,
  Search,
  Star,
  StarOff,
} from "lucide-react";
import { toast } from "sonner";
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
  const [mobileNav, setMobileNav] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

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
    void loadList();
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
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search the archive…"
                className="pl-8 bg-card"
              />
            </div>
          </form>
          <div className="ml-auto text-xs text-muted-foreground hidden sm:block">
            {stats ? `${stats.saved_count} kept · ${stats.unread_count} unread` : ""}
          </div>
        </header>

        <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-1 overflow-hidden lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
          <section className={cn("flex h-full min-h-0 flex-col overflow-hidden border-r", selectedId && "hidden lg:flex")}>
            <div className="shrink-0 px-4 py-3">
              <h1 className="font-[family-name:var(--font-serif)] text-xl">{shelfTitle(shelf, feeds, categories, tags)}</h1>
              <p className="text-xs text-muted-foreground">{total} {shelf.kind === "notes" ? "notes" : "articles"}</p>
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
                      <p className="text-sm mt-1">{note.body}</p>
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
          Add feed
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
                    <NavButton
                      key={feed.id}
                      active={shelf.kind === "feed" && shelf.id === feed.id}
                      onClick={() => onShelf({ kind: "feed", id: feed.id })}
                      count={feed.unread_count}
                    >
                      {feed.title || feed.url}
                    </NavButton>
                  ))}
                </div>
              ) : null,
            )}
            {groupedFeeds.uncategorized.map((feed) => (
              <NavButton
                key={feed.id}
                active={shelf.kind === "feed" && shelf.id === feed.id}
                onClick={() => onShelf({ kind: "feed", id: feed.id })}
                count={feed.unread_count}
              >
                {feed.title || feed.url}
              </NavButton>
            ))}
          </>
        )}
        {tags.length > 0 ? (
          <>
            <p className="px-2 pt-5 pb-1 text-[11px] uppercase tracking-[0.14em] text-sidebar-foreground/50">Tags</p>
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
  onClick,
}: {
  item: ArticleListItem;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full text-left px-4 py-3 border-b hover:bg-accent/40",
        active && "bg-accent/70",
        !item.is_read && "bg-primary/4",
      )}
    >
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-muted-foreground">
        <span className="truncate">{item.feed_title || "Feed"}</span>
        <span>·</span>
        <span>{formatRelative(item.published_at)}</span>
        {item.is_saved ? <Bookmark className="size-3 ml-auto text-primary" /> : null}
      </div>
      <p className={cn("mt-1 font-medium leading-snug", !item.is_read && "text-foreground")}>{item.title}</p>
      <p className="mt-1 text-sm text-muted-foreground line-clamp-2">{stripHtml(item.summary)}</p>
    </button>
  );
}

function Reader({
  article,
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
  const html = article.content_html ? sanitizeHtml(article.content_html) : "";

  return (
    <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
      <article className="max-w-3xl mx-auto px-5 py-6">
        <Button variant="ghost" className="lg:hidden mb-3 -ml-2" onClick={onBack}>
          Back to list
        </Button>
        <p className="text-xs uppercase tracking-[0.14em] text-muted-foreground">
          {article.feed_title} · {formatRelative(article.published_at)}
        </p>
        <h1 className="font-[family-name:var(--font-serif)] text-3xl md:text-4xl leading-tight mt-2">{article.title}</h1>
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
        {html ? (
          <div className="article-body" dangerouslySetInnerHTML={{ __html: html }} />
        ) : article.content_text ? (
          <div className="article-body whitespace-pre-wrap">{article.content_text}</div>
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
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (!tag.trim()) return;
              void onTag(tag.trim()).then(() => setTag(""));
            }}
          >
            <Input value={tag} onChange={(event) => setTag(event.target.value)} placeholder="Add a tag, e.g. fusion" />
            <Button type="submit" variant="secondary">
              Tag
            </Button>
          </form>
          <form
            className="space-y-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (!note.trim()) return;
              void onNote(note.trim()).then(() => setNote(""));
            }}
          >
            <Textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="A note to your future self…" rows={4} />
            <Button type="submit">Save note</Button>
          </form>
          {article.annotations.length === 0 ? (
            <p className="text-sm text-muted-foreground">No notes on this story yet.</p>
          ) : (
            <ul className="space-y-3">
              {article.annotations.map((item) => (
                <li key={item.id} className="rounded-lg border bg-background px-3 py-2">
                  {item.quote ? <p className="text-sm italic text-muted-foreground">“{item.quote}”</p> : null}
                  <p className="text-sm mt-1">{item.body}</p>
                  <p className="text-[11px] text-muted-foreground mt-1">{formatRelative(item.created_at)}</p>
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

function AddFeedDialog({
  open,
  onOpenChange,
  categories,
  onAdded,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  categories: Category[];
  onAdded: () => Promise<void>;
}) {
  const [url, setUrl] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Subscribe to a feed</DialogTitle>
          <DialogDescription>Paste an RSS or Atom URL. Storykeep will import recent items and store their text.</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-3"
          onSubmit={async (event) => {
            event.preventDefault();
            setBusy(true);
            try {
              await api.addFeed(url, categoryId || null);
              toast.success("Feed added. Articles are importing.");
              setUrl("");
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
            <Label htmlFor="feed-url">Feed URL</Label>
            <Input
              id="feed-url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://example.com/feed.xml"
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
          <DialogFooter>
            <Button type="submit" disabled={busy}>
              {busy ? "Fetching…" : "Add feed"}
            </Button>
          </DialogFooter>
        </form>
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
