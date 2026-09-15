"use client";

import { Component, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  Archive,
  BookOpen,
  Bookmark,
  BookmarkCheck,
  Calculator,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronUp,
  FilePlus,
  GraduationCap,
  Inbox,
  Library,
  LoaderCircle,
  GripVertical,
  Maximize2,
  Menu,
  Minimize2,
  History,
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
import { CalculatorOverlay, type CalculatorHandle } from "@/components/calculator-overlay";
import { ArticleShareMenu } from "@/components/article-share-menu";
import { CorrectionCheck, DestinationSelect, FolderSelect, RssShelfSelect } from "@/components/destination-controls";
import { NoteAttachmentChips } from "@/components/note-attachments";
import { NoteComposer } from "@/components/note-composer";
import { useMovableWindow } from "@/components/movable-window";
import { SchoolToolsBar } from "@/components/school-tools-bar";
import { COMPOSE_POS_KEY } from "@/lib/movable-window";
import { ShelfScroller, type ShelfScrollerHandle } from "@/components/shelf-scroller";
import { ProfilePage } from "@/components/profile-page";
import { ShelfSwitcher } from "@/components/shelf-switcher";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { applyAppearanceFromUser } from "@/lib/appearance";
import { ApiError, api } from "@/lib/api";
import { normalizeUserProfile } from "@/lib/user-profile";
import { ArticleImage } from "@/components/article-image";
import { UserAvatar } from "@/components/user-avatar";
import { onCodeCopyClick } from "@/lib/code-copy";
import {
  extractWikilinkTargets,
  onReaderBodyClick,
  type WikilinkResolution,
} from "@/lib/wikilinks";
import {
  articleHeroImageUrl,
  articlePreviewFromListItem,
  articleReaderSource,
  formatRelative,
  isCtaOnlyArticleText,
  isDekOnlyArticleBody,
  isPollutedArticleHtml,
  isPollutedArticleText,
  isUsableArticleBody,
  mergeExtractArticle,
  sanitizeHtml,
  stripHtml,
} from "@/lib/format";
import { clearFindMarks, findMarksInArticle, focusFindMark } from "@/lib/article-find";
import {
  dedupeArticlesById,
  listNextPageOffset,
  listRemovesOnRead,
  listShowsUnreadOnly,
  nextDistinctArticle,
  prevDistinctArticle,
  shelfSupportsUnreadFilter,
} from "@/lib/list-navigation";
import { applyHighlights, HIGHLIGHT_COLORS, selectionInRoot } from "@/lib/highlights";
import { noteMarkdownHtml, parseArticleHash } from "@/lib/markdown";
import {
  ARTICLE_TEXT_SIZE_OPTIONS,
  articleTextSizeClass,
  readArticleTextSize,
  writeArticleTextSize,
  type ArticleTextSize,
} from "@/lib/reader-text-size";
import { asFilingDestination, DESTINATION_LABEL } from "@/lib/destinations";
import {
  destinationLabel,
  parseCustomNoteShelves,
  uniqueShelfId,
  type CustomNoteShelf,
  type FilingDestination,
} from "@/lib/custom-note-shelves";
import {
  folderById,
  foldersForShelf,
  isFolderShelf,
  matchFolderByName,
  shelfFolderId,
  shelfFromFilingDestination,
} from "@/lib/folders";
import { wordIndexFromSelection } from "@/lib/tts-words";
import {
  buildVisibleSpeechScript,
  visibleSpeechSections,
  wrapVisibleSpeechNodes,
} from "@/lib/tts-visible";
import type { VisibleSpeechPayload } from "@/lib/tts-visible";
import type {
  Archive as SnapshotRow,
  Article,
  ArticleListItem,
  Backup,
  Category,
  Profile,
  Feed,
  RssShelf,
  Shelf,
  Stats,
  Folder,
  Tag,
  User,
} from "@/lib/types";
import { showExtractCaughtError, showExtractFailed, showExtractSuccess } from "@/lib/extract-toast";
import { initialListDebug, listRangeLabel } from "@/lib/list-range";
import { toastErrorFromUnknown } from "@/lib/toast-message";
import { cn } from "@/lib/utils";

function isStoryKeepNote(article: Article): boolean {
  return (article.guid || "").startsWith("storykeep-note:");
}

function isVaultImport(article: Article): boolean {
  return (article.guid || "").startsWith("obsidian:") && article.source_kind !== "textbook";
}

const RSS_SHELF_KEY = "storykeep-rss-shelf-id";

function displayArticleShelf(article: Article): FilingDestination | "" {
  if (article.destination) {
    return asFilingDestination(article.destination, article.destination);
  }
  if (article.source_kind === "textbook") return "books";
  return "";
}

function snapshotKind(row: SnapshotRow): "html" | "pdf" {
  if (row.type === "pdf" || row.archive_type === "pdf") return "pdf";
  return "html";
}

function snapshotStamp(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

const PDF_WORKER_SRC = "/pdf.worker.min.mjs";

type PdfPaintStats = {
  status: number;
  pageCount: number;
  firstCanvasHeight: number;
  clientHeight: number;
  scrollHeight: number;
};

async function toggleBrowserFullscreen(selectors: string) {
  try {
    if (document.fullscreenElement) {
      await document.exitFullscreen();
      return;
    }
    const el = document.querySelector<HTMLElement>(selectors);
    if (el?.requestFullscreen) await el.requestFullscreen();
  } catch {
    /* permission or unsupported */
  }
}

const PDF_MAX_CANVAS = 4096;
const PDF_FIRST_PAGES = 2;

class PdfRestoreBoundary extends Component<
  { children: ReactNode; onError?: (message: string) => void },
  { message: string | null }
> {
  state: { message: string | null } = { message: null };

  static getDerivedStateFromError(error: Error) {
    return { message: error?.message || "PDF restore failed." };
  }

  componentDidCatch(error: Error) {
    this.props.onError?.(error?.message || "PDF restore failed.");
  }

  render() {
    if (this.state.message) {
      return <p className="reader-chrome px-0 py-2 text-sm text-destructive">{this.state.message}</p>;
    }
    return this.props.children;
  }
}

function PdfSnapshotViewer({
  archiveId,
  onReady,
  onFailed,
}: {
  archiveId: string;
  onReady?: () => void;
  onFailed?: (message: string) => void;
}) {
  const fileUrl = `/api/v1/archives/${encodeURIComponent(String(archiveId || ""))}/file`;
  const hostRef = useRef<HTMLDivElement>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const blobUrlRef = useRef<string | null>(null);
  const pdfRef = useRef<{ destroy?: () => Promise<unknown> } | null>(null);
  const onReadyRef = useRef(onReady);
  const onFailedRef = useRef(onFailed);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<PdfPaintStats | null>(null);
  onReadyRef.current = onReady;
  onFailedRef.current = onFailed;

  const fail = (message: string) => {
    setLoading(false);
    setError(message);
    try {
      onFailedRef.current?.(message);
    } catch {
      /* never let a callback take down the app */
    }
  };

  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;
    const onKey = (event: KeyboardEvent) => {
      try {
        let node: HTMLElement | null = scroller;
        let host: HTMLElement | null = null;
        while (node) {
          const style = window.getComputedStyle(node);
          if ((style.overflowY === "auto" || style.overflowY === "scroll") && node.scrollHeight > node.clientHeight + 1) {
            host = node;
            break;
          }
          node = node.parentElement;
        }
        if (!host) return;
        const line = 48;
        const page = Math.max(host.clientHeight - 24, 80);
        if (event.key === "ArrowDown") host.scrollTop += line;
        else if (event.key === "ArrowUp") host.scrollTop -= line;
        else if (event.key === "PageDown") host.scrollTop += page;
        else if (event.key === "PageUp") host.scrollTop -= page;
        else if (event.key === "Home") host.scrollTop = 0;
        else if (event.key === "End") host.scrollTop = host.scrollHeight;
        else return;
        event.preventDefault();
      } catch {
        /* ignore */
      }
    };
    scroller.addEventListener("keydown", onKey);
    return () => scroller.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) {
      fail("PDF pane is missing.");
      return;
    }
    let cancelled = false;
    let widthObserver: ResizeObserver | null = null;
    let widthTimer: number | undefined;
    let raf = 0;
    try {
      scroller.replaceChildren();
    } catch {
      fail("Could not prepare the PDF pane.");
      return;
    }
    setError(null);
    setLoading(true);
    setStats(null);

    const waitForWidth = () =>
      new Promise<number>((resolve) => {
        let settled = false;
        const finish = (width: number) => {
          if (settled) return;
          settled = true;
          widthObserver?.disconnect();
          widthObserver = null;
          if (widthTimer !== undefined) {
            window.clearTimeout(widthTimer);
            widthTimer = undefined;
          }
          if (raf) window.cancelAnimationFrame(raf);
          raf = 0;
          resolve(Math.max(1, width));
        };
        const read = () =>
          Math.max(
            scroller.clientWidth || 0,
            scroller.parentElement?.clientWidth || 0,
            hostRef.current?.clientWidth || 0,
          );
        const tick = () => {
          if (cancelled) {
            finish(0);
            return;
          }
          const width = read();
          if (width > 0) {
            finish(width);
            return;
          }
          raf = window.requestAnimationFrame(tick);
        };
        try {
          widthObserver = new ResizeObserver(() => {
            const width = read();
            if (width > 0) finish(width);
          });
          widthObserver.observe(scroller);
        } catch {
          /* ResizeObserver missing */
        }
        tick();
        widthTimer = window.setTimeout(() => finish(Math.max(read(), 320)), 8000);
      });

    // pdf.js page objects are typed more strictly than we need here.
    const paintPage = async (doc: { getPage: (n: number) => Promise<any> }, pageNumber: number, width: number) => {
      const page = await doc.getPage(pageNumber);
      const unscaled = page.getViewport({ scale: 1 });
      const pageWidth = unscaled.width || 1;
      const pageHeight = unscaled.height || 1;
      let scale = width / pageWidth;
      if (!Number.isFinite(scale) || scale <= 0) scale = 1;
      const maxScale = Math.min(PDF_MAX_CANVAS / pageWidth, PDF_MAX_CANVAS / pageHeight);
      scale = Math.min(scale, maxScale);
      const viewport = page.getViewport({ scale });
      const wrap = document.createElement("div");
      wrap.className = "pdf-page";
      wrap.style.display = "block";
      wrap.style.width = "100%";
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.floor(viewport.width));
      canvas.height = Math.max(1, Math.floor(viewport.height));
      canvas.style.display = "block";
      canvas.style.width = "100%";
      canvas.style.height = "auto";
      canvas.style.pointerEvents = "none";
      wrap.appendChild(canvas);
      const context = canvas.getContext("2d", { alpha: false });
      if (!context) throw new Error("Could not draw the PDF snapshot.");
      await page.render({ canvasContext: context, viewport }).promise;
      if (!cancelled) scroller.appendChild(wrap);
      return canvas;
    };

    void (async () => {
      try {
        if (!archiveId) throw new Error("This PDF restore is missing an archive id.");
        const response = await fetch(fileUrl, { credentials: "include", cache: "no-store" });
        let bodyText = "";
        const buffer = response.ok ? await response.arrayBuffer() : null;
        if (!response.ok || !buffer) {
          bodyText = (await response.text().catch(() => "")).slice(0, 80);
          throw new Error(`GET ${fileUrl} returned HTTP ${response.status}. ${bodyText}`.trim());
        }
        const bytes = new Uint8Array(buffer);
        const headText = Array.from(bytes.slice(0, 80), (byte) => String.fromCharCode(byte)).join("");
        if (!headText.startsWith("%PDF")) {
          throw new Error(`Archive file is not a PDF (HTTP ${response.status}). First bytes: ${headText.slice(0, 80)}`);
        }
        if (cancelled) return;
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = PDF_WORKER_SRC;
        const loadingTask = pdfjs.getDocument({ data: bytes.slice() });
        const doc = await loadingTask.promise;
        pdfRef.current = doc;
        const pageCount = Number(doc.numPages) || 0;
        if (pageCount < 1) throw new Error("That PDF has no pages.");
        const width = await waitForWidth();
        if (cancelled) return;
        if (width <= 0) throw new Error("The PDF pane has no width yet.");
        const firstLimit = Math.min(PDF_FIRST_PAGES, pageCount);
        let firstCanvas: HTMLCanvasElement | null = null;
        for (let pageNumber = 1; pageNumber <= firstLimit; pageNumber += 1) {
          if (cancelled) return;
          const canvas = await paintPage(doc, pageNumber, width);
          if (pageNumber === 1) firstCanvas = canvas;
        }
        const firstHeight = firstCanvas
          ? Math.round(firstCanvas.getBoundingClientRect().height) || firstCanvas.height
          : 0;
        if (firstHeight <= 0) throw new Error("PDF pages rendered with no height.");
        if (cancelled) return;
        setStats({
          status: response.status,
          pageCount,
          firstCanvasHeight: firstHeight,
          clientHeight: scroller.clientHeight,
          scrollHeight: scroller.scrollHeight,
        });
        setLoading(false);
        try {
          onReadyRef.current?.();
        } catch {
          /* keep HTML if parent callback throws */
        }
        for (let pageNumber = firstLimit + 1; pageNumber <= pageCount; pageNumber += 1) {
          if (cancelled) return;
          await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
          if (cancelled) return;
          await paintPage(doc, pageNumber, width);
        }
      } catch (caught) {
        if (cancelled) return;
        const message = caught instanceof Error ? caught.message : "Could not load the PDF snapshot.";
        fail(message);
      }
    })();

    return () => {
      cancelled = true;
      widthObserver?.disconnect();
      if (widthTimer !== undefined) window.clearTimeout(widthTimer);
      if (raf) window.cancelAnimationFrame(raf);
      try {
        scroller.replaceChildren();
      } catch {
        /* ignore */
      }
      const pdf = pdfRef.current;
      pdfRef.current = null;
      void Promise.resolve()
        .then(() => pdf?.destroy?.())
        .catch(() => undefined)
        .finally(() => {
          if (blobUrlRef.current) {
            URL.revokeObjectURL(blobUrlRef.current);
            blobUrlRef.current = null;
          }
        });
    };
  }, [archiveId, fileUrl]);

  return (
    <div
      ref={hostRef}
      className="pdf-host bg-muted"
      data-pdf-pending={loading && !error ? "1" : undefined}
      data-pdf-failed={error ? "1" : undefined}
    >
      {error ? <p className="reader-chrome px-3 py-2 text-sm text-destructive">{error}</p> : null}
      {loading && !error ? (
        <p className="reader-chrome px-3 py-2 text-sm text-muted-foreground">Loading PDF snapshot…</p>
      ) : null}
      {stats && !error ? (
        <p className="reader-chrome px-3 py-1 text-[0.7rem] text-muted-foreground">
          {stats.pageCount} page{stats.pageCount === 1 ? "" : "s"} · HTTP {stats.status} · first canvas{" "}
          {stats.firstCanvasHeight}px
        </p>
      ) : null}
      <div
        ref={scrollerRef}
        className="pdf-scroller"
        tabIndex={0}
        role="region"
        aria-label="PDF snapshot"
      />
    </div>
  );
}

