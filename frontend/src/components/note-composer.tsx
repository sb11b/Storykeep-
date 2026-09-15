"use client";

import { useEffect, useRef, useState, type MutableRefObject, type ReactNode, type Ref } from "react";
import {
  Bold,
  Code2,
  Highlighter,
  History,
  ImagePlus,
  Italic,
  Link2,
  List,
  ListOrdered,
  LoaderCircle,
  Maximize2,
  Minimize2,
  Paperclip,
  Underline,
  Undo2,
} from "lucide-react";
import { NoteAttachmentEditorList } from "@/components/note-attachments";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useDictation } from "@/components/dictation";
import { ApiError, api } from "@/lib/api";
import { restoreCharsConfirm } from "@/lib/api-errors";
import { formatRelative } from "@/lib/format";
import type { Article, NoteRevision } from "@/lib/types";
import { onCodeCopyClick } from "@/lib/code-copy";
import {
  normalizeCodeLang,
  noteMarkdownHtml,
  prefixSelectedLines,
  wrapCodeFence,
  wrapHighlight,
  wrapInline,
  wrapWikilink,
} from "@/lib/markdown";
import { wikilinkQueryAtCaret } from "@/lib/wikilinks";
import {
  applyComposerStyle,
  COMPOSER_STYLE_OPTIONS,
  detectComposerStyle,
  type ComposerStyle,
} from "@/lib/note-style";
import { cn } from "@/lib/utils";
import { wordCount } from "@/lib/word-count";

function assignRef<T>(ref: Ref<T> | undefined, value: T | null) {
  if (!ref) return;
  if (typeof ref === "function") ref(value);
  else (ref as MutableRefObject<T | null>).current = value;
}

const COMPOSE_FULL_KEY = "storykeep-compose-fullscreen";

function readComposeFull() {
  if (typeof window === "undefined") return false;
  try {
    return sessionStorage.getItem(COMPOSE_FULL_KEY) === "1";
  } catch {
    return false;
  }
}

function writeComposeFull(next: boolean) {
  try {
    sessionStorage.setItem(COMPOSE_FULL_KEY, next ? "1" : "0");
  } catch {
    /* ignore */
  }
}

