"use client";

import { Download, ExternalLink, Paperclip, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { fileAttachments, removeAttachmentFromMarkdown, type NoteAttachment } from "@/lib/note-attachments";
import { toastErrorFromUnknown } from "@/lib/toast-message";
import { cn } from "@/lib/utils";

function AttachmentRow({
  item,
  onRemove,
  compact = false,
}: {
  item: NoteAttachment;
  onRemove?: () => void;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2 rounded-md border bg-muted/35 px-2.5 py-1.5",
        compact && "text-xs",
      )}
    >
      <Paperclip className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate font-medium">{item.label}</span>
      <div className="flex flex-wrap gap-1">
        <a
          href={item.url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex h-7 items-center gap-1 rounded-md border border-input bg-background px-2 text-xs hover:bg-accent"
        >
          <ExternalLink className="size-3" />
          Open
        </a>
        <a
          href={item.url}
          download={item.label}
          className="inline-flex h-7 items-center gap-1 rounded-md border border-input bg-background px-2 text-xs hover:bg-accent"
        >
          <Download className="size-3" />
          Download
        </a>
        {onRemove ? (
          <Button type="button" size="xs" variant="ghost" onClick={onRemove}>
            <X className="size-3" />
            Remove
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function NoteAttachmentEditorList({
  markdown,
  onChange,
}: {
  markdown: string;
  onChange: (next: string) => void;
}) {
  const items = fileAttachments(markdown);
  if (!items.length) return null;

  return (
    <ul className="space-y-2">
      {items.map((item) => (
        <li key={item.id}>
          <AttachmentRow
            item={item}
            onRemove={() => {
              void (async () => {
                const next = removeAttachmentFromMarkdown(markdown, item.id);
                onChange(next);
                try {
                  await api.deleteNoteMedia(item.id);
                } catch (error) {
                  toastErrorFromUnknown(error, "Could not remove that attachment");
                }
              })();
            }}
          />
        </li>
      ))}
    </ul>
  );
}

export function NoteAttachmentChips({
  markdown,
  className,
}: {
  markdown: string;
  className?: string;
}) {
  const items = fileAttachments(markdown);
  if (!items.length) return null;

  return (
    <div className={cn("flex flex-wrap gap-2", className)}>
      {items.map((item) => (
        <AttachmentRow key={item.id} item={item} compact />
      ))}
    </div>
  );
}