function readerActionError(error: unknown, fallback: string): never {
  toastErrorFromUnknown(error, fallback);
  throw error;
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

function shelfTitle(
  shelf: Shelf,
  feeds: Feed[],
  categories: Category[],
  tags: Tag[],
  folders: Folder[],
  customNoteShelves: CustomNoteShelf[],
): string {
  switch (shelf.kind) {
    case "inbox":
      return "All stories";
    case "unread":
      return "Unread";
    case "saved":
      return "Saved for life";
    case "starred":
      return "Starred";
    case "notes": {
      const folder = shelf.folderId ? folderById(folders, shelf.folderId) : undefined;
      return folder ? `${folder.name} · Notes` : "Notes";
    }
    case "vault": {
      const folder = shelf.folderId ? folderById(folders, shelf.folderId) : undefined;
      return folder ? `${folder.name} · Vault` : "Vault";
    }
    case "additions": {
      const folder = shelf.folderId ? folderById(folders, shelf.folderId) : undefined;
      return folder ? `${folder.name} · Additions` : "Additions";
    }
    case "books": {
      const folder = shelf.folderId ? folderById(folders, shelf.folderId) : undefined;
      return folder ? `${folder.name} · Books` : "Books";
    }
    case "schoolwork": {
      const folder = shelf.folderId ? folderById(folders, shelf.folderId) : undefined;
      return folder ? `${folder.name} · Schoolwork` : "Schoolwork";
    }
    case "custom": {
      const folder = shelf.folderId ? folderById(folders, shelf.folderId) : undefined;
      const label = destinationLabel(shelf.id, customNoteShelves);
      return folder ? `${folder.name} · ${label}` : label;
    }
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
    case "custom":
      return shelf.folderId ? `custom:${shelf.id}:folder:${shelf.folderId}` : `custom:${shelf.id}`;
    default:
      if (isFolderShelf(shelf) && shelf.folderId) return `${shelf.kind}:folder:${shelf.folderId}`;
      return shelf.kind;
  }
}

const LIST_PAGE = 40;

export function LibraryApp({ user, onUserChange }: { user: User; onUserChange?: (patch: Profile) => void }) {
  const router = useRouter();

  useEffect(() => {
    applyAppearanceFromUser(user);
  }, [user]);
  const [customNoteShelves, setCustomNoteShelves] = useState<CustomNoteShelf[]>(() =>
    parseCustomNoteShelves(user.preferences),
  );
  useEffect(() => {
    setCustomNoteShelves(parseCustomNoteShelves(user.preferences));
  }, [user.preferences]);
  const [feeds, setFeeds] = useState<Feed[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [rssShelves, setRssShelves] = useState<RssShelf[]>([]);
  const [activeRssShelfId, setActiveRssShelfId] = useState<string | null>(null);
  const [tags, setTags] = useState<Tag[]>([]);
  const [folders, setFolders] = useState<Folder[]>([]);
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
  const [profileOpen, setProfileOpen] = useState(false);
  const [unreadOnlyFilter, setUnreadOnlyFilter] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [feedToRemove, setFeedToRemove] = useState<Feed | null>(null);
  const [articleToDelete, setArticleToDelete] = useState<ArticleListItem | null>(null);
  const [mobileNav, setMobileNav] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [tagsOpen, setTagsOpen] = useState(false);
  const [readerFull, setReaderFull] = useState(false);
  const [deployBuild, setDeployBuild] = useState<string | null>(
    process.env.NEXT_PUBLIC_BUILD_SHA?.trim() || null,
  );
  const searchRef = useRef<HTMLInputElement>(null);
  const noteFocusRef = useRef<(() => void) | null>(null);
  const listenRef = useRef<ListenControlsHandle>(null);
  const calculatorRef = useRef<CalculatorHandle>(null);
  const caretWordRef = useRef<(() => number | null) | null>(null);
  const itemsRef = useRef<ArticleListItem[]>([]);
  const totalRef = useRef(0);
  const selectedIdRef = useRef<string | null>(null);
  const listGenRef = useRef(0);
  const loadMoreGenRef = useRef(0);
  const firstPageReadyRef = useRef(false);
  const loadingMoreRef = useRef(false);
  const listScrollerRef = useRef<ShelfScrollerHandle>(null);
  const listFeedKeyRef = useRef<string>(shelfKey(shelf));
  const shelfRef = useRef(shelf);
  const loadListRef = useRef<(() => Promise<void>) | null>(null);
  const fetchedCountRef = useRef(0);
  const unreadOnlyFilterRef = useRef(false);
  const advancingRef = useRef(false);
  const [listEpoch, setListEpoch] = useState(0);
  const [listFirstOffset, setListFirstOffset] = useState(0);
  const [listFirstPage, setListFirstPage] = useState(1);
  const [listFirstFetchUrl, setListFirstFetchUrl] = useState("");
  const [listDebug, setListDebug] = useState(initialListDebug);
  const [readerScrollToken, setReaderScrollToken] = useState(0);
  itemsRef.current = items;
  totalRef.current = total;
  selectedIdRef.current = selectedId;
  shelfRef.current = shelf;
  unreadOnlyFilterRef.current = unreadOnlyFilter;

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

  useEffect(() => {
    void loadNav().catch((error) => {
      toast.error(error instanceof ApiError ? error.message : "Could not load library");
    });
  }, [loadNav]);

  useEffect(() => {
    void api
      .health()
      .then((info) => {
        if (info.build && info.build !== "unknown") setDeployBuild(info.build);
      })
      .catch(() => {
        /* ignore */
      });
  }, []);

  useEffect(() => {
    const openFromLocation = () => {
      const fromHash = parseArticleHash(window.location.hash);
      const fromQuery = new URLSearchParams(window.location.search).get("article");
      const articleId = fromHash || fromQuery;
      if (!articleId) return;
      if (fromQuery) {
        const hash = fromHash ? `#article/${fromHash}` : "";
        window.history.replaceState({}, "", `${window.location.pathname}${hash}`);
      }
      openArticle(articleId);
    };
    openFromLocation();
    window.addEventListener("hashchange", openFromLocation);
    return () => window.removeEventListener("hashchange", openFromLocation);
  }, [openArticle]);

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

  const clearReaderSelection = useCallback(() => {
    selectedIdRef.current = null;
    setSelectedId(null);
    setArticle(null);
  }, []);

  const selectRelative = useCallback(
    (delta: number) => {
      void (async () => {
        if (advancingRef.current) return;
        advancingRef.current = true;
        try {
          let list = dedupeArticlesById(itemsRef.current);
          if (list.length !== itemsRef.current.length) {
            itemsRef.current = list;
            setItems(list);
          }
          if (!list.length) return;
          const currentId = selectedIdRef.current;

          if (delta < 0) {
            const prev = prevDistinctArticle(list, currentId);
            if (!prev) {
              toast.message("End of list");
              return;
            }
            openArticle(prev.id);
            return;
          }

          if (currentId) {
            const current = list.find((item) => item.id === currentId);
            const queueRemovesOnRead = listRemovesOnRead(shelfRef.current);
            const markingRead = Boolean(current && !current.is_read);
            const shouldRemove = Boolean(queueRemovesOnRead && current);

            if (current && markingRead) {
              setArticle((row) => (row?.id === currentId ? { ...row, is_read: true } : row));
              void api
                .patchArticle(currentId, { is_read: true })
                .then((next) => {
                  if (!shouldRemove) {
                    setItems((rows) =>
                      rows.map((row) => (row.id === currentId ? { ...row, is_read: next.is_read, read_at: next.read_at } : row)),
                    );
                  }
                  if (selectedIdRef.current === currentId) {
                    setArticle((row) => (row?.id === currentId ? { ...row, is_read: next.is_read, read_at: next.read_at } : row));
                  }
                  void loadNav();
                })
                .catch(() => {
                  if (!shouldRemove) {
                    setItems((rows) => rows.map((row) => (row.id === currentId ? { ...row, is_read: false } : row)));
                    if (selectedIdRef.current === currentId) {
                      setArticle((row) => (row?.id === currentId ? { ...row, is_read: false } : row));
                    }
                  }
                });
            }

            if (shouldRemove) {
              list = list.filter((row) => row.id !== currentId);
              itemsRef.current = list;
              setItems(list);
              setTotal((count) => Math.max(0, count - 1));
            } else if (markingRead) {
              list = list.map((row) => (row.id === currentId ? { ...row, is_read: true } : row));
              itemsRef.current = list;
              setItems(list);
            }
          }

          let target = nextDistinctArticle(list, currentId);
          if (!target) {
            await loadMore();
            list = dedupeArticlesById(itemsRef.current);
            target = nextDistinctArticle(list, currentId);
          }
          if (!target || target.id === currentId) {
            toast.message("End of list");
            return;
          }
          openArticle(target.id);
        } finally {
          advancingRef.current = false;
        }
      })();
    },
    [loadMore, loadNav, openArticle],
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
      if (event.key === "Escape") {
        if (listenRef.current?.isActive()) {
          event.preventDefault();
          listenRef.current.stop();
          return;
        }
        if (readerFull) {
          event.preventDefault();
          setReaderFull(false);
          return;
        }
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
        if (article.offline_view === "pdf") {
          void toggleBrowserFullscreen(".pdf-host, .reader-shell");
        } else {
          setReaderFull((current) => !current);
        }
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
    if (!shelfSupportsUnreadFilter(shelf)) {
      setUnreadOnlyFilter(false);
    }
  }, [shelf]);

  useEffect(() => {
    if (!selectedId) {
      selectedIdRef.current = null;
      setArticle(null);
      setReaderFull(false);
      setLoadingArticle(false);
    }
  }, [selectedId]);

  const autoExtractRef = useRef<string | null>(null);
  useEffect(() => {
    if (!selectedId || !article) return;
    if (isStoryKeepNote(article)) return;
    if (!isDekOnlyArticleBody(article.content_html, article.content_text)) {
      autoExtractRef.current = null;
      return;
    }
    if (autoExtractRef.current === article.id) return;
    autoExtractRef.current = article.id;

    let cancelled = false;
    const previous = article;
    void api
      .extract(selectedId)
      .then((result) => {
        if (cancelled || selectedIdRef.current !== selectedId) return;
        const mergedBody = mergeExtractArticle(previous, result.article);
        const merged = { ...result.article, ...mergedBody };
        setArticle((current) => (current && current.id === selectedId ? { ...current, ...merged } : current));
        if (isUsableArticleBody(merged.content_html, merged.content_text)) {
          setReaderScrollToken((current) => current + 1);
          setItems((current) =>
            current.map((item) =>
              item.id === selectedId
                ? { ...item, has_full_text: isUsableArticleBody(merged.content_html, merged.content_text) }
                : item,
            ),
          );
        }
      })
      .catch(() => {
        /* Keep dek visible in the reader. */
      });
    return () => {
      cancelled = true;
    };
  }, [article, selectedId]);

  const groupedFeeds = useMemo(() => {
    const shelfCategories = categories
      .filter((category) => !activeRssShelfId || category.shelf_id === activeRssShelfId)
      .sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name));
    return {
      groups: shelfCategories.map((category) => ({
        category,
        feeds: feeds.filter((feed) => feed.category_id === category.id),
      })),
    };
  }, [activeRssShelfId, categories, feeds]);

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

  function openProfile() {
    setMobileNav(false);
    setProfileOpen(true);
  }

  function closeProfile() {
    setProfileOpen(false);
    void api.me().then((next) => onUserChange?.(normalizeUserProfile(next))).catch(() => {});
  }

  const nav = (
    <Sidebar
      user={user}
      stats={stats}
      shelf={shelf}
      rssShelves={rssShelves}
      activeRssShelfId={activeRssShelfId}
      groupedFeeds={groupedFeeds}
      tags={tags}
      folders={folders}
      customNoteShelves={customNoteShelves}
      onCreateFolder={(shelfKind) => createFolderOnShelf(shelfKind)}
      onRenameFolder={(folder) => void renameFolderRow(folder)}
      onDeleteFolder={(folder) => void deleteFolderRow(folder)}
      onShelf={(next) => {
        setListFirstOffset(0);
        setListFirstPage(1);
        setListDebug(initialListDebug);
        setShelf(next);
        setSelectedId(null);
        setMobileNav(false);
      }}
      onRssShelfChange={(id) => void onRssShelfChange(id)}
      onAddRssShelf={() => void onAddRssShelf()}
      onAdd={() => setAddOpen(true)}
      onAddCategory={() => void onAddCategory()}
      onAddFeed={() => setAddOpen(true)}
      onRenameCategory={(category) => void onRenameCategory(category)}
      onDeleteCategory={(category) => void onDeleteCategory(category)}
      onChangeFeedCategory={(feed) => void onChangeFeedCategory(feed)}
      onRemoveFeed={(feed) => setFeedToRemove(feed)}
      onManageTags={() => setTagsOpen(true)}
      onBackup={() => setBackupOpen(true)}
      onRefresh={() => void onRefresh()}
      refreshing={refreshing}
      onLogout={async () => {
        await api.logout();
        router.replace("/login");
      }}
      onProfile={openProfile}
      deployBuild={deployBuild}
    />
  );

  const pdfRestoreOpen = article?.offline_view === "pdf";

  return (
    <div className="flex h-full min-h-0 overflow-hidden bg-[var(--storykeep-page-bg)]">
      <aside
        className={cn(
          "hidden h-full min-h-0 w-72 shrink-0 flex-col overflow-hidden bg-sidebar text-sidebar-foreground md:flex",
          readerFull && !pdfRestoreOpen && "!hidden",
        )}
      >
        {nav}
      </aside>
      <Sheet open={mobileNav} onOpenChange={setMobileNav}>
        <SheetContent side="left" className="w-80 overflow-hidden bg-sidebar p-0 text-sidebar-foreground">
          <SheetHeader className="sr-only">
            <SheetTitle>Library</SheetTitle>
          </SheetHeader>
          {nav}
        </SheetContent>
      </Sheet>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-[var(--storykeep-page-bg)]">
        <header className="flex min-h-14 shrink-0 flex-wrap items-center gap-2 border-b border-border bg-[var(--storykeep-top-bar)] px-3 py-1.5">
          <Button variant="ghost" size="icon" className="md:hidden" onClick={() => setMobileNav(true)}>
            <Menu className="size-4" />
          </Button>
          <form
            className="min-w-40 flex-1 max-w-xl"
            onSubmit={(event) => {
              event.preventDefault();
              const q = query.trim();
              if (!q) return;
              const nextShelf = { kind: "search" as const, q };
              const queryChanged = shelf.kind !== "search" || shelf.q !== q;
              setShelf(nextShelf);
              if (queryChanged) {
                setSelectedId(null);
                setArticle(null);
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
              variant="outline"
              title="Open the Calculator overlay"
              onClick={() => calculatorRef.current?.open()}
            >
              <Calculator className="size-3" />
              Calculator
            </Button>
            <Button
              size="xs"
              variant={readerFull ? "default" : "outline"}
              disabled={!article}
              title="Read this article full screen with every option still available"
              onClick={() => {
                if (article?.offline_view === "pdf") {
                  void toggleBrowserFullscreen(".pdf-host, .reader-shell");
                  return;
                }
                setReaderFull((current) => !current);
              }}
            >
              {readerFull ? <Minimize2 className="size-3" /> : <Maximize2 className="size-3" />}
              {readerFull ? "Exit" : "Fullscreen"}
              <kbd className="text-[10px] text-muted-foreground">f</kbd>
            </Button>
          </div>
        </header>

        <div className={cn("grid min-h-0 flex-1 overflow-hidden grid-cols-1 grid-rows-1 [grid-template-rows:minmax(0,1fr)] lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]", readerFull && !pdfRestoreOpen && "lg:grid-cols-1")}>
          <section className={cn("sk-page-surface flex min-h-0 flex-col overflow-hidden border-r", selectedId && "hidden lg:flex", readerFull && !pdfRestoreOpen && "!hidden")}>
            <div className="shrink-0 px-4 py-3 space-y-3">
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <h1 className="font-[family-name:var(--font-serif)] text-xl">{shelfTitle(shelf, feeds, categories, tags, folders, customNoteShelves)}</h1>
                  <p className="text-xs text-muted-foreground">{listRangeLabel(items.length, total, shelf.kind)}</p>
                </div>
                {shelfSupportsUnreadFilter(shelf) ? (
                  <Button
                    size="sm"
                    variant={unreadOnlyFilter ? "default" : "outline"}
                    title="Show unread items only in this list"
                    onClick={() => setUnreadOnlyFilter((current) => !current)}
                  >
                    Unread
                  </Button>
                ) : null}
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
              key={`${shelfKey(shelf)}-${listEpoch}`}
              ref={listScrollerRef}
              shelfKey={shelfKey(shelf)}
              listEpoch={listEpoch}
              itemCount={items.length}
              hasMore={!loadingList && items.length > 0 && items.length < total}
              loadingMore={loadingMore}
              loaded={items.length}
              total={total}
              onNearEnd={() => {
                if (firstPageReadyRef.current) void loadMore();
              }}
              onListPaint={({ feed, offset, startIndex, count }) => {
                if (listFeedKeyRef.current !== feed) return;
                setListDebug({ offset, startIndex, count });
                console.info("[StoryKeep] list first paint", { feed, offset, startIndex, count });
              }}
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
                items.map((item, index) => (
                  <ArticleRow
                    key={item.id}
                    listIndex={index}
                    item={item}
                    active={item.id === selectedId}
                    selected={selectedIds.includes(item.id)}
                    onToggleSelect={() => {
                      setSelectedIds((current) =>
                        current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id],
                      );
                    }}
                    onDelete={() => setArticleToDelete(item)}
                    onClick={() => selectArticle(item)}
                  />
                ))
              )}
            </ShelfScroller>
          </section>

          <section className={cn("sk-page-surface flex min-h-0 flex-col overflow-hidden", !selectedId && "hidden lg:flex", readerFull && "flex")}>
            {selectedId && article ? (
              <Reader
                article={article}
                tags={tags}
                folders={folders}
                customNoteShelves={customNoteShelves}
                onCreateNoteShelf={onCreateNoteShelf}
                onCreateFolder={createFolderOnShelf}
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
                  const id = article.id;
                  const previous = article;
                  try {
                    const result = await api.extract(id);
                    if (selectedIdRef.current !== id) return;
                    const mergedBody = mergeExtractArticle(previous, result.article);
                    const merged = { ...result.article, ...mergedBody };
                    setArticle((current) =>
                      current && current.id === id ? { ...current, ...merged } : { ...previous, ...merged },
                    );
                    if (!result.ok) {
                      showExtractFailed(result.message);
                      return;
                    }
                    setItems((current) =>
                      current.map((item) =>
                        item.id === id
                          ? { ...item, has_full_text: isUsableArticleBody(merged.content_html, merged.content_text) }
                          : item,
                      ),
                    );
                    setReaderScrollToken((current) => current + 1);
                    showExtractSuccess(result.message);
                  } catch (error) {
                    showExtractCaughtError(error);
                  }
                }}
                onUseFeedText={async () => {
                  const id = article.id;
                  try {
                    const next = await api.useFeedText(id);
                    if (selectedIdRef.current !== id) return;
                    setArticle(next);
                    setItems((current) =>
                      current.map((item) =>
                        item.id === id ? { ...item, has_full_text: Boolean(next.content_text?.trim()) } : item,
                      ),
                    );
                    setReaderScrollToken((current) => current + 1);
                    toast.success("Restored feed text");
                  } catch (error) {
                    toast.error(error instanceof ApiError ? error.message : "No feed text available");
                  }
                }}
                readerScrollToken={readerScrollToken}
                onArchive={async () => {
                  const id = article.id;
                  try {
                    await api.archive(id, "html");
                    const next = await api.article(id);
                    if (selectedIdRef.current !== id) return;
                    setArticle(next);
                    toast.success("Snapshot stored in the archive");
                    void loadNav();
                  } catch (error) {
                    readerActionError(error, "Could not store a snapshot");
                  }
                }}
                onArchivePdf={async () => {
                  const id = article.id;
                  try {
                    await api.archive(id, "pdf");
                    const next = await api.article(id);
                    if (selectedIdRef.current !== id) return;
                    setArticle(next);
                    toast.success("PDF snapshot stored in the archive");
                    void loadNav();
                  } catch (error) {
                    readerActionError(error, "Could not store a PDF snapshot");
                  }
                }}
                onRestore={async (archiveId) => {
                  const id = article.id;
                  try {
                    const next = await api.restore(id, archiveId);
                    if (selectedIdRef.current !== id) return;
                    try {
                      if (next.offline_view === "pdf" && !next.offline_archive_id) {
                        next.offline_archive_id = archiveId;
                      }
                      setArticle(next);
                      setReaderScrollToken((current) => current + 1);
                    } catch (caught) {
                      toast.error(caught instanceof Error ? caught.message : "Could not open that restore.");
                      return;
                    }
                    toast.success(
                      next.offline_view === "pdf"
                        ? "Offline view is the PDF snapshot. Article text was kept."
                        : "Restored the HTML snapshot. Current text was saved first.",
                    );
                    void loadNav();
                  } catch (error) {
                    readerActionError(error, "Could not restore that snapshot");
                    throw error;
                  }
                }}
                onTag={async (name) => {
                  const id = article.id;
                  try {
                    await api.attachTag(id, name);
                    const next = await api.article(id);
                    if (selectedIdRef.current !== id) return;
                    setArticle(next);
                    void loadNav();
                  } catch (error) {
                    readerActionError(error, "Could not add that tag");
                  }
                }}
                onNote={async (title, markdown, destination, isCorrection, folderId) => {
                  const id = article.id;
                  const hadCorrection = Boolean(article.corrections?.length);
                  try {
                    if (isCorrection) {
                      await api.upsertCorrection(id, markdown);
                    } else {
                      if (hadCorrection) {
                        await api.deleteCorrection(id);
                      }
                      await api.addAddition(id, title, markdown, destination, false, folderId);
                    }
                    const next = await api.article(id);
                    if (selectedIdRef.current !== id) return;
                    setArticle(next);
                    toast.success(
                      isCorrection
                        ? "Correction updated on this article. The vault original was not touched."
                        : "Note saved on that shelf. The vault original was not touched.",
                    );
                    void Promise.all([loadNav(), loadList()]);
                  } catch (error) {
                    readerActionError(error, "Could not save that note");
                  }
                }}
                onHighlight={async (payload) => {
                  const id = article.id;
                  try {
                    await api.addNote(id, payload.note || payload.quote, {
                      kind: "highlight",
                      quote: payload.quote,
                      color: payload.color,
                      prefix: payload.prefix,
                      suffix: payload.suffix,
                    });
                    const next = await api.article(id);
                    if (selectedIdRef.current !== id) return;
                    setArticle(next);
                    setItems((current) => current.map((item) => (item.id === next.id ? { ...item, ...next } : item)));
                    toast.success("Highlight saved in the overlay pack");
                    void Promise.all([loadNav(), loadList()]);
                  } catch (error) {
                    readerActionError(error, "Could not save that highlight");
                  }
                }}
                onFileArticle={async (destination, folderId) => {
                  const id = article.id;
                  try {
                    const next = await api.fileArticle(id, destination || null, folderId ?? null);
                    if (selectedIdRef.current !== id) return;
                    setArticle(next);
                    setItems((current) => current.map((item) => (item.id === next.id ? { ...item, ...next } : item)));
                    toast.success(
                      destination ? "Article filed on that shelf. It is not duplicated." : "Article removed from shelves.",
                    );
                    void Promise.all([loadNav(), loadList()]);
                  } catch (error) {
                    readerActionError(error, "Could not file that article");
                  }
                }}
                onMoveNote={async (noteId, destination, isCorrection, folderId) => {
                  const id = article.id;
                  try {
                    const next = await api.setNoteDestination(noteId, destination, isCorrection, folderId);
                    if (selectedIdRef.current !== id) return;
                    if (noteId === id) {
                      setArticle(next);
                    } else {
                      const parent = await api.article(id);
                      if (selectedIdRef.current !== id) return;
                      setArticle(parent);
                    }
                    toast.success("Note moved. It is not duplicated.");
                    void Promise.all([loadNav(), loadList()]);
                  } catch (error) {
                    readerActionError(error, "Could not move that note");
                  }
                }}
                onEditComposed={async (title, markdown, destination, isCorrection, folderId) => {
                  const id = article.id;
                  try {
                    const next = await api.updateComposedNote(id, title, markdown, destination, isCorrection, folderId);
                    if (selectedIdRef.current !== id) return;
                    setArticle(next);
                    setItems((current) => current.map((item) => (item.id === next.id ? { ...item, ...next } : item)));
                    toast.success("StoryKeep note updated");
                    void Promise.all([loadNav(), loadList()]);
                  } catch (error) {
                    readerActionError(error, "Could not update that note");
                  }
                }}
                onDownloadPack={async () => {
                  try {
                    await api.downloadObsidianPack();
                    toast.success("Obsidian pack downloaded");
                  } catch (error) {
                    readerActionError(error, "Could not download the Obsidian pack");
                  }
                }}
                onDeleteAnnotation={async (id) => {
                  const articleId = article.id;
                  try {
                    await api.deleteNote(id);
                    const next = await api.article(articleId);
                    if (selectedIdRef.current !== articleId) return;
                    setArticle(next);
                    void Promise.all([loadNav(), loadList()]);
                  } catch (error) {
                    readerActionError(error, "Could not remove that highlight");
                  }
                }}
                onOpenNote={openArticle}
                onCreateLinkedNote={async (title, shelf, folderId) => {
                  try {
                    const created = await api.composeVaultNote(
                      title,
                      "",
                      [],
                      shelf || "notes",
                      false,
                      folderId,
                    );
                    void Promise.all([loadNav(), loadList()]);
                    toast.success(`Created “${title}”`);
                    return created.id;
                  } catch (error) {
                    toast.error(error instanceof ApiError ? error.message : "Could not create that note");
                    return null;
                  }
                }}
              />
            ) : selectedId ? (
              <EmptyState icon={<LoaderCircle className="size-5 animate-spin" />} title="Opening article" body="Loading the stored text, not just the link." />
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
        rssShelves={rssShelves}
        activeRssShelfId={activeRssShelfId}
        categories={categories}
        folders={folders}
        customNoteShelves={customNoteShelves}
        onCreateFolder={createFolderOnShelf}
        onCreateNoteShelf={onCreateNoteShelf}
        onAddRssShelf={onAddRssShelf}
        onOpenChange={setAddOpen}
        onAdded={async () => {
          await Promise.all([loadNav(), loadList()]);
        }}
        onSavedPage={async (articleId) => {
          openArticle(articleId);
          setShelf({ kind: "saved" });
          await Promise.all([loadNav(), loadList()]);
        }}
        onCreatedNote={async (articleId, destination, folderId) => {
          openArticle(articleId);
          setShelf(shelfFromFilingDestination(destination, folderId));
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
      <DeleteArticleDialog
        item={articleToDelete}
        onOpenChange={(open) => {
          if (!open) setArticleToDelete(null);
        }}
        onConfirm={async (item) => {
          await deleteArticleItem(item);
          setArticleToDelete(null);
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
      <Dialog open={profileOpen} onOpenChange={(open) => (open ? setProfileOpen(true) : closeProfile())}>
        <DialogContent
          showCloseButton={false}
          className="!top-0 !left-0 !flex h-[100dvh] !max-h-none w-[100vw] !max-w-none !translate-x-0 !translate-y-0 flex-col overflow-hidden rounded-none border-0 bg-background p-0 shadow-none ring-0 sm:max-w-none"
        >
          <ProfilePage
            className="h-full min-h-0 flex-1"
            onClose={closeProfile}
            onUpdated={(updated) => onUserChange?.(updated)}
          />
        </DialogContent>
      </Dialog>
      <CalculatorOverlay ref={calculatorRef} userId={user.id} />
      <GrokBubble
        articleId={article?.id ?? null}
        articleTitle={article?.title ?? null}
        articleGuid={article?.guid ?? null}
        sourceRef={article?.source_ref ?? null}
        articleBody={article?.content_text ?? null}
        onStopArticleListen={() => listenRef.current?.stop()}
        onOpenArticle={(id) => {
          window.history.replaceState({}, "", `${window.location.pathname}${window.location.search}#article/${id}`);
          openArticle(id);
        }}
        onSavedNote={async (noteId, destination, folderId) => {
          await loadNav();
          const currentId = selectedIdRef.current;
          if (noteId && noteId !== currentId) {
            setShelf(shelfFromFilingDestination(destination || "notes", folderId));
            openArticle(noteId);
            return;
          }
          if (!currentId) return;
          const next = await api.article(currentId);
          if (selectedIdRef.current !== currentId) return;
          setArticle(next);
        }}
      />
    </div>
  );
}

function ShelfWithFolders({
  shelfId,
  label,
  icon,
  count,
  shelf,
  folders,
  onShelf,
  onCreateFolder,
  onRenameFolder,
  onDeleteFolder,
}: {
  shelfId: FilingDestination;
  label: string;
  icon: React.ReactNode;
  count?: number;
  shelf: Shelf;
  folders: Folder[];
  onShelf: (shelf: Shelf) => void;
  onCreateFolder: (shelf: FilingDestination) => Promise<string | null>;
  onRenameFolder: (folder: Folder) => void;
  onDeleteFolder: (folder: Folder) => void;
}) {
  const rows = foldersForShelf(folders, shelfId);
  const shelfActive =
    (shelf.kind === shelfId || (shelf.kind === "custom" && shelf.id === shelfId)) && !shelfFolderId(shelf);
  const openShelf = (folderId?: string) => onShelf(shelfFromFilingDestination(shelfId, folderId));
  return (
    <div className="mb-0.5">
      <div className="flex items-center gap-0.5">
        <NavButton active={shelfActive} onClick={() => openShelf()} icon={icon} count={count} className="flex-1">
          {label}
        </NavButton>
        <Button
          type="button"
          size="icon-xs"
          variant="ghost"
          className="shrink-0 text-sidebar-foreground/55 hover:text-sidebar-foreground"
          aria-label={`New ${label} folder`}
          onClick={() => void onCreateFolder(shelfId)}
        >
          <Plus className="size-3.5" />
        </Button>
      </div>
      {rows.map((folder) => (
        <div key={folder.id} className="group flex items-center gap-0.5 pl-3">
          <NavButton
            active={(shelf.kind === shelfId || (shelf.kind === "custom" && shelf.id === shelfId)) && shelfFolderId(shelf) === folder.id}
            onClick={() => openShelf(folder.id)}
            count={folder.item_count}
            className="flex-1 text-[0.92rem]"
          >
            {folder.name}
          </NavButton>
          <Button
            type="button"
            size="icon-xs"
            variant="ghost"
            className="shrink-0 text-sidebar-foreground/45 opacity-0 group-hover:opacity-100 hover:text-sidebar-foreground"
            aria-label={`Rename ${folder.name}`}
            onClick={() => onRenameFolder(folder)}
          >
            <NotebookPen className="size-3" />
          </Button>
          <Button
            type="button"
            size="icon-xs"
            variant="ghost"
            className="shrink-0 text-sidebar-foreground/45 opacity-0 group-hover:opacity-100 hover:text-destructive"
            aria-label={`Delete ${folder.name}`}
            onClick={() => onDeleteFolder(folder)}
          >
            <Trash2 className="size-3" />
          </Button>
        </div>
      ))}
    </div>
  );
}

function Sidebar({
  user,
  stats,
  shelf,
  rssShelves,
  activeRssShelfId,
  groupedFeeds,
  tags,
  folders,
  customNoteShelves,
  onShelf,
  onRssShelfChange,
  onAddRssShelf,
  onCreateFolder,
  onRenameFolder,
  onDeleteFolder,
  onAdd,
  onAddCategory,
  onAddFeed,
  onRenameCategory,
  onDeleteCategory,
  onChangeFeedCategory,
  onRemoveFeed,
  onManageTags,
  onBackup,
  onRefresh,
  refreshing,
  onLogout,
  onProfile,
  deployBuild,
}: {
  user: User;
  stats: Stats | null;
  shelf: Shelf;
  rssShelves: RssShelf[];
  activeRssShelfId: string | null;
  groupedFeeds: { groups: { category: Category; feeds: Feed[] }[] };
  tags: Tag[];
  folders: Folder[];
  customNoteShelves: CustomNoteShelf[];
  onShelf: (shelf: Shelf) => void;
  onRssShelfChange: (shelfId: string) => void;
  onAddRssShelf: () => void;
  onCreateFolder: (shelf: FilingDestination) => Promise<string | null>;
  onRenameFolder: (folder: Folder) => void;
  onDeleteFolder: (folder: Folder) => void;
  onAdd: () => void;
  onAddCategory: () => void;
  onAddFeed: () => void;
  onRenameCategory: (category: Category) => void;
  onDeleteCategory: (category: Category) => void;
  onChangeFeedCategory: (feed: Feed) => void;
  onRemoveFeed: (feed: Feed) => void;
  onManageTags: () => void;
  onBackup: () => void;
  onRefresh: () => void;
  refreshing: boolean;
  onLogout: () => void;
  onProfile: () => void;
  deployBuild: string | null;
}) {
  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden">
      <button
        type="button"
        onClick={onProfile}
        className="shrink-0 px-4 pt-5 pb-3 text-left hover:bg-sidebar-accent/40 rounded-none transition-colors"
      >
        <p className="font-[family-name:var(--font-serif)] text-2xl tracking-tight">Storykeep</p>
        <div className="mt-2 flex items-center gap-2">
          <UserAvatar
            mediaId={user.avatar_media_id}
            displayName={user.display_name}
            email={user.email}
            className="size-8 bg-sidebar-accent"
            initialsClassName="text-xs text-sidebar-foreground/80"
          />
          <p className="min-w-0 truncate text-xs text-sidebar-foreground/70">{user.display_name || user.email}</p>
        </div>
      </button>
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
        <ShelfWithFolders shelfId="vault" label="Vault" icon={<Library className="size-4" />} count={stats?.vault_count} shelf={shelf} folders={folders} onShelf={onShelf} onCreateFolder={onCreateFolder} onRenameFolder={onRenameFolder} onDeleteFolder={onDeleteFolder} />
        <ShelfWithFolders shelfId="additions" label="Additions" icon={<FilePlus className="size-4" />} count={stats?.additions_count} shelf={shelf} folders={folders} onShelf={onShelf} onCreateFolder={onCreateFolder} onRenameFolder={onRenameFolder} onDeleteFolder={onDeleteFolder} />
        <ShelfWithFolders shelfId="books" label="Books" icon={<BookOpen className="size-4" />} count={stats?.books_count} shelf={shelf} folders={folders} onShelf={onShelf} onCreateFolder={onCreateFolder} onRenameFolder={onRenameFolder} onDeleteFolder={onDeleteFolder} />
        <ShelfWithFolders shelfId="notes" label="Notes" icon={<NotebookPen className="size-4" />} count={stats?.annotation_count} shelf={shelf} folders={folders} onShelf={onShelf} onCreateFolder={onCreateFolder} onRenameFolder={onRenameFolder} onDeleteFolder={onDeleteFolder} />
        <ShelfWithFolders shelfId="schoolwork" label="Schoolwork" icon={<GraduationCap className="size-4" />} count={stats?.schoolwork_count} shelf={shelf} folders={folders} onShelf={onShelf} onCreateFolder={onCreateFolder} onRenameFolder={onRenameFolder} onDeleteFolder={onDeleteFolder} />
        {customNoteShelves.map((row) => (
          <ShelfWithFolders
            key={row.id}
            shelfId={row.id}
            label={row.name}
            icon={<Library className="size-4" />}
            shelf={shelf}
            folders={folders}
            onShelf={onShelf}
            onCreateFolder={onCreateFolder}
            onRenameFolder={onRenameFolder}
            onDeleteFolder={onDeleteFolder}
          />
        ))}
        <NavButton active={shelf.kind === "starred"} onClick={() => onShelf({ kind: "starred" })} icon={<Star className="size-4" />}>
          Starred
        </NavButton>
        <ShelfSwitcher
          shelf={shelf}
          rssShelves={rssShelves}
          activeRssShelfId={activeRssShelfId}
          groupedFeeds={groupedFeeds}
          onRssShelfChange={onRssShelfChange}
          onAddRssShelf={onAddRssShelf}
          onShelf={onShelf}
          onAddCategory={onAddCategory}
          onAddFeed={onAddFeed}
          onRenameCategory={onRenameCategory}
          onDeleteCategory={onDeleteCategory}
          onChangeFeedCategory={onChangeFeedCategory}
          onRemoveFeed={onRemoveFeed}
        />
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
        <Button type="button" variant="ghost" className="w-full justify-start text-sidebar-foreground" onClick={onProfile}>
          Profile
        </Button>
        <Button variant="ghost" className="w-full justify-start text-sidebar-foreground" onClick={onBackup}>
          Backup & export
        </Button>
        <Button variant="ghost" className="w-full justify-start text-sidebar-foreground/70" onClick={onLogout}>
          Sign out
        </Button>
        {deployBuild ? (
          <p className="px-2 pt-1 text-[0.65rem] text-sidebar-foreground/45" title="Deployed build">
            Build {deployBuild}
          </p>
        ) : null}
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
  className,
}: {
  children: React.ReactNode;
  onClick: () => void;
  active?: boolean;
  icon?: React.ReactNode;
  count?: number;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-left",
        active ? "bg-sidebar-accent text-sidebar-accent-foreground" : "hover:bg-sidebar-accent/60",
        className,
      )}
    >
      {icon}
      <span className="truncate flex-1">{children}</span>
      {count ? <span className="text-[11px] text-sidebar-foreground/55">{count}</span> : null}
    </button>
  );
}

function ArticleRow({
  listIndex,
  item,
  active,
  selected,
  onToggleSelect,
  onDelete,
  onClick,
}: {
  listIndex: number;
  item: ArticleListItem;
  active: boolean;
  selected: boolean;
  onToggleSelect: () => void;
  onDelete: () => void;
  onClick: () => void;
}) {
  const thumbUrl = articleHeroImageUrl(item.image_url, item.url);
  return (
    <div
      data-list-index={listIndex}
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
      <button
        type="button"
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          onClick();
        }}
        className="min-w-0 flex-1 cursor-pointer text-left"
      >
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
        <div className="mt-1 flex gap-3">
          {thumbUrl ? (
            <ArticleImage src={thumbUrl} className="size-14 shrink-0 rounded-md object-cover bg-muted" />
          ) : null}
          <div className="min-w-0 flex-1">
            <p className={cn("leading-snug", item.is_read ? "font-medium text-foreground" : "font-semibold text-foreground")}>{item.title}</p>
            <p className="mt-1 text-sm text-muted-foreground line-clamp-2">{stripHtml(item.summary)}</p>
          </div>
        </div>
      </button>
      <Button
        type="button"
        size="icon-sm"
        variant="ghost"
        className="mt-0.5 shrink-0 text-muted-foreground hover:text-destructive"
        aria-label={`Delete ${item.title}`}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          onDelete();
        }}
      >
        <Trash2 className="size-3.5" />
      </Button>
    </div>
  );
}

