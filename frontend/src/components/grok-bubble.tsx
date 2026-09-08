"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Copy, LoaderCircle, Maximize2, NotebookPen, Send, Sparkles, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import { renderMarkdown } from "@/lib/markdown";
import { cn } from "@/lib/utils";

type ChatRole = "user" | "assistant";
type ChatLine = { id: string; role: ChatRole; content: string };

const BUBBLE_KEY = "storykeep-grok-bubble";
const PANEL_KEY = "storykeep-grok-panel";
const DEFAULT_PANEL = { w: 380, h: 520 };

function loadPoint(key: string, fallback: { x: number; y: number }) {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as { x?: number; y?: number };
    if (typeof parsed.x === "number" && typeof parsed.y === "number") return { x: parsed.x, y: parsed.y };
  } catch {
    /* ignore */
  }
  return fallback;
}

function loadSize() {
  try {
    const raw = window.localStorage.getItem(PANEL_KEY);
    if (!raw) return DEFAULT_PANEL;
    const parsed = JSON.parse(raw) as { w?: number; h?: number };
    if (typeof parsed.w === "number" && typeof parsed.h === "number") {
      return { w: Math.max(300, parsed.w), h: Math.max(320, parsed.h) };
    }
  } catch {
    /* ignore */
  }
  return DEFAULT_PANEL;
}

function isComposedNote(guid?: string | null) {
  return Boolean(guid?.startsWith("storykeep-note:"));
}

