"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { LoaderCircle, Maximize2, Minimize2, Send, Sparkles, X } from "lucide-react";
import { GrokChatMessage } from "@/components/grok-chat-message";
import { GrokListenStopBar } from "@/components/grok-message-listen";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import { DESTINATION_LABEL, type NoteDestination } from "@/lib/destinations";
import { cn } from "@/lib/utils";

type ChatRole = "user" | "assistant";
type ChatLine = { id: string; role: ChatRole; content: string };
type GrokNoteDestination = Extract<NoteDestination, "notes" | "schoolwork">;

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
  onStopArticleListen,
}: {
  articleId: string | null;
  articleTitle: string | null;
  articleGuid?: string | null;
  sourceRef?: string | null;
  articleBody?: string | null;
  onSavedNote: (noteId?: string, destination?: GrokNoteDestination) => Promise<void>;
  onStopArticleListen?: () => void;
}) {
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [pos, setPos] = useState({ x: 24, y: 24 });
  const [size, setSize] = useState(DEFAULT_PANEL);
  const [messages, setMessages] = useState<ChatLine[]>([]);
  const [draft, setDraft] = useState("");
  const [includeArticle, setIncludeArticle] = useState(true);
  const [noteDest, setNoteDest] = useState<GrokNoteDestination>("notes");
  const [busy, setBusy] = useState(false);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [ttsEnabled, setTtsEnabled] = useState(false);
  const [locked, setLocked] = useState(false);
  const [listening, setListening] = useState(false);
  const activeListenStopRef = useRef<(() => void) | null>(null);
  const dragRef = useRef<{ kind: "bubble" | "panel"; dx: number; dy: number } | null>(null);
  const movedRef = useRef(false);
  const resizeRef = useRef<{ x: number; y: number; w: number; h: number } | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

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
      .then((row) => {
        setEnabled(row.enabled);
        setLocked(Boolean(row.locked));
      })
      .catch(() => {
        setEnabled(false);
        setLocked(false);
      });
    api
      .tts()
      .then((row) => setTtsEnabled(row.enabled))
      .catch(() => setTtsEnabled(false));
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
    setIncludeArticle(Boolean(articleId));
  }, [articleId]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (!open) return;
      const target = event.target as HTMLElement | null;
      const inPanel = Boolean(panelRef.current && target && panelRef.current.contains(target));
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        if (listening && activeListenStopRef.current) {
          activeListenStopRef.current();
          return;
        }
        if (fullscreen) {
          setFullscreen(false);
          return;
        }
        setOpen(false);
        return;
      }
      if (event.key === "f" && !event.metaKey && !event.ctrlKey && !event.altKey && inPanel) {
        if (target?.closest("textarea, input, select, [contenteditable='true']")) return;
        event.preventDefault();
        setFullscreen((current) => !current);
      }
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [fullscreen, listening, open]);

  function handleActivateListen(stop: (() => void) | null) {
    activeListenStopRef.current = stop;
    setListening(Boolean(stop));
  }

  function closePanel() {
    setFullscreen(false);
    setOpen(false);
  }

  function toggleFullscreen() {
    setFullscreen((current) => !current);
  }

  const onPointerMove = useCallback((event: PointerEvent) => {
    if (fullscreen) return;
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
  }, [fullscreen, pos.x, pos.y]);

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
    if (!content || busy || !enabled) return;
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
      toast.error(detail.trim() || "Grok did not reply");
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
        await onSavedNote(articleId, noteDest);
        return;
      }
      const markdown = noteMarkdown(body, articleTitle, sourceRef || null);
      const article = await api.composeVaultNote(titleFromReply(body), markdown, ["grok"], noteDest);
      toast.success(`Saved to StoryKeep/${DESTINATION_LABEL[noteDest]}.`);
      await onSavedNote(article.id, noteDest);
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

  const panelLeft = Math.min(pos.x, window.innerWidth - size.w - 8);
  const panelTop = Math.min(pos.y, window.innerHeight - size.h - 8);

  const panel = (
    <div
      ref={panelRef}
      className={cn(
        "fixed flex flex-col overflow-hidden border bg-popover text-popover-foreground shadow-xl",
        fullscreen
          ? "inset-0 z-[90] h-[100dvh] w-[100vw] rounded-none"
          : "z-[80] rounded-xl",
      )}
      style={
        fullscreen
          ? undefined
          : {
              left: panelLeft,
              top: panelTop,
              width: size.w,
              height: size.h,
            }
      }
    >
      <div
        className={cn(
          "flex shrink-0 items-center gap-2 border-b px-3 py-2",
          fullscreen ? "cursor-default" : "cursor-grab active:cursor-grabbing",
        )}
        onPointerDown={(event) => {
          if (fullscreen) return;
          if ((event.target as HTMLElement).closest("button")) return;
          dragRef.current = { kind: "panel", dx: event.clientX - pos.x, dy: event.clientY - pos.y };
        }}
      >
        <Sparkles className="size-4 text-primary" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium leading-none">Grok</p>
          <p className="truncate text-[11px] text-muted-foreground">
            {includeArticle && articleTitle
              ? `Connected: ${articleTitle}`
              : articleTitle
                ? "General knowledge (article disconnected)"
                : "School coding help"}
          </p>
        </div>
        {fullscreen ? (
          <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => setFullscreen(false)}>
            Exit full screen
          </Button>
        ) : (
          <Button
            size="icon-xs"
            variant="ghost"
            onClick={toggleFullscreen}
            aria-label="Full screen"
            title="Full screen (f)"
          >
            <Maximize2 className="size-3.5" />
          </Button>
        )}
        <Button size="icon-xs" variant="ghost" onClick={closePanel} aria-label="Close chat">
          <X className="size-3.5" />
        </Button>
      </div>
      <label className="flex items-start gap-2 border-b px-3 py-2 text-xs leading-snug">
        <input
          type="checkbox"
          className="mt-0.5"
          checked={includeArticle}
          disabled={!articleId}
          onChange={(event) => setIncludeArticle(event.target.checked)}
        />
        <span>
          Connect to current article
          {!articleId ? (
            <span className="block text-[11px] text-muted-foreground">Open an article to connect Grok to it.</span>
          ) : includeArticle ? (
            <span className="block text-[11px] text-muted-foreground">Grok uses up to ~12k characters from this article.</span>
          ) : (
            <span className="block text-[11px] text-muted-foreground">
              Unchecked — Grok answers from general knowledge, not the article.
            </span>
          )}
        </span>
      </label>
      {listening ? <GrokListenStopBar onStop={() => activeListenStopRef.current?.()} /> : null}
      <div ref={listRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain px-3 py-3">
        {messages.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {includeArticle && articleId
              ? "Ask about this article or school coding. Try dictating a Python question."
              : "Ask for school coding help — explanations, debugging, or fenced code examples."}
          </p>
        ) : (
          messages.map((item) => (
            <GrokChatMessage
              key={item.id}
              id={item.id}
              role={item.role}
              content={item.content}
              ttsAvailable={ttsEnabled && !locked}
              noteDest={noteDest}
              showNoteDest={!(articleId && isComposedNote(articleGuid)) && item.role === "assistant"}
              onNoteDestChange={setNoteDest}
              onAddToNotes={(body) => void addToNotes(body)}
              onActivateListen={handleActivateListen}
              onStopArticleListen={onStopArticleListen}
            />
          ))
        )}
      </div>
      {locked ? (
        <p className="border-t px-3 py-2 text-xs text-muted-foreground">
          Demo accounts cannot use chat, dictation, or Listen.
        </p>
      ) : enabled === false ? (
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
          placeholder={
            includeArticle && articleId ? "Ask about this article or school coding…" : "Ask Grok for school coding help…"
          }
          disabled={!enabled}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
        />
        <Button type="submit" size="icon" disabled={busy || !draft.trim() || !enabled} aria-label="Send">
          {busy ? <LoaderCircle className="size-4 animate-spin" /> : <Send className="size-4" />}
        </Button>
      </form>
      {fullscreen ? null : (
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
      )}
    </div>
  );

  return createPortal(
    <>
      {!open ? bubble : null}
      {open ? panel : null}
    </>,
    document.body,
  );
}