function Reader({
  article,
  tags,
  folders,
  customNoteShelves,
  onCreateNoteShelf,
  onCreateFolder,
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
  onUseFeedText,
  onArchive,
  onArchivePdf,
  onRestore,
  onTag,
  onNote,
  onHighlight,
  onDeleteAnnotation,
  onFileArticle,
  onMoveNote,
  onEditComposed,
  onDownloadPack,
  onOpenNote,
  onCreateLinkedNote,
  readerScrollToken,
}: {
  article: Article;
  tags: Tag[];
  folders: Folder[];
  customNoteShelves: CustomNoteShelf[];
  onCreateNoteShelf: () => Promise<string | null>;
  onCreateFolder: (shelf: FilingDestination) => Promise<string | null>;
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
  onUseFeedText: () => Promise<void>;
  onArchive: () => Promise<void>;
  onArchivePdf: () => Promise<void>;
  onRestore: (archiveId: string) => Promise<void>;
  readerScrollToken: number;
  onTag: (name: string) => Promise<void>;
  onNote: (title: string, markdown: string, destination: FilingDestination, isCorrection: boolean, folderId?: string | null) => Promise<void>;
  onHighlight: (payload: { quote: string; color: string; prefix: string; suffix: string; note?: string }) => Promise<void>;
  onDeleteAnnotation: (id: string) => Promise<void>;
  onFileArticle: (destination: FilingDestination | "", folderId?: string | null) => Promise<void>;
  onMoveNote: (noteId: string, destination: FilingDestination, isCorrection: boolean, folderId?: string | null) => Promise<void>;
  onEditComposed: (title: string, markdown: string, destination: FilingDestination, isCorrection: boolean, folderId?: string | null) => Promise<void>;
  onDownloadPack: () => Promise<void>;
  onOpenNote: (id: string) => void;
  onCreateLinkedNote: (title: string, shelf: FilingDestination | "", folderId: string | null) => Promise<string | null>;
}) {
  const [note, setNote] = useState("");
  const [noteTitle, setNoteTitle] = useState("");
  const [noteDest, setNoteDest] = useState<FilingDestination>("notes");
  const [noteFolder, setNoteFolder] = useState<string | null>(null);
  const [noteCorrection, setNoteCorrection] = useState(false);
  const [fileDest, setFileDest] = useState<FilingDestination | "">(displayArticleShelf(article));
  const [fileFolder, setFileFolder] = useState<string | null>(article.folder_id ?? null);
  const [editTitle, setEditTitle] = useState(article.title);
  const [editBody, setEditBody] = useState(article.content_text || "");
  const [editDest, setEditDest] = useState<FilingDestination>(
    asFilingDestination(article.destination, "additions") as FilingDestination,
  );
  const [editFolder, setEditFolder] = useState<string | null>(article.folder_id ?? null);
  const [editCorrection, setEditCorrection] = useState(Boolean(article.is_correction));

  async function handleCreateNoteShelfSelect(
    setDest: (next: FilingDestination) => void,
    setFolder: (next: string | null) => void,
    afterSelect?: (id: FilingDestination) => void,
  ) {
    const id = await onCreateNoteShelf();
    if (id) {
      setDest(id);
      setFolder(null);
      afterSelect?.(id);
    }
  }

  function handleNoteDestChange(next: FilingDestination | "") {
    if (!next) return;
    setNoteDest(next);
    setNoteFolder(null);
  }

  function handleEditDestChange(next: FilingDestination | "") {
    if (!next) return;
    setEditDest(next);
    setEditFolder(null);
  }

  async function handleCreateNoteFolder() {
    const created = await onCreateFolder(noteDest);
    if (created) setNoteFolder(created);
  }

  async function handleCreateEditFolder() {
    const created = await onCreateFolder(editDest);
    if (created) {
      setEditFolder(created);
      void moveComposedShelf(editDest, editCorrection, created);
    }
  }

  async function handleCreateFileFolder() {
    if (!fileDest) return;
    const created = await onCreateFolder(fileDest);
    if (created) void moveArticleFiling(fileDest, created);
  }

  async function moveArticleFiling(nextDest: FilingDestination | "", nextFolder: string | null = fileFolder) {
    const prevDest = fileDest;
    const prevFolder = fileFolder;
    setFileDest(nextDest);
    setFileFolder(nextFolder);
    try {
      await onFileArticle(nextDest, nextFolder);
    } catch {
      setFileDest(prevDest);
      setFileFolder(prevFolder);
    }
  }
  const [highlightNote, setHighlightNote] = useState("");
  const [findQuery, setFindQuery] = useState("");
  const [findIndex, setFindIndex] = useState(0);
  const [findCount, setFindCount] = useState(0);
  const [tag, setTag] = useState("");
  const [busy, setBusy] = useState(false);
  const [restoreOpen, setRestoreOpen] = useState(false);
  const [restoreRows, setRestoreRows] = useState<SnapshotRow[]>([]);
  const [restoreLoading, setRestoreLoading] = useState(false);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [pendingRestore, setPendingRestore] = useState<SnapshotRow | null>(null);
  const [activeWord, setActiveWord] = useState<number | null>(null);
  const articleRef = useRef<HTMLElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const noteRef = useRef<HTMLTextAreaElement>(null);
  const findRef = useRef<HTMLInputElement>(null);
  const findMarksRef = useRef<HTMLElement[]>([]);
  const clickedWordRef = useRef<number | null>(null);
  const [picker, setPicker] = useState<{ quote: string; prefix: string; suffix: string; top: number; left: number } | null>(
    null,
  );
  const bodyRef = useRef<HTMLDivElement>(null);
  const [pdfReady, setPdfReady] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [browserFs, setBrowserFs] = useState(false);
  const [htmlSnapshotError, setHtmlSnapshotError] = useState<string | null>(null);
  const composed = isStoryKeepNote(article);
  const pdfIntent = !composed && article.offline_view === "pdf";
  const pdfArchiveId = article.offline_archive_id ? String(article.offline_archive_id) : "";
  const pdfLocked = pdfIntent && pdfReady;

  useEffect(() => {
    setPdfReady(false);
    setPdfError(pdfIntent && !pdfArchiveId ? "This PDF restore is missing an archive id." : null);
    setHtmlSnapshotError(null);
  }, [article.id, pdfArchiveId, pdfIntent]);

  useEffect(() => {
    const onFs = () => setBrowserFs(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onFs);
    onFs();
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);
  const heroImage = composed ? null : articleHeroImageUrl(article.image_url, article.url);
  const html = composed ? composedNoteHtml(article) : articleReaderSource(article);
  const fallbackBody = composed
    ? composedNoteMarkdown(article)
    : article.content_text || stripHtml(article.summary) || "";
  const [bodyHtml, setBodyHtml] = useState(html || "");
  const [articleTextSize, setArticleTextSize] = useState<ArticleTextSize>("md");
  const [includeNotesInListen, setIncludeNotesInListen] = useState(false);
  const [followSpeech, setFollowSpeech] = useState(false);
  const followSpeechRef = useRef(false);
  const userPausedFollowRef = useRef(false);
  const programmaticScrollRef = useRef(false);
  const suggestions = tags
    .filter((item) => !article.tags.some((attached) => attached.id === item.id))
    .filter((item) => !tag.trim() || item.name.toLowerCase().includes(tag.trim().toLowerCase()))
    .slice(0, 8);
  const highlightKey = article.annotations
    .filter((item) => item.kind === "highlight")
    .map((item) => `${item.id}:${item.color}:${item.quote}`)
    .join("|");
  const highlights = article.annotations.filter((item) => item.kind === "highlight" && item.quote);
  const filedNotes = (article.filed_notes || []).filter((item) => !item.is_correction);
  const articleCorrection = article.corrections?.length
    ? article.corrections[article.corrections.length - 1]
    : null;
  const articleShelf = displayArticleShelf(article);
  const [wikilinkMap, setWikilinkMap] = useState<Map<string, WikilinkResolution>>(new Map());
  const wikilinkMarkdownSources = useMemo(() => {
    const sources = [fallbackBody, articleCorrection?.markdown || ""];
    for (const item of filedNotes) sources.push(item.markdown);
    return sources.filter(Boolean).join("\n");
  }, [fallbackBody, articleCorrection?.markdown, filedNotes]);

  useEffect(() => {
    const targets = extractWikilinkTargets(wikilinkMarkdownSources);
    if (!targets.length) {
      setWikilinkMap(new Map());
      return;
    }
    let cancelled = false;
    void api
      .resolveNoteTitles(targets, articleShelf || undefined, article.id)
      .then((payload) => {
        if (cancelled) return;
        const next = new Map<string, WikilinkResolution>();
        for (const item of payload.results) {
          if (item.id && item.title) next.set(item.query, { id: item.id, title: item.title });
        }
        setWikilinkMap(next);
      })
      .catch(() => {
        if (!cancelled) setWikilinkMap(new Map());
      });
    return () => {
      cancelled = true;
    };
  }, [article.id, articleShelf, wikilinkMarkdownSources]);

  const wikilinkResolver = useCallback(
    (target: string) => wikilinkMap.get(target.trim()) ?? null,
    [wikilinkMap],
  );

  const wikilinkClickContext = useMemo(
    () => ({
      shelf: articleShelf || null,
      folderId: article.folder_id ?? null,
      onOpenNote,
      onCreateNote: (title: string, shelf: string | null, folderId: string | null) =>
        onCreateLinkedNote(title, (shelf || "notes") as FilingDestination, folderId),
      resolveTitle: (title: string, shelf: string | null) =>
        api.resolveNoteTitle(title, shelf || undefined, article.id).then((item) => item || null),
    }),
    [article.id, article.folder_id, articleShelf, onCreateLinkedNote, onOpenNote],
  );

  const handleReaderBodyClick = useCallback(
    (event: React.MouseEvent<HTMLElement>) => onReaderBodyClick(event, wikilinkClickContext),
    [wikilinkClickContext],
  );

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
    if (composed && fallbackBody) {
      setBodyHtml(applyHighlights(sanitizeHtml(noteMarkdownHtml(fallbackBody, wikilinkResolver)), marks));
      return;
    }
    if (html) {
      setBodyHtml(applyHighlights(html, marks));
      return;
    }
    if (fallbackBody) {
      const escaped = fallbackBody
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/\n/g, "<br/>");
      setBodyHtml(applyHighlights(`<p>${escaped}</p>`, marks));
      return;
    }
    setBodyHtml("");
  }, [article.id, composed, fallbackBody, html, highlightKey, wikilinkResolver]);

  useEffect(() => {
    setActiveWord(null);
    clickedWordRef.current = null;
    if (!isStoryKeepNote(article) && article.corrections?.length) {
      const latest = article.corrections[article.corrections.length - 1];
      setNote(latest?.markdown || "");
      setNoteTitle("Correction");
      setNoteCorrection(true);
    } else {
      setNote("");
      setNoteTitle("");
      setNoteCorrection(false);
    }
    setNoteDest("notes");
    setNoteFolder(null);
    setTag("");
    setEditTitle(article.title);
    setEditBody(composedNoteMarkdown(article) || article.content_text || "");
    setEditDest(asFilingDestination(article.destination, "additions") as FilingDestination);
    setEditFolder(article.folder_id ?? null);
    setEditCorrection(Boolean(article.is_correction));
    setFileDest(displayArticleShelf(article));
    setFileFolder(article.folder_id ?? null);
    setHighlightNote("");
    setFindQuery("");
    setFindIndex(0);
    setFindCount(0);
    findMarksRef.current = [];
  }, [article.id]);

  useEffect(() => {
    setEditDest(asFilingDestination(article.destination, "additions") as FilingDestination);
    setEditFolder(article.folder_id ?? null);
    setEditCorrection(Boolean(article.is_correction));
    setFileDest(displayArticleShelf(article));
    setFileFolder(article.folder_id ?? null);
  }, [article.destination, article.folder_id, article.is_correction, article.source_kind]);

  useEffect(() => {
    const root = bodyRef.current;
    if (!root) return;
    if (pdfLocked) return;
    try {
      root.innerHTML = bodyHtml;
    } catch {
      root.replaceChildren();
      const notice = document.createElement("p");
      notice.className = "text-sm text-destructive";
      notice.textContent = "Could not render this HTML snapshot. The live article was kept.";
      root.append(notice);
      return;
    }
    root.querySelectorAll("img").forEach((node) => {
      const img = node as HTMLImageElement;
      img.addEventListener("error", () => {
        const alt = (img.getAttribute("alt") || "Image unavailable").trim();
        const fallback = document.createElement("span");
        fallback.className = "article-img-fallback";
        fallback.textContent = alt;
        img.replaceWith(fallback);
      });
    });
    if (bodyHtml) {
      wrapVisibleSpeechNodes(root, { skipTitle: article.title, skipAuthor: article.author });
    }
    if (!findQuery.trim()) {
      findMarksRef.current = [];
      setFindCount(0);
      return;
    }
    findMarksRef.current = findMarksInArticle(root, findQuery);
    setFindCount(findMarksRef.current.length);
    if (findMarksRef.current.length) {
      focusFindMark(findMarksRef.current, findIndex);
    }
  }, [article.author, article.title, bodyHtml, findQuery, article.id, pdfLocked]);

  useEffect(() => {
    if (!findMarksRef.current.length) return;
    focusFindMark(findMarksRef.current, findIndex);
  }, [findIndex]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing = Boolean(target?.closest("input, textarea, select, [contenteditable='true']"));
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "f") {
        if (typing || !bodyHtml) return;
        event.preventDefault();
        findRef.current?.focus();
        findRef.current?.select();
        return;
      }
      if (event.key === "Escape" && findQuery.trim()) {
        event.preventDefault();
        setFindQuery("");
        setFindIndex(0);
        const root = bodyRef.current;
        if (root) clearFindMarks(root);
        findMarksRef.current = [];
        setFindCount(0);
        if (target === findRef.current) findRef.current?.blur();
        return;
      }
      if (target !== findRef.current) return;
      if (event.key === "Enter" && findCount > 0) {
        event.preventDefault();
        setFindIndex((current) => current + (event.shiftKey ? -1 : 1));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [bodyHtml, findCount, findQuery]);

  useEffect(() => {
    noteFocusRef.current = () => noteRef.current?.focus();
    caretWordRef.current = () => wordIndexFromSelection(bodyRef.current) ?? clickedWordRef.current;
    return () => {
      noteFocusRef.current = null;
      caretWordRef.current = null;
    };
  }, [caretWordRef, noteFocusRef]);

  useEffect(() => {
    setArticleTextSize(readArticleTextSize());
    try {
      setIncludeNotesInListen(window.localStorage.getItem("storykeep-tts-include-notes") === "1");
      setFollowSpeech(window.localStorage.getItem("storykeep-tts-follow-speech") === "1");
    } catch {
      setIncludeNotesInListen(false);
      setFollowSpeech(false);
    }
  }, []);

  useEffect(() => {
    followSpeechRef.current = followSpeech;
  }, [followSpeech]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 0 });
  }, [readerScrollToken]);

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
      if (!programmaticScrollRef.current && listenRef.current?.isActive()) {
        userPausedFollowRef.current = true;
      }
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.cancelAnimationFrame(frame);
      el.removeEventListener("scroll", onScroll);
      window.localStorage.setItem(key, String(el.scrollTop));
    };
  }, [article.id]);

  async function moveComposedShelf(nextDest: FilingDestination, nextCorrection: boolean, nextFolder: string | null = editFolder) {
    const prevDest = editDest;
    const prevCorrection = editCorrection;
    const prevFolder = editFolder;
    setEditDest(nextDest);
    setEditCorrection(nextCorrection);
    setEditFolder(nextFolder);
    try {
      await onMoveNote(article.id, nextDest, nextCorrection, nextFolder);
    } catch {
      setEditDest(prevDest);
      setEditCorrection(prevCorrection);
      setEditFolder(prevFolder);
    }
  }

  useEffect(() => {
    const root = articleRef.current;
    if (!root) return;
    root.querySelectorAll(".tts-word-active").forEach((node) => node.classList.remove("tts-word-active"));
    if (activeWord == null) return;
    const current = root.querySelector(`[data-tts-word="${activeWord}"]`);
    if (!(current instanceof HTMLElement)) return;
    current.classList.add("tts-word-active");
    if (!followSpeechRef.current || userPausedFollowRef.current) return;
    const holder = scrollRef.current;
    if (!holder) return;
    const wordBox = current.getBoundingClientRect();
    const holdBox = holder.getBoundingClientRect();
    const margin = 72;
    if (wordBox.top >= holdBox.top + margin && wordBox.bottom <= holdBox.bottom - margin) return;
    programmaticScrollRef.current = true;
    if (wordBox.top < holdBox.top + margin) {
      holder.scrollTop += wordBox.top - holdBox.top - margin;
    } else if (wordBox.bottom > holdBox.bottom - margin) {
      holder.scrollTop += wordBox.bottom - holdBox.bottom + margin;
    }
    window.requestAnimationFrame(() => {
      programmaticScrollRef.current = false;
    });
  }, [activeWord]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (!listenRef.current?.isActive()) return;
      event.preventDefault();
      event.stopPropagation();
      listenRef.current.stop();
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [listenRef]);

  const getVisibleSpeech = useCallback((): VisibleSpeechPayload | null => {
    if (!bodyRef.current) return null;
    const noteRoots = includeNotesInListen
      ? (Array.from(articleRef.current?.querySelectorAll(".tts-spoken-note") ?? []) as HTMLElement[])
      : [];
    const { script, visibleWordCount } = buildVisibleSpeechScript(bodyRef.current, {
      skipTitle: article.title,
      skipAuthor: article.author,
      noteRoots,
      includeNotes: includeNotesInListen,
    });
    if (!script.trim()) return null;
    return { script, visibleWordCount };
  }, [article.author, article.title, includeNotesInListen]);

  return (
    <div className="reader-shell">
      <div className="reader-chrome sticky top-0 z-30 border-b border-border bg-[var(--storykeep-top-bar)] px-5 py-2">
        <ListenControls
          ref={listenRef}
          articleId={article.id}
          hasText={Boolean(bodyHtml)}
          includeNotes={includeNotesInListen}
          noteMode={composed}
          onCue={setActiveWord}
          onFollowUnavailable={() => {
            setFollowSpeech(false);
            try {
              window.localStorage.setItem("storykeep-tts-follow-speech", "0");
            } catch {
              /* ignore */
            }
          }}
          getCaretWord={() => wordIndexFromSelection(bodyRef.current) ?? clickedWordRef.current}
          getVisibleSpeech={getVisibleSpeech}
          getVisibleSections={() => visibleSpeechSections(bodyRef.current)}
        />
        {!pdfIntent ? (
          <SchoolToolsBar
            source={{ articleId: article.id }}
            dest={asFilingDestination(article.destination, "schoolwork")}
            folderId={article.folder_id}
            persist={false}
            onSavedNote={(noteId) => onOpenNote(noteId)}
          />
        ) : null}
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
          {pdfIntent ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => void toggleBrowserFullscreen(".pdf-host, .reader-shell")}
            >
              {browserFs ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
              {browserFs ? "Exit" : "Fullscreen"}
            </Button>
          ) : null}
          {!composed && filedNotes.length > 0 ? (
            <label className="flex items-start gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={includeNotesInListen}
                onChange={(event) => {
                  const next = event.target.checked;
                  setIncludeNotesInListen(next);
                  try {
                    window.localStorage.setItem("storykeep-tts-include-notes", next ? "1" : "0");
                  } catch {
                    /* ignore */
                  }
                }}
              />
              <span>
                Include my notes
                <span className="block text-[11px]">
                  Off by default so Listen does not speak overlay notes unless you ask.
                </span>
              </span>
            </label>
          ) : null}
          <label className="flex items-start gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={followSpeech}
              onChange={(event) => {
                const next = event.target.checked;
                setFollowSpeech(next);
                if (next) userPausedFollowRef.current = false;
                try {
                  window.localStorage.setItem("storykeep-tts-follow-speech", next ? "1" : "0");
                } catch {
                  /* ignore */
                }
              }}
            />
            <span>
              Follow speech
              <span className="block text-[11px]">
                Off by default. When on, scroll chases the spoken word until you scroll by hand.
              </span>
            </span>
          </label>
        </div>
      </div>
      <div
        ref={scrollRef}
        className={cn(
          "min-h-0 flex-1 overflow-y-auto overscroll-contain",
          !pdfIntent && "article-scrollport",
        )}
      >
      <article
        ref={articleRef}
        className={cn("mx-auto px-5 py-6", readerFull ? "max-w-4xl" : "max-w-3xl")}
      >
        <div>
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <Button variant="ghost" className="lg:hidden -ml-2" onClick={onBack}>
            Back to list
          </Button>
          {browserFs || (readerFull && !pdfIntent) ? (
            <Button
              variant="outline"
              size="sm"
              className="hidden lg:inline-flex"
              onClick={() => {
                if (pdfIntent) void toggleBrowserFullscreen(".pdf-host, .reader-shell");
                else onToggleFull();
              }}
            >
              <Minimize2 className="size-3.5" />
              Exit
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              className="hidden lg:inline-flex"
              onClick={() => {
                if (pdfIntent) void toggleBrowserFullscreen(".pdf-host, .reader-shell");
                else onToggleFull();
              }}
            >
              <Maximize2 className="size-3.5" />
              Fullscreen
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
        <h1 className="font-[family-name:var(--font-serif)] text-3xl md:text-4xl leading-tight mt-2">{article.title}</h1>
        {article.author ? <p className="mt-2 text-sm text-muted-foreground">{article.author}</p> : null}
        {heroImage ? (
          <ArticleImage eager src={heroImage} className="article-hero mt-4 max-w-full rounded-lg" />
        ) : null}
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
          {article.has_feed_text || article.source_kind === "rss" ? (
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => {
                setBusy(true);
                void onUseFeedText().finally(() => setBusy(false));
              }}
            >
              Use feed text
            </Button>
          ) : null}
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => {
              setBusy(true);
              setHtmlSnapshotError(null);
              void onArchive()
                .catch((error) => {
                  setHtmlSnapshotError(
                    error instanceof Error ? error.message : "Could not store a snapshot. The live article was kept.",
                  );
                })
                .finally(() => setBusy(false));
            }}
          >
            Snapshot
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => {
              setBusy(true);
              void onArchivePdf().finally(() => setBusy(false));
            }}
          >
            PDF snapshot
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => {
              setPendingRestore(null);
              setRestoreError(null);
              setRestoreOpen(true);
              setRestoreLoading(true);
              void api
                .archives(article.id)
                .then((rows) => {
                  setRestoreRows(rows);
                })
                .catch((error) => {
                  setRestoreRows([]);
                  setRestoreError(error instanceof ApiError ? error.message : "Could not load snapshots");
                })
                .finally(() => setRestoreLoading(false));
            }}
          >
            <History className="size-3.5" />
            Restore…
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => void onDownloadPack()}
          >
            Obsidian overlay pack
          </Button>
          <ArticleShareMenu article={{ id: article.id, title: article.title, url: article.url }} />
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
        {!composed && !isVaultImport(article) ? (
          <div className="mt-4 flex flex-wrap items-center gap-2 rounded-md border bg-muted/20 px-3 py-2">
            <span className="text-xs font-medium text-muted-foreground">Shelf</span>
            <DestinationSelect
              allowEmpty
              value={fileDest}
              customShelves={customNoteShelves}
              onCreateShelf={() =>
                void handleCreateNoteShelfSelect(setFileDest, setFileFolder, (id) => void moveArticleFiling(id, null))
              }
              onChange={(next) => {
                if (next) setFileDest(next);
                else setFileDest("");
                setFileFolder(null);
                void moveArticleFiling(next, null);
              }}
            />
            <span className="text-xs font-medium text-muted-foreground">Folder</span>
            <FolderSelect
              shelf={fileDest || "notes"}
              folders={folders}
              value={fileFolder}
              disabled={!fileDest}
              onChange={(next) => void moveArticleFiling(fileDest, next)}
              onCreateFolder={() => void handleCreateFileFolder()}
            />
            <p className="w-full text-[11px] text-muted-foreground">
              Filing moves this article to that sidebar shelf in StoryKeep only. Steve&apos;s Surface Vault is never overwritten.
            </p>
          </div>
        ) : null}
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
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex min-w-[12rem] flex-1 max-w-lg items-center gap-1.5">
              <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <Input
                ref={findRef}
                value={findQuery}
                onChange={(event) => {
                  setFindQuery(event.target.value);
                  setFindIndex(0);
                }}
                placeholder="Find in article…"
                aria-label="Find in article"
                className="h-8"
                autoComplete="off"
                spellCheck={false}
              />
              <span className="w-11 shrink-0 text-center text-[11px] tabular-nums text-muted-foreground">
                {findQuery.trim()
                  ? findCount
                    ? `${(((findIndex % findCount) + findCount) % findCount) + 1}/${findCount}`
                    : "0"
                  : ""}
              </span>
              <Button
                type="button"
                size="icon-sm"
                variant="outline"
                disabled={!findCount}
                aria-label="Previous match"
                onClick={() => setFindIndex((current) => current - 1)}
              >
                <ChevronUp className="size-3.5" />
              </Button>
              <Button
                type="button"
                size="icon-sm"
                variant="outline"
                disabled={!findCount}
                aria-label="Next match"
                onClick={() => setFindIndex((current) => current + 1)}
              >
                <ChevronDown className="size-3.5" />
              </Button>
            </div>
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
        ) : null}
        </div>
        {composed ? <NoteAttachmentChips markdown={composedNoteMarkdown(article)} className="mb-4" /> : null}
        {htmlSnapshotError && !pdfIntent ? (
          <p className="border-b bg-destructive/10 px-0 py-2 text-sm text-destructive">{htmlSnapshotError}</p>
        ) : null}
        {article.offline_view === "html" && !pdfIntent ? (
          <p className="border-b bg-muted/30 px-0 py-2 text-xs text-muted-foreground">
            Offline view is this HTML snapshot.
          </p>
        ) : null}
        {pdfIntent ? (
          <>
            <p className="reader-chrome border-b bg-muted/30 px-0 py-2 text-xs text-muted-foreground">
              Offline view is this PDF snapshot. The article text was not replaced.
            </p>
            {pdfError && !pdfArchiveId ? (
              <p className="reader-chrome px-0 py-2 text-sm text-destructive">{pdfError}</p>
            ) : null}
            {pdfArchiveId ? (
              <PdfRestoreBoundary
                key={pdfArchiveId}
                onError={(message) => {
                  setPdfReady(false);
                  setPdfError(message);
                }}
              >
                <PdfSnapshotViewer
                  archiveId={pdfArchiveId}
                  onReady={() => {
                    setPdfReady(true);
                    setPdfError(null);
                  }}
                  onFailed={(message) => {
                    setPdfReady(false);
                    setPdfError(message);
                  }}
                />
              </PdfRestoreBoundary>
            ) : null}
          </>
        ) : null}
        {!pdfLocked && bodyHtml ? (
          <div
            ref={bodyRef}
            className={cn("article-body", composed && "note-md", articleTextSizeClass(articleTextSize))}
            onClick={(event) => {
              handleReaderBodyClick(event);
              const word = (event.target as HTMLElement).closest("[data-tts-word]");
              if (word instanceof HTMLElement) {
                const index = Number(word.dataset.ttsWord);
                if (Number.isFinite(index)) {
                  clickedWordRef.current = index;
                  setActiveWord(index);
                }
              }
            }}
            onMouseUp={() => {
              const next = selectionInRoot(bodyRef.current);
              setPicker(next);
            }}
          />
        ) : null}
        {!pdfLocked && !bodyHtml ? (
          <EmptyState
            title="Only the feed snippet is stored"
            body="The original page has not been extracted yet. Use Re-extract to pull the full article, or Snapshot to keep a copy."
          />
        ) : null}
        {!pdfLocked ? (
          <>
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
          {articleCorrection ? (
            <div className="rounded-lg border bg-muted/25 px-3 py-2 space-y-2">
              <p className="text-sm font-medium">Correction on this article</p>
              <div
                className="note-md text-sm"
                onClick={handleReaderBodyClick}
                dangerouslySetInnerHTML={{
                  __html: sanitizeHtml(noteMarkdownHtml(articleCorrection.markdown, wikilinkResolver)),
                }}
              />
            </div>
          ) : null}
          {isStoryKeepNote(article) ? null : (
          <form
            className="space-y-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (!note.trim()) return;
              const title = noteCorrection
                ? "Correction"
                : noteTitle.trim() || note.trim().split("\n")[0]?.slice(0, 80) || "Note";
              void onNote(title, note.trim(), noteDest, noteCorrection, noteFolder).then(() => {
                if (!noteCorrection) {
                  setNote("");
                  setNoteTitle("");
                }
                setNoteCorrection(noteCorrection);
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
                  <DestinationSelect
                    value={noteDest}
                    onChange={handleNoteDestChange}
                    customShelves={customNoteShelves}
                    onCreateShelf={() => void handleCreateNoteShelfSelect(setNoteDest, setNoteFolder)}
                  />
                  <FolderSelect
                    shelf={noteDest}
                    folders={folders}
                    value={noteFolder}
                    onChange={setNoteFolder}
                    onCreateFolder={() => void handleCreateNoteFolder()}
                  />
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
              className="flex max-h-[min(70vh,40rem)] min-h-0 flex-col overflow-hidden rounded-md border p-3"
              onSubmit={(event) => {
                event.preventDefault();
                if (!editTitle.trim() || !editBody.trim()) return;
                void onEditComposed(editTitle.trim(), editBody.trim(), editDest, editCorrection, editFolder);
              }}
            >
              <NoteComposer
                value={editBody}
                onChange={setEditBody}
                placeholder="Full note, with ==highlights== and images…"
                rows={10}
                fill
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
                      customShelves={customNoteShelves}
                      onCreateShelf={() =>
                        void handleCreateNoteShelfSelect(setEditDest, setEditFolder, (id) =>
                          void moveComposedShelf(id, editCorrection, null),
                        )
                      }
                      onChange={(next) => {
                        if (!next) return;
                        setEditDest(next);
                        setEditFolder(null);
                        void moveComposedShelf(next, editCorrection, null);
                      }}
                    />
                    <FolderSelect
                      shelf={editDest}
                      folders={folders}
                      value={editFolder}
                      onChange={(next) => void moveComposedShelf(editDest, editCorrection, next)}
                      onCreateFolder={() => void handleCreateEditFolder()}
                    />
                    <CorrectionCheck
                      checked={editCorrection}
                      onChange={(next) => {
                        void moveComposedShelf(editDest, next, editFolder);
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
                      value={(item.destination as FilingDestination | null) || "notes"}
                      customShelves={customNoteShelves}
                      onCreateShelf={() =>
                        void onCreateNoteShelf().then((id) => {
                          if (id) void onMoveNote(item.id, id, Boolean(item.is_correction), null);
                        })
                      }
                      onChange={(next) => {
                        if (!next) return;
                        void onMoveNote(item.id, next, Boolean(item.is_correction), null);
                      }}
                    />
                    <FolderSelect
                      shelf={(item.destination as FilingDestination | null) || "notes"}
                      folders={folders}
                      value={item.folder_id ?? null}
                      onChange={(next) =>
                        void onMoveNote(
                          item.id,
                          (item.destination as FilingDestination | null) || "notes",
                          Boolean(item.is_correction),
                          next,
                        )
                      }
                      onCreateFolder={async () => {
                        const shelf = (item.destination as FilingDestination | null) || "notes";
                        const created = await onCreateFolder(shelf);
                        if (created) {
                          void onMoveNote(item.id, shelf, Boolean(item.is_correction), created);
                        }
                      }}
                    />
                    <CorrectionCheck
                      checked={Boolean(item.is_correction)}
                      onChange={(next) =>
                        void onMoveNote(
                          item.id,
                          (item.destination as FilingDestination | null) || "notes",
                          next,
                          item.folder_id ?? null,
                        )
                      }
                    />
                  </div>
                  <NoteAttachmentChips markdown={item.markdown} className="mt-2 mb-2" />
                  <div
                    className="text-sm mt-1 note-md tts-spoken-note"
                    onClick={handleReaderBodyClick}
                    dangerouslySetInnerHTML={{ __html: sanitizeHtml(noteMarkdownHtml(item.markdown, wikilinkResolver)) }}
                  />
                  {item.markdown.trim() ? (
                    <div className="mt-2">
                      <ListenControls
                        articleId={item.id}
                        hasText
                        noteMode
                      />
                    </div>
                  ) : null}
                  <p className="text-[11px] text-muted-foreground mt-1">{formatRelative(item.updated_at || item.created_at)}</p>
                </li>
              ))}
            </ul>
          )}
          {article.archives.length > 0 ? (
            <div className="space-y-1 text-xs text-muted-foreground">
              <p>
                {article.archives.length} snapshot{article.archives.length === 1 ? "" : "s"} stored if the original link
                dies.
              </p>
              {article.archives
                .filter((row) => row.archive_type === "pdf" && row.download_url)
                .map((row) => (
                  <p key={row.id}>
                    <a className="text-primary underline" href={row.download_url || undefined}>
                      Download PDF snapshot
                    </a>
                  </p>
                ))}
            </div>
          ) : null}
        </section>
          </>
        ) : null}
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
                  })
                    .then(() => {
                      setPicker(null);
                      setHighlightNote("");
                      window.getSelection()?.removeAllRanges();
                    })
                    .catch(() => {
                      /* parent shows the error toast */
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
      <Dialog
        open={restoreOpen}
        onOpenChange={(open) => {
          setRestoreOpen(open);
          if (!open) {
            setPendingRestore(null);
            setRestoreError(null);
          }
        }}
      >
        <DialogContent className="sm:max-w-md" showCloseButton>
          {pendingRestore ? (
            <>
              <DialogHeader>
                <DialogTitle>
                  Restore {snapshotKind(pendingRestore) === "pdf" ? "PDF" : "HTML"} snapshot?
                </DialogTitle>
                <DialogDescription>
                  {snapshotKind(pendingRestore) === "pdf"
                    ? "The article text is kept. This PDF becomes the offline view."
                    : "This replaces the article text with the snapshot. Your current text is saved as a new HTML snapshot first."}
                </DialogDescription>
              </DialogHeader>
              <p className="text-sm text-muted-foreground">
                {snapshotKind(pendingRestore) === "pdf" ? "PDF" : "HTML"} · {snapshotStamp(pendingRestore.created_at)}
              </p>
              <DialogFooter>
                <Button variant="outline" disabled={busy} onClick={() => setPendingRestore(null)}>
                  Back
                </Button>
                <Button
                  disabled={busy}
                  onClick={() => {
                    const row = pendingRestore;
                    setBusy(true);
                    void onRestore(row.id)
                      .then(() => {
                        setRestoreOpen(false);
                        setPendingRestore(null);
                        setHtmlSnapshotError(null);
                      })
                      .catch((error) => {
                        if (snapshotKind(row) !== "pdf") {
                          setHtmlSnapshotError(
                            error instanceof Error
                              ? error.message
                              : "Could not restore that HTML snapshot. The live article was kept.",
                          );
                        }
                      })
                      .finally(() => setBusy(false));
                  }}
                >
                  Restore
                </Button>
              </DialogFooter>
            </>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle>Restore a snapshot</DialogTitle>
                <DialogDescription>Choose an HTML or PDF snapshot to use as the offline view.</DialogDescription>
              </DialogHeader>
              {restoreLoading ? (
                <p className="text-sm text-muted-foreground">Loading snapshots…</p>
              ) : restoreError ? (
                <p className="text-sm text-destructive">{restoreError}</p>
              ) : restoreRows.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No snapshots yet. Take an HTML or PDF snapshot first.
                </p>
              ) : (
                <ul className="max-h-72 space-y-1 overflow-y-auto">
                  {restoreRows.map((row) => (
                    <li key={row.id}>
                      <button
                        type="button"
                        className="w-full rounded-md px-3 py-2 text-left text-sm hover:bg-accent"
                        onClick={() => setPendingRestore(row)}
                      >
                        {snapshotKind(row) === "pdf" ? "PDF" : "HTML"} · {snapshotStamp(row.created_at)}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <DialogFooter>
                <Button variant="outline" onClick={() => setRestoreOpen(false)}>
                  Cancel
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
      </div>
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

function DeleteArticleDialog({
  item,
  onOpenChange,
  onConfirm,
}: {
  item: ArticleListItem | null;
  onOpenChange: (open: boolean) => void;
  onConfirm: (item: ArticleListItem) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);

  return (
    <Dialog open={Boolean(item)} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete this from StoryKeep?</DialogTitle>
          <DialogDescription>
            {item
              ? `"${item.title}" will be removed from your library shelves. Steve's Surface Vault originals are never changed.`
              : "This item will be removed from your library shelves."}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Keep
          </Button>
          <Button
            variant="destructive"
            disabled={busy}
            onClick={async () => {
              if (!item) return;
              setBusy(true);
              try {
                await onConfirm(item);
              } finally {
                setBusy(false);
              }
            }}
          >
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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
  const [needsForce, setNeedsForce] = useState(false);

  useEffect(() => {
    setForce(false);
    setNeedsForce(Boolean(feed && (feed.saved_count ?? 0) > 0));
  }, [feed?.id, feed?.saved_count]);

  return (
    <Dialog open={Boolean(feed)} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Remove this feed?</DialogTitle>
          <DialogDescription>Unread items go away. Saved/shelved items stay.</DialogDescription>
        </DialogHeader>
        {needsForce ? (
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={force}
              onChange={(event) => setForce(event.target.checked)}
            />
            <span>Force: keep saved/shelved items and remove the feed</span>
          </label>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Keep feed
          </Button>
          <Button
            variant="destructive"
            disabled={busy || (needsForce && !force)}
            onClick={async () => {
              if (!feed) return;
              setBusy(true);
              try {
                await onConfirm(feed, force);
              } catch (error) {
                if (error instanceof ApiError && error.status === 409) {
                  setNeedsForce(true);
                  setForce(false);
                  toast.error("This feed has saved articles. Check Force to keep them and remove the feed.");
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
  rssShelves,
  activeRssShelfId,
  categories,
  folders,
  customNoteShelves,
  onCreateFolder,
  onCreateNoteShelf,
  onAddRssShelf,
  onAdded,
  onSavedPage,
  onCreatedNote,
  onImportedVault,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  rssShelves: RssShelf[];
  activeRssShelfId: string | null;
  categories: Category[];
  folders: Folder[];
  customNoteShelves: CustomNoteShelf[];
  onCreateFolder: (shelf: FilingDestination) => Promise<string | null>;
  onCreateNoteShelf: () => Promise<string | null>;
  onAddRssShelf: () => Promise<string | null>;
  onAdded: () => Promise<void>;
  onSavedPage: (articleId: string) => Promise<void>;
  onCreatedNote: (articleId: string, destination: FilingDestination, folderId?: string | null) => Promise<void>;
  onImportedVault: () => Promise<void>;
}) {
  const [tab, setTab] = useState<"feed" | "page" | "opml" | "vault" | "file">("feed");
  const [url, setUrl] = useState("");
  const [pageUrl, setPageUrl] = useState("");
  const [rssShelfId, setRssShelfId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [busy, setBusy] = useState(false);
  const [candidates, setCandidates] = useState<{ url: string; title: string | null }[]>([]);
  const [additionTitle, setAdditionTitle] = useState("");
  const [additionSubject, setAdditionSubject] = useState("");
  const [additionBody, setAdditionBody] = useState("");
  const [composeDest, setComposeDest] = useState<FilingDestination>("vault");
  const [composeFolder, setComposeFolder] = useState<string | null>(null);
  const [composeCorrection, setComposeCorrection] = useState(false);

  function handleComposeDestChange(next: FilingDestination | "") {
    if (!next) return;
    setComposeDest(next);
    setComposeFolder(null);
  }

  async function handleComposeCreateFolder() {
    const created = await onCreateFolder(composeDest);
    if (created) setComposeFolder(created);
  }

  async function handleCreateComposeShelf() {
    const id = await onCreateNoteShelf();
    if (id) {
      setComposeDest(id);
      setComposeFolder(null);
    }
  }

  async function handleCreateFeedShelf() {
    const id = await onAddRssShelf();
    if (id) {
      setRssShelfId(id);
      setCategoryId("");
    }
  }
  const [composeFull, setComposeFull] = useState(false);
  const composeMove = useMovableWindow({
    storageKey: COMPOSE_POS_KEY,
    open: open && !composeFull,
    defaultMode: "center",
    estimatedSize: { w: 640, h: 560 },
  });
  const [fileTitle, setFileTitle] = useState("");
  const [fileTags, setFileTags] = useState("");
  const bookmarklet =
    typeof window === "undefined"
      ? ""
      : `javascript:void(location='${window.location.origin}/?save='+encodeURIComponent(location.href))`;

  useEffect(() => {
    if (!open) return;
    setRssShelfId(activeRssShelfId || rssShelves[0]?.id || "");
  }, [activeRssShelfId, open, rssShelves]);

  const shelfCategories = categories.filter((row) => row.shelf_id === rssShelfId);

  async function createCategoryInline() {
    const name = window.prompt("New category name:")?.trim();
    if (!name || !rssShelfId) return null;
    const row = await api.createCategory(name, rssShelfId);
    setCategoryId(row.id);
    return row.id;
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setComposeFull(false);
        onOpenChange(next);
      }}
    >
      <DialogContent
        data-movable-window=""
        style={composeFull ? undefined : { left: composeMove.pos.x, top: composeMove.pos.y }}
        className={cn(
          "max-h-[90vh]",
          tab === "vault" && !composeFull
            ? "!flex h-[min(90vh,52rem)] w-[min(96vw,72rem)] sm:max-w-6xl flex-col overflow-hidden"
            : tab !== "vault"
              ? "overflow-y-auto"
              : "",
          !composeFull && "!top-0 !left-0 !translate-x-0 !translate-y-0 duration-0",
          composeFull &&
            "!top-0 !left-0 !flex h-[100dvh] !max-h-none w-[100vw] !max-w-none sm:!max-w-none !translate-x-0 !translate-y-0 flex-col overflow-hidden rounded-none p-3",
        )}
      >
        {composeFull ? null : (
          <>
        <DialogHeader
          data-drag-handle
          className="shrink-0 cursor-grab active:cursor-grabbing"
          onPointerDown={composeMove.onHandlePointerDown}
        >
          <DialogTitle className="flex items-center gap-1.5">
            <GripVertical className="size-3.5 text-muted-foreground" aria-hidden />
            Collect
          </DialogTitle>
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
                const feed = await api.addFeed(url, {
                  shelfId: rssShelfId || null,
                  categoryId: categoryId || null,
                });
                if (feed.last_error) {
                  toast.error(feed.last_error);
                } else {
                  toast.success("Feed added. Articles are importing.");
                }
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
            <div className="space-y-1.5">
              <Label htmlFor="feed-shelf">Shelf</Label>
              <RssShelfSelect
                id="feed-shelf"
                value={rssShelfId}
                shelves={rssShelves}
                onCreateShelf={handleCreateFeedShelf}
                onChange={(next) => {
                  setRssShelfId(next);
                  setCategoryId("");
                }}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="feed-category">Category</Label>
              <div className="flex gap-2">
                <select
                  id="feed-category"
                  className="h-9 min-w-0 flex-1 rounded-md border bg-background px-3 text-sm"
                  value={categoryId}
                  onChange={(event) => setCategoryId(event.target.value)}
                >
                  <option value="">Uncategorized</option>
                  {shelfCategories.map((category) => (
                    <option key={category.id} value={category.id}>
                      {category.name}
                    </option>
                  ))}
                </select>
                <Button type="button" variant="outline" size="sm" onClick={() => void createCategoryInline()}>
                  + New category
                </Button>
              </div>
            </div>
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
                    composeFolder,
                  );
                  toast.success("Note saved on that StoryKeep shelf. Steve's Surface Vault was not overwritten.");
                  setAdditionTitle("");
                  setAdditionSubject("");
                  setAdditionBody("");
                  setComposeFolder(null);
                  setComposeCorrection(false);
                  setComposeFull(false);
                  onOpenChange(false);
                  await onCreatedNote(article.id, composeDest, composeFolder);
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
                    <DestinationSelect
                      value={composeDest}
                      onChange={handleComposeDestChange}
                      customShelves={customNoteShelves}
                      onCreateShelf={handleCreateComposeShelf}
                    />
                    <FolderSelect
                      shelf={composeDest}
                      folders={folders}
                      value={composeFolder}
                      onChange={setComposeFolder}
                      onCreateFolder={() => void handleComposeCreateFolder()}
                    />
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
            StoryKeep is the working archive. Primary backup is a dated bundle on Backblaze when configured: Export JSON
            (archive.json + note media in one zip) or Dump database (pg_dump). A database dump is also uploaded to that
            bucket about once a day. Nothing writes to Steve&apos;s Surface Vault on
            disk. The Obsidian overlay pack is optional if you still want a markdown zip.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-wrap gap-2">
          <Button
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                const row = await api.createBackup("export_json");
                if (row.status !== "success") {
                  toast.error(row.error || "JSON export failed");
                } else if (row.destination === "s3") {
                  toast.success("Dated export bundle saved to Backblaze under storykeep/");
                } else {
                  toast.success("Dated export bundle saved on this server");
                }
                await onCreated();
              } catch (error) {
                toast.error(error instanceof ApiError ? error.message : "Export failed");
              } finally {
                setBusy(false);
              }
            }}
          >
            Export JSON bundle
          </Button>
          <Button
            variant="secondary"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                const row = await api.createBackup("db_dump");
                toast[row.status === "success" ? "success" : "error"](
                  row.status === "success"
                    ? row.destination === "s3"
                      ? "Database dump saved to Backblaze under storykeep/"
                      : "Database dump saved on this server"
                    : row.error || "Dump failed",
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
          <Button
            variant="outline"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await api.downloadObsidianPack();
                toast.success("Obsidian overlay pack downloaded");
              } catch (error) {
                toast.error(error instanceof ApiError ? error.message : "Pack download failed");
              } finally {
                setBusy(false);
              }
            }}
          >
            Obsidian overlay pack (optional)
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