function titleFromReply(reply: string) {
  const line = reply.trim().split("\n").find((item) => item.trim()) || "Grok note";
  return line.replace(/^#+\s*/, "").replace(/^["“]+|["”]+$/g, "").slice(0, 80) || "Grok note";
}

function noteMarkdown(reply: string, articleTitle: string | null, sourceRef: string | null) {
  const heading = titleFromReply(reply);
  const source = articleTitle || sourceRef;
  if (!source) return `# ${heading}\n\n${reply.trim()}`;
  return `# ${heading}\n\nAbout: ${source}${sourceRef ? `\nPath: ${sourceRef}` : ""}\n\n${reply.trim()}`;
}

export function GrokBubble({
  articleId,
  articleTitle,
  articleGuid,
  sourceRef,
  articleBody,
  onSavedNote,
}: {
  articleId: string | null;
  articleTitle: string | null;
  articleGuid?: string | null;
  sourceRef?: string | null;
  articleBody?: string | null;
  onSavedNote: (noteId?: string) => Promise<void>;
}) {
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ x: 24, y: 24 });
  const [size, setSize] = useState(DEFAULT_PANEL);
  const [messages, setMessages] = useState<ChatLine[]>([]);
  const [draft, setDraft] = useState("");
  const [includeArticle, setIncludeArticle] = useState(true);
  const [busy, setBusy] = useState(false);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const dragRef = useRef<{ kind: "bubble" | "panel"; dx: number; dy: number } | null>(null);
  const movedRef = useRef(false);
  const resizeRef = useRef<{ x: number; y: number; w: number; h: number } | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMounted(true);
    const fallback = {
      x: Math.max(16, window.innerWidth - 72),
      y: Math.max(16, window.innerHeight - 72),
    };
    setPos(loadPoint(BUBBLE_KEY, fallback));
    setSize(loadSize());
    api
      .chatStatus()
      .then((row) => setEnabled(row.enabled))
      .catch(() => setEnabled(false));
  }, []);

  useEffect(() => {
    if (!mounted) return;
    window.localStorage.setItem(BUBBLE_KEY, JSON.stringify(pos));
  }, [mounted, pos]);

  useEffect(() => {
    if (!mounted) return;
    window.localStorage.setItem(PANEL_KEY, JSON.stringify(size));
  }, [mounted, size]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, open]);

  useEffect(() => {
    if (articleId) setIncludeArticle(true);
  }, [articleId]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape" || !open) return;
      event.preventDefault();
      event.stopPropagation();
      setOpen(false);
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open]);

  const onPointerMove = useCallback((event: PointerEvent) => {
    if (resizeRef.current) {
      const nextW = Math.min(window.innerWidth - 24, Math.max(300, resizeRef.current.w + (event.clientX - resizeRef.current.x)));
      const nextH = Math.min(window.innerHeight - 24, Math.max(320, resizeRef.current.h + (event.clientY - resizeRef.current.y)));
      setSize({ w: nextW, h: nextH });
      return;
    }
    const drag = dragRef.current;
    if (!drag) return;
    const x = Math.min(window.innerWidth - 48, Math.max(8, event.clientX - drag.dx));
    const y = Math.min(window.innerHeight - 48, Math.max(8, event.clientY - drag.dy));
    if (Math.abs(x - pos.x) > 3 || Math.abs(y - pos.y) > 3) movedRef.current = true;
    setPos({ x, y });
  }, [pos.x, pos.y]);

  const onPointerUp = useCallback(() => {
    dragRef.current = null;
    resizeRef.current = null;
  }, []);

  useEffect(() => {
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };
  }, [onPointerMove, onPointerUp]);

  async function send() {
    const content = draft.trim();
    if (!content || busy) return;
    const userLine: ChatLine = { id: crypto.randomUUID(), role: "user", content };
    const assistantId = crypto.randomUUID();
    const nextMessages = [...messages, userLine];
    setMessages([...nextMessages, { id: assistantId, role: "assistant", content: "" }]);
    setDraft("");
    setBusy(true);
    try {
      await api.streamChat(
        {
          messages: nextMessages.map((item) => ({ role: item.role, content: item.content })),
          article_id: articleId,
          include_article: Boolean(includeArticle && articleId),
        },
        (delta) => {
          setMessages((current) =>
            current.map((item) => (item.id === assistantId ? { ...item, content: item.content + delta } : item)),
          );
        },
      );
    } catch (error) {
      const detail = error instanceof ApiError ? error.message : "Grok did not reply";
      setMessages((current) =>
        current.map((item) => (item.id === assistantId ? { ...item, content: item.content || detail } : item)),
      );
      toast.error(detail);
    } finally {
      setBusy(false);
    }
  }

  async function addToNotes(content: string) {
    const body = content.trim();
    if (!body) return;
    try {
      if (articleId && isComposedNote(articleGuid)) {
        const existing = (articleBody || "").trim();
        const next = existing ? `${existing}\n\n## Grok\n\n${body}` : body;
        await api.updateComposedNote(articleId, articleTitle || titleFromReply(body), next);
        toast.success("Appended to this StoryKeep addition. The vault original was not touched.");
        await onSavedNote(articleId);
        return;
      }
      const markdown = noteMarkdown(body, articleTitle, sourceRef || null);
      const article = await api.composeVaultNote(titleFromReply(body), markdown, ["grok"], "additions");
      toast.success("Saved in StoryKeep/Additions. It will be in the next Obsidian pack.");
      await onSavedNote(article.id);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not save that note");
    }
  }

  if (!mounted) return null;

  const bubble = (
    <button
      type="button"
      className="fixed z-[80] flex size-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg ring-1 ring-black/10"
      style={{ left: pos.x, top: pos.y }}
      aria-label="Open Grok chat"
      onPointerDown={(event) => {
        movedRef.current = false;
        dragRef.current = { kind: "bubble", dx: event.clientX - pos.x, dy: event.clientY - pos.y };
      }}
      onClick={() => {
        if (movedRef.current) return;
        setOpen(true);
      }}
    >
      <Sparkles className="size-5" />
    </button>
  );

  const panel = (
    <div
      className="fixed z-[80] flex flex-col overflow-hidden rounded-xl border bg-popover text-popover-foreground shadow-xl"
      style={{ left: Math.min(pos.x, window.innerWidth - size.w - 8), top: Math.min(pos.y, window.innerHeight - size.h - 8), width: size.w, height: size.h }}
    >
      <div
        className="flex cursor-grab items-center gap-2 border-b px-3 py-2 active:cursor-grabbing"
        onPointerDown={(event) => {
          if ((event.target as HTMLElement).closest("button")) return;
          dragRef.current = { kind: "panel", dx: event.clientX - pos.x, dy: event.clientY - pos.y };
        }}
      >
        <Sparkles className="size-4 text-primary" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium leading-none">Grok</p>
          <p className="truncate text-[11px] text-muted-foreground">
            {includeArticle && articleTitle ? `Reading: ${articleTitle}` : "Archive assistant"}
          </p>
        </div>
        <Button size="icon-xs" variant="ghost" onClick={() => setOpen(false)} aria-label="Close chat">
          <X className="size-3.5" />
        </Button>
      </div>
      <label className="flex items-center gap-2 border-b px-3 py-2 text-xs">
        <input
          type="checkbox"
          checked={includeArticle}
          disabled={!articleId}
          onChange={(event) => setIncludeArticle(event.target.checked)}
        />
        Include current article
      </label>
      <div ref={listRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain px-3 py-3">
        {messages.length === 0 ? (
          <p className="text-sm text-muted-foreground">Ask about this article or anything in your archive context.</p>
        ) : (
          messages.map((item) => (
            <div key={item.id} className={cn("rounded-lg px-2.5 py-2 text-sm", item.role === "user" ? "ml-6 bg-primary/10" : "mr-4 bg-muted/60")}>
              <p className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
                {item.role === "user" ? "You" : "Grok"}
              </p>
              {item.content ? (
                <div className="note-md" dangerouslySetInnerHTML={{ __html: renderMarkdown(item.content) }} />
              ) : (
                <LoaderCircle className="size-4 animate-spin text-muted-foreground" />
              )}
              {item.role === "assistant" && item.content ? (
                <div className="mt-2 flex flex-wrap gap-1">
                  <Button
                    size="xs"
                    variant="outline"
                    onClick={() => {
                      void navigator.clipboard.writeText(item.content);
                      toast.success("Copied");
                    }}
                  >
                    <Copy className="size-3" />
                    Copy
                  </Button>
                  <Button size="xs" variant="outline" onClick={() => void addToNotes(item.content)}>
                    <NotebookPen className="size-3" />
                    Add to notes
                  </Button>
                </div>
              ) : null}
            </div>
          ))
        )}
      </div>
      {enabled === false ? (
        <p className="border-t px-3 py-2 text-xs text-muted-foreground">
          Chat is off until XAI_API_KEY is set on Railway. It never lives in the browser.
        </p>
      ) : null}
      <form
        className="flex gap-2 border-t p-2"
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        <Textarea
          className="min-h-12 max-h-28 flex-1 resize-y rounded-md border bg-background px-2 py-1.5 text-sm"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={articleId ? "Ask about this article…" : "Ask Grok…"}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
        />
        <Button type="submit" size="icon" disabled={busy || !draft.trim() || enabled === false} aria-label="Send">
          {busy ? <LoaderCircle className="size-4 animate-spin" /> : <Send className="size-4" />}
        </Button>
      </form>
      <button
        type="button"
        className="absolute bottom-1 right-1 size-4 cursor-se-resize"
        aria-label="Resize chat"
        onPointerDown={(event) => {
          event.preventDefault();
          resizeRef.current = { x: event.clientX, y: event.clientY, w: size.w, h: size.h };
        }}
      >
        <Maximize2 className="size-3 text-muted-foreground" />
      </button>
    </div>
  );

  return createPortal(open ? panel : bubble, document.body);
}
