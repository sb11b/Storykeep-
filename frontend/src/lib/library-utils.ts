import { destinationLabel, type CustomNoteShelf, type FilingDestination } from "@/lib/custom-note-shelves";
import { folderById, isFolderShelf } from "@/lib/folders";
import type { Archive, Article, Category, Feed, Folder, Shelf, Tag } from "@/lib/types";

export function isStoryKeepNote(article: Article): boolean {
  return (article.guid || "").startsWith("storykeep-note:");
}

export function isVaultImport(article: Article): boolean {
  return (article.guid || "").startsWith("obsidian:") && article.source_kind !== "textbook";
}

export function displayArticleShelf(
  article: Article,
  asFilingDestination: (value: string | null | undefined, fallback?: string) => string,
): FilingDestination | "" {
  if (article.destination) {
    return asFilingDestination(article.destination, article.destination);
  }
  if (article.source_kind === "textbook") return "books";
  return "";
}

export function snapshotKind(row: Archive): "html" | "pdf" {
  if (row.type === "pdf" || row.archive_type === "pdf") return "pdf";
  return "html";
}

export function snapshotStamp(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function readerActionError(
  error: unknown,
  fallback: string,
  toastErrorFromUnknown: (error: unknown, fallback: string) => void,
): never {
  toastErrorFromUnknown(error, fallback);
  throw error;
}

export function composedNoteMarkdown(article: Article): string {
  const fromArticle = (article.content_text || "").trim();
  if (fromArticle) return fromArticle;
  const fromOverlay = (article.overlay_additions?.[0]?.markdown || "").trim();
  if (fromOverlay) return fromOverlay;
  return "";
}

export function composedNoteHtml(
  article: Article,
  sanitizeHtml: (html: string) => string,
  noteMarkdownHtml: (markdown: string) => string,
): string {
  const markdown = composedNoteMarkdown(article);
  if (markdown) return sanitizeHtml(noteMarkdownHtml(markdown));
  if (article.content_html) return sanitizeHtml(article.content_html);
  return "";
}

export function shelfTitle(
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

export function shelfKey(shelf: Shelf): string {
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
