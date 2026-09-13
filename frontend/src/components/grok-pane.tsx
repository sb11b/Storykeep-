"use client";

import { useEffect, useRef, useState } from "react";
import { LoaderCircle, Send, X } from "lucide-react";
import { toast } from "sonner";
import { GrokChatMessage } from "@/components/grok-chat-message";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import { DESTINATION_LABEL, type NoteDestination } from "@/lib/destinations";
import { cn } from "@/lib/utils";

type ChatRole = "user" | "assistant";
export type ChatLine = { id: string; role: ChatRole; content: string };
export type GrokNoteDestination = Extract<NoteDestination, "notes" | "schoolwork">;

export type GrokPaneState = {
  id: string;
  conversationId: string | null;
  messages: ChatLine[];
  draft: string;
  includeArticle: boolean;
  noteDest: GrokNoteDestination;
};

export function createGrokPane(): GrokPaneState {
  return {
    id: crypto.randomUUID(),
    conversationId: null,
    messages: [],
    draft: "",
    includeArticle: false,
    noteDest: "notes",
  };
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

export function GrokPane({
  pane,
  label,
  compact,
  focused,
  canRemove,
  articleId,
  articleTitle,
  articleGuid,
  sourceRef,
  articleBody,
  enabled,
  ttsEnabled,
  locked,
  onFocus,
  onUpdate,
  onRemove,
  onSavedNote,
  onActivateListen,
  onStopArticleListen,
  onHistoryChanged,
}: {
  pane: GrokPaneState;
  label: string;
  compact?: boolean;
  focused?: boolean;
  canRemove?: boolean;
  articleId: string | null;
  articleTitle: string | null;
  articleGuid?: string | null;
  sourceRef?: string | null;
  articleBody?: string | null;
  enabled: boolean;
  ttsEnabled: boolean;
  locked: boolean;
  onFocus: () => void;
  onUpdate: (updater: (pane: GrokPaneState) => GrokPaneState) => void;
  onRemove?: () => void;
  onSavedNote: (noteId?: string, destination?: GrokNoteDestination) => Promise<void>;
  onActivateListen: (stop: (() => void) | null) => void;
  onStopArticleListen?: () => void;
  onHistoryChanged?: () => void;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const stopRef = useRef<() => void>(() => {});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [pane.messages]);

  async function send() {
    const content = pane.draft.trim();
    if (!content || busy || !enabled) return;
    const userLine: ChatLine = { id: crypto.randomUUID(), role: "user", content };
    const assistantId = crypto.randomUUID();
    const history = [...pane.messages, userLine];
    onUpdate((current) => ({
      ...current,
      draft: "",
      messages: [...history, { id: assistantId, role: "assistant", content: "" }],
    }));
    setBusy(true);
    try {
      await api.streamChat(
        {
          message: content,
          conversation_id: pane.conversationId,
          article_id: articleId,
          include_article: Boolean(pane.includeArticle && articleId),
        },
        (delta) => {
          onUpdate((current) => ({
            ...current,
            messages: current.messages.map((item) =>
              item.id === assistantId ? { ...item, content: item.content + delta } : item,
            ),
          }));
        },
        (meta) => {
          onUpdate((current) => {
            let next = current;
            if (meta.conversation_id && meta.conversation_id !== current.conversationId) {
              next = { ...next, conversationId: meta.conversation_id };
            }
            if (meta.user_message_id) {
              next = {
                ...next,
                messages: next.messages.map((item) =>
                  item.id === userLine.id ? { ...item, id: meta.user_message_id! } : item,
                ),
              };
            }
            if (meta.assistant_message_id) {
              next = {
                ...next,
                messages: next.messages.map((item) =>
                  item.id === assistantId ? { ...item, id: meta.assistant_message_id! } : item,
                ),
              };
            }
            return next;
          });
          if (meta.conversation_id || meta.assistant_message_id) onHistoryChanged?.();
        },
      );
    } catch (error) {
      const detail = error instanceof ApiError ? error.message : "Grok did not reply";
      onUpdate((current) => ({
        ...current,
        messages: current.messages.map((item) =>
          item.id === assistantId ? { ...item, content: item.content || detail } : item,
        ),
      }));
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
        await onSavedNote(articleId, pane.noteDest);
        return;
      }
      const markdown = noteMarkdown(body, articleTitle, sourceRef || null);
      const article = await api.composeVaultNote(titleFromReply(body), markdown, ["grok"], pane.noteDest);
      toast.success(`Saved to StoryKeep/${DESTINATION_LABEL[pane.noteDest]}.`);
      await onSavedNote(article.id, pane.noteDest);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not save that note");
    }
  }

  function patch(partial: Partial<GrokPaneState>) {
    onUpdate((current) => ({ ...current, ...partial }));
  }

  return (
    <div
      className={cn(
        "flex min-h-0 flex-col overflow-hidden",
        compact ? "h-full" : "min-h-0 flex-1",
        focused && compact ? "ring-1 ring-inset ring-primary/40" : "",
      )}
      onPointerDown={onFocus}
    >
      {compact ? (
        <div className="flex shrink-0 items-center gap-2 border-b px-2 py-1.5">
          <p className="min-w-0 flex-1 truncate text-xs font-medium">{label}</p>
          {canRemove ? (
            <Button size="icon-xs" variant="ghost" onClick={onRemove} aria-label={`Remove ${label}`}>
              <X className="size-3.5" />
            </Button>
          ) : null}
        </div>
      ) : null}
      <label className="flex shrink-0 items-start gap-2 border-b px-3 py-2 text-xs leading-snug">
        <input
          type="checkbox"
          className="mt-0.5"
          checked={pane.includeArticle}
          disabled={!articleId}
          onChange={(event) => patch({ includeArticle: event.target.checked })}
        />
        <span>
          Include current article
          {!articleId ? (
            <span className="block text-[11px] text-muted-foreground">Open an article to ground this pane.</span>
          ) : pane.includeArticle ? (
            <span className="block text-[11px] text-muted-foreground">Uses up to ~12k characters from this article.</span>
          ) : (
            <span className="block text-[11px] text-muted-foreground">Off — this pane uses its thread only.</span>
          )}
        </span>
      </label>
      <div ref={listRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain px-3 py-3">
        {pane.messages.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {pane.includeArticle && articleId
              ? "Ask about this article or school coding."
              : "Ask for school coding help — explanations, debugging, or fenced code."}
          </p>
        ) : (
          pane.messages.map((item) => (
            <GrokChatMessage
              key={item.id}
              id={item.id}
              role={item.role}
              content={item.content}
              ttsAvailable={ttsEnabled && !locked}
              noteDest={pane.noteDest}
              showNoteDest={!(articleId && isComposedNote(articleGuid)) && item.role === "assistant"}
              onNoteDestChange={(dest) => patch({ noteDest: dest })}
              onAddToNotes={(body) => void addToNotes(body)}
              onActivateListen={(stop) => {
                stopRef.current = stop ?? (() => {});
                onActivateListen(stop);
              }}
              onStopArticleListen={onStopArticleListen}
            />
          ))
        )}
      </div>
      {locked ? (
        <p className="shrink-0 border-t px-3 py-2 text-xs text-muted-foreground">
          Demo accounts cannot use chat, dictation, or Listen.
        </p>
      ) : enabled === false ? (
        <p className="shrink-0 border-t px-3 py-2 text-xs text-muted-foreground">
          Chat is off until XAI_API_KEY is set on Railway. It never lives in the browser.
        </p>
      ) : null}
      <form
        className="flex shrink-0 gap-2 border-t p-2"
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        <Textarea
          className="min-h-12 max-h-28 flex-1 resize-y rounded-md border bg-background px-2 py-1.5 text-sm"
          value={pane.draft}
          onChange={(event) => patch({ draft: event.target.value })}
          placeholder={
            pane.includeArticle && articleId ? "Ask about this article or school coding…" : "Ask Grok for school coding help…"
          }
          disabled={!enabled}
          onFocus={onFocus}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
        />
        <Button type="submit" size="icon" disabled={busy || !pane.draft.trim() || !enabled} aria-label="Send">
          {busy ? <LoaderCircle className="size-4 animate-spin" /> : <Send className="size-4" />}
        </Button>
      </form>
    </div>
  );
}
