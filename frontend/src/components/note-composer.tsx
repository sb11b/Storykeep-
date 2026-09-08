"use client";

import { useEffect, useRef, useState, type MutableRefObject, type ReactNode, type Ref } from "react";
import { Highlighter, ImagePlus, LoaderCircle, Maximize2, Minimize2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import { renderMarkdown, wrapHighlight } from "@/lib/markdown";
import { cn } from "@/lib/utils";

function assignRef<T>(ref: Ref<T> | undefined, value: T | null) {
  if (!ref) return;
  if (typeof ref === "function") ref(value);
  else (ref as MutableRefObject<T | null>).current = value;
}

const LONG_NOTE_CHARS = 1400;
const LONG_NOTE_LINES = 18;

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
  fill = false,
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
  fill?: boolean;
}) {
  const areaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const skipAutoExpand = useRef(false);
  const [uploading, setUploading] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const applyWrap = (next: string, start: number, end: number) => {
    onChange(next);
    requestAnimationFrame(() => {
      const el = areaRef.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(start, end);
    });
  };

  function setOpen(next: boolean, fromUser = false) {
    if (fromUser && !next) skipAutoExpand.current = true;
    if (fromUser && next) skipAutoExpand.current = false;
    setExpanded(next);
  }

  useEffect(() => {
    if (expanded || skipAutoExpand.current) return;
    const lines = value.split("\n").length;
    if (value.length >= LONG_NOTE_CHARS || lines >= LONG_NOTE_LINES) setExpanded(true);
  }, [value, expanded]);

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
    const el = areaRef.current;
    el?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      setOpen(false, true);
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [expanded]);

  return (
    <div
      className={cn(
        "flex min-h-0 flex-col gap-2",
        fill && !expanded && "h-full min-h-0 flex-1",
        expanded && "fixed inset-3 z-[70] rounded-xl border bg-background p-3 shadow-2xl md:inset-5",
      )}
    >
      <div className="flex w-full shrink-0 flex-wrap items-center gap-2 bg-background">
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => {
              const el = areaRef.current;
              const start = el?.selectionStart ?? value.length;
              const end = el?.selectionEnd ?? value.length;
              const result = wrapHighlight(value, start, end);
              applyWrap(result.text, result.selectionStart, result.selectionEnd);
            }}
          >
            <Highlighter className="size-3.5" />
            Highlight
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
            onClick={() => setOpen(!expanded, true)}
            aria-label={expanded ? "Shrink editor" : "Expand editor"}
          >
            {expanded ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
            {expanded ? "Shrink" : "Expand"}
          </Button>
          {expanded ? (
            <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false, true)}>
              Cancel
            </Button>
          ) : null}
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
      <div
        className="note-md composer-preview max-h-36 shrink-0 overflow-y-auto rounded-md border bg-muted/40 px-2.5 py-2 text-sm"
        aria-label="Highlight preview"
      >
        {value.trim() ? (
          <div dangerouslySetInnerHTML={{ __html: renderMarkdown(value) }} />
        ) : (
          <p className="m-0 text-[11px] text-muted-foreground">
            Highlight preview: selected words turn yellow here as <mark>mark</mark>.
          </p>
        )}
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
          "min-h-0 resize-none overflow-y-auto [field-sizing:fixed]",
          (expanded || fill) && "h-auto min-h-0 flex-1",
        )}
      />
      <p className="shrink-0 text-[11px] text-muted-foreground">
        Highlight wraps the selection in <code>==yellow marks==</code>. Images stay in StoryKeep and unzip under
        StoryKeep/Additions/media.
        {expanded ? " Esc or Shrink returns to the list." : null}
      </p>
    </div>
  );
}
