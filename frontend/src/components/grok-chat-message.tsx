"use client";

import { useEffect, useRef, useState } from "react";
import { Copy, LoaderCircle, NotebookPen } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { onCodeCopyClick } from "@/lib/code-copy";
import { DESTINATION_LABEL, type NoteDestination } from "@/lib/destinations";
import { sanitizeHtml } from "@/lib/format";
import { renderMarkdown } from "@/lib/markdown";
import { cn } from "@/lib/utils";
import { GrokListenBar, useGrokMessageListen } from "@/components/grok-message-listen";
import { buildVisibleSpeechScript } from "@/lib/tts-visible";

type GrokNoteDestination = Extract<NoteDestination, "notes" | "schoolwork">;

export function GrokChatMessage({
  id,
  role,
  content,
  error,
  failed,
  waiting,
  busy,
  ttsAvailable,
  noteDest,
  showNoteDest,
  onNoteDestChange,
  onAddToNotes,
  onRetry,
  onActivateListen,
  onStopArticleListen,
}: {
  id: string;
  role: "user" | "assistant";
  content: string;
  error?: string | null;
  failed?: boolean;
  waiting?: boolean;
  busy?: boolean;
  ttsAvailable: boolean;
  noteDest: GrokNoteDestination;
  showNoteDest: boolean;
  onNoteDestChange: (dest: GrokNoteDestination) => void;
  onAddToNotes: (content: string) => void;
  onRetry?: () => void;
  onActivateListen: (stop: (() => void) | null) => void;
  onStopArticleListen?: () => void;
}) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const stopRef = useRef<() => void>(() => {});
  const [activeWord, setActiveWord] = useState<number | null>(null);

  useEffect(() => {
    const root = bodyRef.current;
    if (!root || role !== "assistant" || !content) return;
    root.innerHTML = sanitizeHtml(renderMarkdown(content));
    buildVisibleSpeechScript(root);
  }, [content, role]);

  const listen = useGrokMessageListen({
    messageId: id,
    bodyRef,
    disabled: !ttsAvailable || !content.trim(),
    onCue: setActiveWord,
    onPlayingChange: (active) => {
      if (active) {
        onStopArticleListen?.();
        onActivateListen(() => stopRef.current());
      } else {
        onActivateListen(null);
      }
    },
  });
  stopRef.current = listen.stop;

  useEffect(() => {
    const root = bodyRef.current;
    if (!root) return;
    root.querySelectorAll(".tts-word-active").forEach((node) => node.classList.remove("tts-word-active"));
    if (activeWord == null) return;
    const current = root.querySelector(`[data-tts-word="${activeWord}"]`);
    if (current instanceof HTMLElement) {
      current.classList.add("tts-word-active");
      current.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [activeWord, content]);

  return (
    <div className={cn("rounded-lg px-2.5 py-2 text-sm", role === "user" ? "ml-6 bg-primary/10" : "mr-4 bg-muted/60")}>
      <p className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">{role === "user" ? "You" : "Grok"}</p>
      {content ? (
        role === "assistant" ? (
          <div ref={bodyRef} className="note-md" onClick={onCodeCopyClick} />
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
      {content && !failed ? (
        <div className="mt-2 flex flex-wrap items-center gap-1">
          {role === "assistant" ? (
            <GrokListenBar
              phase={listen.phase}
              disabled={!ttsAvailable}
              speed={listen.speed}
              onListen={listen.listen}
              onPause={listen.pause}
              onStop={listen.stop}
              onSpeedChange={listen.changeSpeed}
            />
          ) : null}
          {role === "assistant" ? (
            <>
              <Button
                size="xs"
                variant="outline"
                onClick={() => {
                  void navigator.clipboard.writeText(content);
                  toast.success("Copied full reply");
                }}
              >
                <Copy className="size-3" />
                Copy all
              </Button>
              <Button size="xs" variant="outline" onClick={() => onAddToNotes(content)}>
                <NotebookPen className="size-3" />
                Add to notes
              </Button>
              {showNoteDest ? (
                <select
                  aria-label="Save destination"
                  value={noteDest}
                  onChange={(event) => onNoteDestChange(event.target.value as GrokNoteDestination)}
                  className="h-7 rounded-md border border-input bg-background px-2 text-[0.72rem] outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                >
                  {(["notes", "schoolwork"] as const).map((dest) => (
                    <option key={dest} value={dest}>
                      {DESTINATION_LABEL[dest]}
                    </option>
                  ))}
                </select>
              ) : null}
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
