"use client";

import { useState } from "react";
import { FileDown, LoaderCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import { sanitizeHtml } from "@/lib/format";
import { renderMarkdown } from "@/lib/markdown";
import type { GrokMessage } from "@/lib/types";
import { wordCount } from "@/lib/word-count";

const TRIM_TARGETS = [500, 750, 1000] as const;

export type SchoolToolSource = {
  messageId?: string | null;
  articleId?: string | null;
  conversationId?: string | null;
};

export function SchoolToolsBar({
  source,
  dest,
  folderId,
  persist = true,
  disabled = false,
  onAssistant,
  onSavedNote,
}: {
  source: SchoolToolSource;
  dest?: string;
  folderId?: string | null;
  persist?: boolean;
  disabled?: boolean;
  onAssistant?: (message: GrokMessage) => void;
  onSavedNote?: (noteId: string) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [trimTarget, setTrimTarget] = useState<(typeof TRIM_TARGETS)[number]>(500);
  const [quiz, setQuiz] = useState<{ questions: Array<{ n: string; q: string; a: string }>; questions_md: string; key_md: string } | null>(
    null,
  );
  const [showKey, setShowKey] = useState(false);
  const [localResult, setLocalResult] = useState<{ title: string; markdown: string; words: number } | null>(null);

  const body = {
    message_id: source.messageId || undefined,
    article_id: source.articleId || undefined,
    conversation_id: source.conversationId || undefined,
    persist,
  };

  function takeAssistant(message?: GrokMessage, markdown?: string, title?: string) {
    if (message) onAssistant?.(message);
    else if (markdown) setLocalResult({ title: title || "Result", markdown, words: wordCount(markdown) });
  }

  async function run(kind: string, work: () => Promise<void>) {
    if (disabled || busy) return;
    setBusy(kind);
    try {
      await work();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : `Could not run ${kind}.`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mt-2 space-y-2">
      <div className="flex flex-wrap items-center gap-1">
        <Button
          size="xs"
          variant="outline"
          disabled={disabled || Boolean(busy)}
          onClick={() =>
            void run("quiz", async () => {
              const result = await api.schoolQuiz({ ...body, persist: false });
              setShowKey(false);
              setQuiz({ questions: result.questions, questions_md: result.questions_md, key_md: result.key_md });
              takeAssistant(result.assistant_message, result.questions_md, "Quiz");
            })
          }
        >
          {busy === "quiz" ? <LoaderCircle className="size-3 animate-spin" /> : null}
          Quiz
        </Button>
        <Button
          size="xs"
          variant="outline"
          disabled={disabled || Boolean(busy)}
          onClick={() =>
            void run("apa", async () => {
              const result = await api.schoolApa(body);
              takeAssistant(result.assistant_message, result.markdown, "APA 7 citations");
              toast.success("Citations only — the paper body was not rewritten.");
            })
          }
        >
          {busy === "apa" ? <LoaderCircle className="size-3 animate-spin" /> : null}
          Fix citations only
        </Button>
        <label className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
          <span>Trim</span>
          <select
            aria-label="Trim word target"
            className="h-6 rounded-md border bg-background px-1 text-[11px]"
            value={trimTarget}
            disabled={disabled || Boolean(busy)}
            onChange={(event) => setTrimTarget(Number(event.target.value) as (typeof TRIM_TARGETS)[number])}
          >
            {TRIM_TARGETS.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <Button
            size="xs"
            variant="outline"
            disabled={disabled || Boolean(busy)}
            onClick={() =>
              void run("trim", async () => {
                const result = await api.schoolTrim({ ...body, target: trimTarget });
                takeAssistant(result.assistant_message, result.markdown, `Trim · ${result.word_count} words`);
                toast.success(`Trimmed to ${result.word_count} words (target ${result.target}).`);
              })
            }
          >
            {busy === "trim" ? <LoaderCircle className="size-3 animate-spin" /> : null}
            Trim
          </Button>
        </label>
        <Button
          size="xs"
          variant="outline"
          disabled={disabled || Boolean(busy)}
          onClick={() =>
            void run("grammar", async () => {
              const result = await api.schoolGrammar(body);
              takeAssistant(result.assistant_message, result.markdown, "Grammar");
              toast.success("Grammar marks are highlighted. Use Clean copy for Word.");
            })
          }
        >
          {busy === "grammar" ? <LoaderCircle className="size-3 animate-spin" /> : null}
          Grammar
        </Button>
      </div>
      {quiz ? (
        <div className="rounded-md border bg-background p-2 text-sm">
          <ol className="list-decimal space-y-1 pl-4">
            {quiz.questions.map((item) => (
              <li key={item.n}>{item.q}</li>
            ))}
          </ol>
          <div className="mt-2 flex flex-wrap gap-1">
            <Button size="xs" variant="outline" onClick={() => setShowKey((open) => !open)}>
              {showKey ? "Hide key" : "Show key"}
            </Button>
            <Button
              size="xs"
              variant="outline"
              disabled={Boolean(busy)}
              onClick={() =>
                void run("save-quiz", async () => {
                  const saved = await api.schoolQuizSave({
                    questions_md: quiz.questions_md,
                    key_md: quiz.key_md,
                    article_id: source.articleId || undefined,
                    destination: dest,
                    folder_id: folderId,
                  });
                  toast.success("Saved quiz as a child note.");
                  onSavedNote?.(saved.id);
                })
              }
            >
              Save quiz
            </Button>
          </div>
          {showKey ? (
            <ol className="mt-2 list-decimal space-y-1 pl-4 text-muted-foreground">
              {quiz.questions.map((item) => (
                <li key={`k-${item.n}`}>{item.a || "(no key)"}</li>
              ))}
            </ol>
          ) : null}
        </div>
      ) : null}
      {localResult ? (
        <div className="rounded-md border bg-background p-2">
          <p className="text-[11px] text-muted-foreground">
            {localResult.title} · {localResult.words} words
          </p>
          <div
            className="note-md markdown mt-1 max-h-64 overflow-auto text-sm"
            dangerouslySetInnerHTML={{ __html: sanitizeHtml(renderMarkdown(localResult.markdown)) }}
          />
          <Button
            size="xs"
            variant="outline"
            className="mt-2"
            onClick={() => {
              void downloadSchoolDocx(localResult.markdown);
            }}
          >
            <FileDown className="size-3" />
            Clean copy
          </Button>
        </div>
      ) : null}
    </div>
  );
}

async function downloadSchoolDocx(markdown: string) {
  try {
    const response = await fetch("/api/v1/school/docx?clean=true", {
      method: "POST",
      credentials: "include",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markdown }),
    });
    if (!response.ok) throw new Error("Could not download that Word file.");
    const buffer = await response.arrayBuffer();
    const blob = new Blob([buffer], {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "junior-note.docx";
    document.body.appendChild(link);
    link.click();
    window.setTimeout(() => {
      URL.revokeObjectURL(url);
      link.remove();
    }, 60_000);
    toast.success("Saved Word file");
  } catch (error) {
    toast.error(error instanceof Error ? error.message : "Could not download that Word file.");
  }
}
