"use client";

import { useEffect, useState } from "react";
import { GripVertical } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CorrectionCheck, DestinationSelect, FolderSelect, RssShelfSelect } from "@/components/destination-controls";
import { NoteComposer } from "@/components/note-composer";
import { useMovableWindow } from "@/components/movable-window";
import { COMPOSE_POS_KEY } from "@/lib/movable-window";
import { ApiError, api } from "@/lib/api";
import { asFilingDestination } from "@/lib/destinations";
import { loadLastFiling, saveLastFiling } from "@/lib/last-filing";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ArticleListItem, Backup, Category, Feed, Folder, RssShelf, Tag } from "@/lib/types";
import type { CustomNoteShelf, FilingDestination } from "@/lib/custom-note-shelves";

export function EmptyState({
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

export function DeleteArticleDialog({
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

export function RemoveFeedDialog({
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

export function AddFeedDialog({
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
  const [composeDest, setComposeDest] = useState<FilingDestination>(() => loadLastFiling("notes").dest);
  const [composeFolder, setComposeFolder] = useState<string | null>(() => loadLastFiling("notes").folderId);
  const [composeCorrection, setComposeCorrection] = useState(false);

  function handleComposeDestChange(next: FilingDestination | "") {
    if (!next) return;
    setComposeDest(next);
    setComposeFolder(null);
    saveLastFiling(next, null);
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
    const last = loadLastFiling("notes");
    setComposeDest(last.dest);
    setComposeFolder(last.folderId);
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
                  const dest = composeDest;
                  const folder = composeFolder;
                  const article = await api.composeVaultNote(
                    additionTitle.trim(),
                    additionBody.trim(),
                    tags,
                    dest,
                    composeCorrection,
                    folder,
                  );
                  const filedDest = asFilingDestination(article.destination, dest);
                  const filedFolder = article.folder_id ?? folder;
                  saveLastFiling(filedDest, filedFolder);
                  toast.success("Note saved on that StoryKeep shelf. Steve's Surface Vault was not overwritten.");
                  setAdditionTitle("");
                  setAdditionSubject("");
                  setAdditionBody("");
                  setComposeCorrection(false);
                  setComposeFull(false);
                  onOpenChange(false);
                  await onCreatedNote(article.id, filedDest, filedFolder);
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
                      onChange={(next) => {
                        setComposeFolder(next);
                        saveLastFiling(composeDest, next);
                      }}
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

export function TagsDialog({
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

export function BackupDialog({
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