export function NoteComposer({
  value,
  onChange,
  placeholder,
  rows = 8,
  required,
  id,
  textareaRef,
  header,
  actions,
  toolbarExtra,
  fill = false,
  onExpandedChange,
  noteId,
  onRestored,
}: {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  rows?: number;
  required?: boolean;
  id?: string;
  textareaRef?: Ref<HTMLTextAreaElement>;
  header?: ReactNode;
  actions?: ReactNode;
  toolbarExtra?: ReactNode;
  fill?: boolean;
  onExpandedChange?: (expanded: boolean) => void;
  noteId?: string | null;
  onRestored?: (article: Article) => void;
}) {
  const dictation = useDictation();
  const areaRef = useRef<HTMLTextAreaElement>(null);
  const imageRef = useRef<HTMLInputElement>(null);
  const attachRef = useRef<HTMLInputElement>(null);
  const selectionRef = useRef({ start: 0, end: 0 });
  const [uploadingImage, setUploadingImage] = useState(false);
  const [uploadingFile, setUploadingFile] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [composerStyle, setComposerStyle] = useState<ComposerStyle>("body");
  const [wikilinkTitles, setWikilinkTitles] = useState<Array<{ id: string; title: string }>>([]);
  const [wikilinkPick, setWikilinkPick] = useState<{ query: string; replaceFrom: number; replaceTo: number } | null>(
    null,
  );
  const [historyOpen, setHistoryOpen] = useState(false);
  const [revisions, setRevisions] = useState<NoteRevision[]>([]);
  const [historyBusy, setHistoryBusy] = useState(false);

  useEffect(() => {
    if (readComposeFull()) setOpen(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const applyWrap = (next: string, start: number, end: number) => {
    onChange(next);
    requestAnimationFrame(() => {
      const el = areaRef.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(start, end);
    });
  };

  function setOpen(next: boolean) {
    setExpanded(next);
    writeComposeFull(next);
    onExpandedChange?.(next);
    requestAnimationFrame(() => {
      const el = areaRef.current;
      if (el) dictation?.attach(el);
    });
  }

  useEffect(() => {
    const el = areaRef.current;
    if (!el) return;
    if (expanded || fill) {
      el.style.height = "";
      return;
    }
    el.style.height = "auto";
    const minPx = Math.max(rows * 22, 112);
    const maxPx = Math.round(window.innerHeight * 0.4);
    el.style.height = `${Math.min(Math.max(el.scrollHeight, minPx), maxPx)}px`;
  }, [value, expanded, rows, fill]);

  useEffect(() => {
    if (!expanded) return;
    areaRef.current?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      dictation?.stop();
      setOpen(false);
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [expanded, dictation]);

  function runWrap(maker: (source: string, start: number, end: number) => { text: string; selectionStart: number; selectionEnd: number }) {
    const el = areaRef.current;
    const start = el?.selectionStart ?? value.length;
    const end = el?.selectionEnd ?? value.length;
    const result = maker(value, start, end);
    applyWrap(result.text, result.selectionStart, result.selectionEnd);
  }

  function captureSelection() {
    const el = areaRef.current;
    if (!el) return;
    selectionRef.current = { start: el.selectionStart, end: el.selectionEnd };
  }

  function syncComposerStyle() {
    captureSelection();
    const { start, end } = selectionRef.current;
    setComposerStyle(detectComposerStyle(value, start, end));
  }

  function applyStyle(style: ComposerStyle) {
    const { start, end } = selectionRef.current;
    const result = applyComposerStyle(value, start, end, style);
    setComposerStyle(style);
    applyWrap(result.text, result.selectionStart, result.selectionEnd);
  }

  async function insertUploadedMedia(file: File, mode: "image" | "file") {
    const setBusy = mode === "image" ? setUploadingImage : setUploadingFile;
    setBusy(true);
    try {
      const uploaded = await api.uploadNoteMedia(file);
      const { start, end } = selectionRef.current;
      const insertAt = Math.max(0, Math.min(start, value.length));
      const insertEnd = Math.max(insertAt, Math.min(end, value.length));
      const insert =
        uploaded.kind === "file" || mode === "file"
          ? `[${uploaded.filename}](${uploaded.url})`
          : uploaded.markdown;
      const prefix = insertAt > 0 && value[insertAt - 1] !== "\n" ? "\n" : "";
      const suffix = insertEnd >= value.length || value[insertEnd] !== "\n" ? "\n" : "";
      const chunk = `${prefix}${insert}${suffix}`;
      const next = value.slice(0, insertAt) + chunk + value.slice(insertEnd);
      const cursor = insertAt + chunk.length;
      applyWrap(next, cursor, cursor);
      toast.success(mode === "image" ? "Image added to the note" : "File attached to the note");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not upload that file");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!wikilinkPick) {
      setWikilinkTitles([]);
      return;
    }
    let cancelled = false;
    void api.noteTitles(wikilinkPick.query, 12).then((payload) => {
      if (!cancelled) setWikilinkTitles(payload.items);
    });
    return () => {
      cancelled = true;
    };
  }, [wikilinkPick]);

  function syncWikilinkAutocomplete() {
    const el = areaRef.current;
    if (!el) return;
    const caret = el.selectionStart ?? value.length;
    setWikilinkPick(wikilinkQueryAtCaret(value, caret));
  }

  function insertWikilinkTitle(title: string) {
    if (!wikilinkPick) return;
    const { replaceFrom, replaceTo } = wikilinkPick;
    const next = `${value.slice(0, replaceFrom)}${title}${value.slice(replaceTo)}`;
    const caret = replaceFrom + title.length;
    applyWrap(next, caret, caret);
    setWikilinkPick(null);
    setWikilinkTitles([]);
  }

  function insertCodeFence() {
    const el = areaRef.current;
    const start = el?.selectionStart ?? value.length;
    const end = el?.selectionEnd ?? value.length;
    const picked = window.prompt("Code language (python, js, sql, text)", "text");
    if (picked === null) return;
    const lang = normalizeCodeLang(picked);
    const result = wrapCodeFence(value, start, end, lang);
    applyWrap(result.text, result.selectionStart, result.selectionEnd);
  }

  async function loadRevisions() {
    if (!noteId) return;
    try {
      setRevisions(await api.listNoteRevisions(noteId));
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not load note history");
    }
  }

  async function undoLastSave() {
    if (!noteId) return;
    setHistoryBusy(true);
    try {
      const rows = await api.listNoteRevisions(noteId);
      const latest = rows[0];
      if (!latest) {
        toast.error("No previous save to undo.");
        return;
      }
      if (!window.confirm(restoreCharsConfirm(latest.char_count))) return;
      const article = await api.undoNoteRevision(noteId);
      onChange(article.content_text || "");
      onRestored?.(article);
      toast.success("Restored previous save");
      await loadRevisions();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not undo that save");
    } finally {
      setHistoryBusy(false);
    }
  }

  async function restoreRevision(row: NoteRevision) {
    if (!noteId) return;
    if (!window.confirm(restoreCharsConfirm(row.char_count))) return;
    setHistoryBusy(true);
    try {
      const article = await api.restoreNoteRevision(noteId, row.id);
      onChange(article.content_text || "");
      onRestored?.(article);
      toast.success("Restored that version");
      await loadRevisions();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not restore that version");
    } finally {
      setHistoryBusy(false);
    }
  }

  const pinned = expanded || fill;

  return (
    <div
      className={cn(
        "flex min-h-0 flex-col gap-2 overflow-hidden",
        fill && !expanded && "h-full min-h-0 flex-1",
        expanded && "fixed inset-0 z-[80] flex h-[100dvh] w-[100vw] flex-col bg-background p-3",
      )}
    >
      <div className="flex w-full shrink-0 flex-wrap items-center gap-2 bg-background">
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => runWrap(wrapHighlight)}
          >
            <Highlighter className="size-3.5" />
            Highlight
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => runWrap((source, start, end) => wrapInline(source, start, end, "**", "**"))}
          >
            <Bold className="size-3.5" />
            Bold
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => runWrap((source, start, end) => wrapInline(source, start, end, "*", "*"))}
          >
            <Italic className="size-3.5" />
            Italic
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => runWrap((source, start, end) => wrapInline(source, start, end, "<u>", "</u>"))}
          >
            <Underline className="size-3.5" />
            Underline
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => runWrap((source, start, end) => prefixSelectedLines(source, start, end, "ul"))}
          >
            <List className="size-3.5" />
            List
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => runWrap((source, start, end) => prefixSelectedLines(source, start, end, "ol"))}
          >
            <ListOrdered className="size-3.5" />
            Outline
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onMouseDown={(event) => event.preventDefault()}
            onClick={insertCodeFence}
          >
            <Code2 className="size-3.5" />
            Code
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => runWrap(wrapWikilink)}
          >
            <Link2 className="size-3.5" />
            Link note
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={uploadingImage}
            onMouseDown={(event) => {
              event.preventDefault();
              captureSelection();
            }}
            onClick={() => imageRef.current?.click()}
          >
            {uploadingImage ? <LoaderCircle className="size-3.5 animate-spin" /> : <ImagePlus className="size-3.5" />}
            {uploadingImage ? "Uploading…" : "Image"}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={uploadingFile}
            onMouseDown={(event) => {
              event.preventDefault();
              captureSelection();
            }}
            onClick={() => attachRef.current?.click()}
          >
            {uploadingFile ? <LoaderCircle className="size-3.5 animate-spin" /> : <Paperclip className="size-3.5" />}
            {uploadingFile ? "Uploading…" : "Attach"}
          </Button>
          <label className="inline-flex items-center gap-1.5 text-[0.8rem] text-muted-foreground">
            <span className="whitespace-nowrap">Style</span>
            <select
              aria-label="Text style"
              value={composerStyle}
              onPointerDown={captureSelection}
              onFocus={syncComposerStyle}
              onChange={(event) => applyStyle(event.target.value as ComposerStyle)}
              className="h-7 rounded-md border border-input bg-background px-2 text-[0.8rem] text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              {COMPOSER_STYLE_OPTIONS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="flex flex-wrap gap-2">
          {noteId ? (
            <>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={historyBusy}
                onClick={() => void undoLastSave()}
              >
                <Undo2 className="size-3.5" />
                Undo last save
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={historyBusy}
                onClick={() => {
                  const next = !historyOpen;
                  setHistoryOpen(next);
                  if (next) void loadRevisions();
                }}
              >
                <History className="size-3.5" />
                History
              </Button>
            </>
          ) : null}
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() => setOpen(!expanded)}
            aria-label={expanded ? "Shrink editor" : "Expand editor"}
          >
            {expanded ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
            {expanded ? "Shrink" : "Expand"}
          </Button>
          {expanded ? (
            <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
          ) : null}
          {toolbarExtra}
          {actions}
          <span className="text-[11px] text-muted-foreground">{wordCount(value)} words</span>
        </div>
        <input
          ref={imageRef}
          type="file"
          accept="image/png,image/jpeg,image/gif,image/webp,.png,.jpg,.jpeg,.gif,.webp"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (!file) return;
            void insertUploadedMedia(file, "image");
          }}
        />
        <input
          ref={attachRef}
          type="file"
          accept=".pdf,.txt,.md,.docx,.csv,application/pdf,text/plain,text/markdown,text/csv,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.png,.jpg,.jpeg,.gif,.webp,image/png,image/jpeg,image/gif,image/webp"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (!file) return;
            void insertUploadedMedia(file, "file");
          }}
        />
      </div>
      {noteId && historyOpen ? (
        <div className="max-h-40 shrink-0 overflow-y-auto rounded-md border bg-muted/30 px-2 py-1.5">
          {revisions.length === 0 ? (
            <p className="m-0 text-[11px] text-muted-foreground">
              No earlier saves yet. History appears after you update this note.
            </p>
          ) : (
            <ul className="space-y-1">
              {revisions.map((row) => (
                <li key={row.id} className="flex flex-wrap items-center justify-between gap-2 text-[11px]">
                  <span>
                    {formatRelative(row.created_at)} · {row.char_count} characters
                  </span>
                  <Button type="button" size="xs" variant="ghost" disabled={historyBusy} onClick={() => void restoreRevision(row)}>
                    Restore
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
      <div className="shrink-0 space-y-2">
        {header ? <div className="space-y-2">{header}</div> : null}
        <NoteAttachmentEditorList markdown={value} onChange={onChange} />
      </div>
      <div className={cn("relative flex min-h-0 flex-col overflow-hidden", pinned && "min-h-0 flex-1")}>
        <Textarea
          id={id}
          ref={(node) => {
            areaRef.current = node;
            assignRef(textareaRef, node);
          }}
          value={value}
          required={required}
          rows={rows}
          placeholder={placeholder}
          onChange={(event) => {
            onChange(event.target.value);
            requestAnimationFrame(syncWikilinkAutocomplete);
          }}
          onSelect={() => {
            syncComposerStyle();
            syncWikilinkAutocomplete();
          }}
          onKeyUp={() => {
            syncComposerStyle();
            syncWikilinkAutocomplete();
          }}
          onClick={() => {
            syncComposerStyle();
            syncWikilinkAutocomplete();
          }}
          onFocus={() => {
            captureSelection();
            syncWikilinkAutocomplete();
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape" && wikilinkPick) {
              event.preventDefault();
              setWikilinkPick(null);
              setWikilinkTitles([]);
            }
          }}
          className={cn(
            "w-full min-h-0 resize-none overflow-y-auto [field-sizing:fixed]",
            pinned ? "min-h-0 flex-1" : "min-h-[6rem] max-h-[40vh]",
          )}
        />
        {wikilinkPick && wikilinkTitles.length > 0 ? (
          <ul className="absolute left-0 right-0 top-full z-20 mt-1 max-h-40 overflow-y-auto rounded-md border bg-popover shadow-md">
            {wikilinkTitles.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className="w-full px-3 py-1.5 text-left text-sm hover:bg-accent"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => insertWikilinkTitle(item.title)}
                >
                  {item.title}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      <div className="shrink-0 space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[11px] font-medium text-muted-foreground">Highlight preview</p>
          <Button type="button" size="xs" variant="ghost" onClick={() => setShowPreview((current) => !current)}>
            {showPreview ? "Hide preview" : "Show preview"}
          </Button>
        </div>
        {showPreview ? (
          <div
            className="note-md composer-preview h-40 max-h-48 overflow-y-auto rounded-md border bg-muted/40 px-2.5 py-2 text-sm"
            aria-label="Highlight preview"
            onClick={onCodeCopyClick}
          >
            {value.trim() ? (
              <div dangerouslySetInnerHTML={{ __html: noteMarkdownHtml(value) }} />
            ) : (
              <p className="m-0 text-[11px] text-muted-foreground">
                Selected words turn yellow here as <mark>mark</mark>. Bold, italic, underline, sizes, headings, and lists render here too.
              </p>
            )}
          </div>
        ) : null}
      </div>
      <p className="shrink-0 text-[11px] text-muted-foreground">
        Highlight uses <code>==yellow==</code>. Attach stores files in StoryKeep media only — never in Steve&apos;s Surface Vault.
        Pack export copies them to StoryKeep/Additions/media with relative links.
        {expanded ? " Esc or Shrink returns to the card." : null}
      </p>
    </div>
  );
}
