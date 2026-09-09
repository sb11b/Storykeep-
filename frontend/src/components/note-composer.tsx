"use client";

import { useEffect, useRef, useState, type MutableRefObject, type ReactNode, type Ref } from "react";
import { Bold, Highlighter, ImagePlus, Italic, List, ListOrdered, LoaderCircle, Maximize2, Minimize2, Underline } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useDictation } from "@/components/dictation";
import { ApiError, api } from "@/lib/api";
import { noteMarkdownHtml, prefixSelectedLines, wrapHighlight, wrapInline } from "@/lib/markdown";
import { cn } from "@/lib/utils";

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
}) {
  const dictation = useDictation();
  const areaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [showPreview, setShowPreview] = useState(false);

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

  return (
    <div
      className={cn(
        "flex min-h-0 flex-col gap-2",
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
          <Button type="button" size="sm" variant="outline" disabled={uploading} onClick={() => fileRef.current?.click()}>
            {uploading ? <LoaderCircle className="size-3.5 animate-spin" /> : <ImagePlus className="size-3.5" />}
            {uploading ? "Uploading…" : "Image"}
          </Button>
        </div>
        <div className="flex flex-wrap gap-2">
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
        </div>
        <input
          ref={fileRef}
          type="file"
          accept="image/png,image/jpeg,image/gif,image/webp,.png,.jpg,.jpeg,.gif,.webp"
          className="hidden"
          onChange={async (event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (!file) return;
            setUploading(true);
            try {
              const uploaded = await api.uploadNoteImage(file);
              const el = areaRef.current;
              const start = el?.selectionStart ?? value.length;
              const end = el?.selectionEnd ?? value.length;
              const insert = uploaded.markdown;
              const prefix = start > 0 && value[start - 1] !== "\n" ? "\n" : "";
              const suffix = value[end] !== "\n" ? "\n" : "";
              const chunk = `${prefix}${insert}${suffix}`;
              const next = value.slice(0, start) + chunk + value.slice(end);
              const cursor = start + chunk.length;
              applyWrap(next, cursor, cursor);
              toast.success("Image added to the note");
            } catch (error) {
              toast.error(error instanceof ApiError ? error.message : "Could not add that image");
            } finally {
              setUploading(false);
            }
          }}
        />
      </div>
      {header ? <div className="shrink-0 space-y-2">{header}</div> : null}
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
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          "w-full min-h-0 resize-none overflow-y-auto [field-sizing:fixed]",
          (expanded || fill) && "h-auto min-h-0 flex-1",
        )}
      />
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
          >
            {value.trim() ? (
              <div dangerouslySetInnerHTML={{ __html: noteMarkdownHtml(value) }} />
            ) : (
              <p className="m-0 text-[11px] text-muted-foreground">
                Selected words turn yellow here as <mark>mark</mark>. Bold, italic, underline, and lists render here too.
              </p>
            )}
          </div>
        ) : null}
      </div>
      <p className="shrink-0 text-[11px] text-muted-foreground">
        Highlight uses <code>==yellow==</code>. Underline uses <code>&lt;u&gt;</code> so marks stay yellow. Images stay in
        StoryKeep and unzip under StoryKeep/Additions/media.
        {expanded ? " Esc or Shrink returns to the card." : null}
      </p>
    </div>
  );
}
