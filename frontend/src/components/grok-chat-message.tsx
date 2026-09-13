"use client";

import { useEffect, useRef } from "react";
import { Copy, LoaderCircle, NotebookPen, Volume2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { onCodeCopyClick } from "@/lib/code-copy";
import { sanitizeHtml } from "@/lib/format";
import { renderMarkdown } from "@/lib/markdown";
import { DEFAULT_PANE_NAME } from "@/lib/grok-pane-name";
import { buildVisibleSpeechScript } from "@/lib/tts-visible";
import { cn } from "@/lib/utils";

export function GrokChatMessage({
  id,
  role,
  content,
  assistantName = DEFAULT_PANE_NAME,
  error,
  failed,
  waiting,
  busy,
  ttsAvailable,
  listening,
  activeWord,
  onRegisterBody,
  onListen,
  onAddToNotes,
  onRetry,
}: {
  id: string;
  role: "user" | "assistant";
  content: string;
  /** Custom pane name, e.g. "Larry (the asparagus)". */
  assistantName?: string;
  error?: string | null;
  failed?: boolean;
  waiting?: boolean;
  busy?: boolean;
  ttsAvailable: boolean;
  listening?: boolean;
  activeWord?: number | null;
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
      {content ? (
        role === "assistant" ? (
          <div ref={bodyRef} className="note-md markdown" data-larry-reply-body={id} onClick={onCodeCopyClick} />
        ) : (
          <div ref={bodyRef} className="whitespace-pre-wrap">
            {content}
          </div>
        )
      ) : waiting && !failed ? (
        <LoaderCircle className="size-4 animate-spin text-muted-foreground" />
      ) : null}
      {failed && error ? (
        <p className="mt-1 text-xs text-destructive whitespace-pre-wrap">{error}</p>
      ) : null}
      {failed && onRetry ? (
        <Button size="xs" variant="outline" className="mt-2" disabled={busy} onClick={onRetry}>
          Retry
        </Button>
      ) : null}
      {content && !failed && role === "assistant" ? (
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
