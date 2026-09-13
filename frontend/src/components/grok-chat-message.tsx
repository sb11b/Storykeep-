"use client";

import { type MouseEvent, useEffect, useRef } from "react";
import { Copy, Download, LoaderCircle, NotebookPen, Paperclip, Volume2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { onCodeCopyClick } from "@/lib/code-copy";
import { downloadChatPicture, resolveChatImageSrc } from "@/lib/chat-media-download";
import { sanitizeHtml } from "@/lib/format";
import { renderMarkdown } from "@/lib/markdown";
import { DEFAULT_PANE_NAME } from "@/lib/grok-pane-name";
import { formatFileSize, type LarryAttachment } from "@/lib/larry-attach";
import { buildVisibleSpeechScript } from "@/lib/tts-visible";
import { cn } from "@/lib/utils";

function toastDownloadError(error: unknown) {
  toast.error(error instanceof Error ? error.message : "Could not download that picture.");
}

function onReplyBodyClick(event: MouseEvent<HTMLElement>) {
  const trigger = (event.target as HTMLElement).closest<HTMLElement>(".sk-chat-image-download");
  if (trigger) {
    event.preventDefault();
    event.stopPropagation();
    const figure = trigger.closest("figure");
    const img = figure?.querySelector("img") ?? trigger.parentElement?.querySelector("img");
    const mediaId = trigger.getAttribute("data-media-id") || "";
    void downloadChatPicture({
      img,
      mediaId,
      url: img?.currentSrc || img?.getAttribute("src") || trigger.getAttribute("data-media-url"),
    }).catch(toastDownloadError);
    return;
  }
  onCodeCopyClick(event);
}

function ChatPicture({
  mediaId,
  alt,
  contentType,
}: {
  mediaId: string;
  url: string;
  alt: string;
  contentType?: string | null;
}) {
  const src = resolveChatImageSrc(url, mediaId);
  return (
    <figure className="sk-chat-image mt-2">
      <img src={src} alt={alt} className="max-h-80 w-auto max-w-full rounded-md border" />
      <Button
        type="button"
        size="xs"
        variant="outline"
        className="mt-1.5"
        aria-label="Download picture"
        onClick={(event) => {
          const img = (event.currentTarget.closest("figure") as HTMLElement | null)?.querySelector("img");
          void downloadChatPicture({
            img,
            mediaId,
            url: img?.currentSrc || img?.getAttribute("src") || src,
            contentType,
          }).catch(toastDownloadError);
        }}
      >
        <Download className="size-3" />
        Download picture
      </Button>
    </figure>
  );
}

export function GrokChatMessage({
  id,
  role,
  content,
  files = [],
  assistantName = DEFAULT_PANE_NAME,
  error,
  failed,
  waiting,
  busy,
  ttsAvailable,
  listening,
  activeWord,
  statusLine,
  routeLabel,
  onRegisterBody,
  onListen,
  onAddToNotes,
  onRetry,
}: {
  id: string;
  role: "user" | "assistant";
  content: string;
  files?: LarryAttachment[];
  /** Custom pane name, e.g. "Junior". */
  assistantName?: string;
  error?: string | null;
  failed?: boolean;
  waiting?: boolean;
  busy?: boolean;
  ttsAvailable: boolean;
  listening?: boolean;
  activeWord?: number | null;
  statusLine?: string | null;
  /** Auto routing, e.g. "Auto → 4.6 · low". Not inside the Listen body. */
  routeLabel?: string | null;
  onRegisterBody?: (messageId: string, element: HTMLElement | null) => void;
  /** `trigger` is the Listen button, so the reply body is one closest() away. */
  onListen?: (messageId: string, trigger: HTMLElement) => void;
  onAddToNotes: (content: string) => void;
  onRetry?: () => void;
}) {
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = bodyRef.current;
    if (!root || role !== "assistant" || !content) return;
    root.innerHTML = sanitizeHtml(renderMarkdown(content));
    buildVisibleSpeechScript(root);
  }, [content, id, role]);

  useEffect(() => {
    onRegisterBody?.(id, bodyRef.current);
    return () => onRegisterBody?.(id, null);
  }, [id, onRegisterBody, content]);

  useEffect(() => {
    const root = bodyRef.current;
    if (!root) return;
    root.querySelectorAll(".tts-word-active").forEach((node) => node.classList.remove("tts-word-active"));
    if (activeWord == null) return;
    const current = root.querySelector(`[data-tts-word="${activeWord}"]`);
    if (current instanceof HTMLElement) {
      current.classList.add("tts-word-active");
      if (listening) current.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [activeWord, content, listening]);

  const imageFiles = files.filter((file) => file.kind === "image" && file.media_id);
  const otherFiles = files.filter((file) => file.kind !== "image");
  const extraAssistantImages = imageFiles.filter(
    (file) => !content.includes(`/api/v1/media/${file.media_id}`),
  );

  return (
    <div
      data-role={role}
      className={cn(
        "chat-message rounded-lg px-2.5 py-2 text-sm",
        role === "user" ? "ml-6 bg-primary/10" : "larry-reply mr-4 bg-muted/60",
      )}
    >
      <p className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
        {role === "user" ? "You" : content || failed ? `${assistantName} replied` : assistantName}
      </p>
      {role === "assistant" && routeLabel ? (
        <p className="mb-1 text-[11px] text-muted-foreground" data-junior-route="">
          {routeLabel}
        </p>
      ) : null}
      {statusLine || (waiting && !failed && !content) ? (
        <p className="mb-1 flex items-center gap-2 text-sm font-medium" role="status">
          {waiting && !content ? <LoaderCircle className="size-4 animate-spin shrink-0" /> : null}
          <span>{statusLine || `${assistantName} is working…`}</span>
        </p>
      ) : null}
      {content ? (
        role === "assistant" ? (
          <div ref={bodyRef} className="note-md markdown" data-larry-reply-body={id} onClick={onReplyBodyClick} />
        ) : (
          <div ref={bodyRef} className="whitespace-pre-wrap">
            {content}
          </div>
        )
      ) : null}
      {role === "assistant"
        ? extraAssistantImages.map((file) => (
            <ChatPicture
              key={file.media_id}
              mediaId={file.media_id}
              url={file.url || `/api/v1/media/${file.media_id}`}
              alt={file.filename}
              contentType={file.content_type}
            />
          ))
        : null}
      {role === "user"
        ? imageFiles.map((file) => (
            <ChatPicture
              key={file.media_id}
              mediaId={file.media_id}
              url={file.url || `/api/v1/media/${file.media_id}`}
              alt={file.filename}
              contentType={file.content_type}
            />
          ))
        : null}
      {role === "user" && otherFiles.length ? (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {otherFiles.map((file) => (
            <li
              key={file.media_id}
              className="inline-flex max-w-full items-center gap-1 rounded-full border bg-background px-2 py-0.5 text-[11px]"
            >
              <Paperclip className="size-3 shrink-0 text-muted-foreground" aria-hidden="true" />
              <a href={file.url} target="_blank" rel="noreferrer" className="truncate hover:underline">
                {file.filename}
              </a>
              <span className="shrink-0 text-muted-foreground">{formatFileSize(file.byte_size)}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {failed && error ? (
        <p className="mt-1 text-xs text-destructive whitespace-pre-wrap">{error}</p>
      ) : null}
      {failed && onRetry ? (
        <Button size="xs" variant="outline" className="mt-2" disabled={busy} onClick={onRetry}>
          Retry
        </Button>
      ) : null}
      {content && role === "assistant" ? (
        <div className="mt-2 flex flex-wrap items-center gap-1">
          <Button
            size="xs"
            variant={listening ? "secondary" : "outline"}
            disabled={!ttsAvailable}
            onClick={(event) => onListen?.(id, event.currentTarget)}
          >
            <Volume2 className="size-3" />
            {listening ? "Playing…" : "Listen"}
          </Button>
          <Button
            size="xs"
            variant="outline"
            onClick={() => {
              void navigator.clipboard.writeText(content);
              toast.success("Copied full reply");
            }}
          >
            <Copy className="size-3" />
            Copy
          </Button>
          <Button size="xs" variant="outline" onClick={() => onAddToNotes(content)}>
            <NotebookPen className="size-3" />
            Add to notes
          </Button>
        </div>
      ) : null}
    </div>
  );
}
