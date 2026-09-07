"use client";

import { useRef, useState, type MutableRefObject, type Ref } from "react";
import { Highlighter, ImagePlus, LoaderCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import { wrapHighlight } from "@/lib/markdown";

function assignRef<T>(ref: Ref<T> | undefined, value: T | null) {
  if (!ref) return;
  if (typeof ref === "function") ref(value);
  else (ref as MutableRefObject<T | null>).current = value;
}

export function NoteComposer({
  value,
  onChange,
  placeholder,
  rows = 8,
  required,
  id,
  textareaRef,
}: {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  rows?: number;
  required?: boolean;
  id?: string;
  textareaRef?: Ref<HTMLTextAreaElement>;
}) {
  const areaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const applyWrap = (next: string, start: number, end: number) => {
    onChange(next);
    requestAnimationFrame(() => {
      const el = areaRef.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(start, end);
    });
  };

  return (
    <div className="space-y-2">
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
      />
      <p className="text-[11px] text-muted-foreground">
        Highlight wraps the selection in <code>==yellow marks==</code>. Images stay in StoryKeep and unzip under
        StoryKeep/Additions/media.
      </p>
    </div>
  );
}
