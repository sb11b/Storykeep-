"use client";

import { type MouseEvent, useEffect, useRef, useState } from "react";
import { Copy, Download, FileDown, LoaderCircle, NotebookPen, Paperclip, Volume2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { CorrectionCheck, DestinationSelect, FolderSelect } from "@/components/destination-controls";
import { MovableWindow } from "@/components/movable-window";
import { SchoolToolsBar } from "@/components/school-tools-bar";
import type { GrokMessage } from "@/lib/types";
import { onCodeCopyClick } from "@/lib/code-copy";
import { downloadChatPicture, resolveChatImageSrc } from "@/lib/chat-media-download";
import type { CustomNoteShelf, FilingDestination } from "@/lib/custom-note-shelves";
import { sanitizeHtml } from "@/lib/format";
import { renderMarkdown, chatArticleClick } from "@/lib/markdown";
import { DEFAULT_PANE_NAME } from "@/lib/grok-pane-name";
import {
  downloadChatMessageDocx,
  downloadReplyText,
  isPersistedMessageId,
  replyCopyText,
  replyHasWordBody,
  wordDownloadToast,
} from "@/lib/chat-message-docx";
import { formatFileSize, type LarryAttachment } from "@/lib/larry-attach";
import { hasGrammarMarks, wordCount } from "@/lib/word-count";
import type { Folder } from "@/lib/types";
import { buildVisibleSpeechScript } from "@/lib/tts-visible";
import { wordIndexFromSelection } from "@/lib/tts-words";
import { cn } from "@/lib/utils";

function toastDownloadError(error: unknown) {
  toast.error(error instanceof Error ? error.message : "Could not download that picture.");
}

function onReplyBodyClick(
  event: MouseEvent<HTMLElement>,
  onTtsWordPick?: (index: number) => void,
  onRun?: (code: string) => void,
  onOpenArticle?: (id: string) => void,
) {
  const articleClick = chatArticleClick(event.target);
  if (articleClick) {
    event.preventDefault();
    event.stopPropagation();
    if (articleClick.kind === "article") onOpenArticle?.(articleClick.id);
    return;
  }
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
  onCodeCopyClick(event, onRun);
  if (event.defaultPrevented) return;
  const wordEl = (event.target as HTMLElement).closest("[data-tts-word]");
  if (wordEl instanceof HTMLElement) {
    const index = Number(wordEl.getAttribute("data-tts-word"));
    if (Number.isFinite(index)) onTtsWordPick?.(index);
  }
}

function ChatPicture({
  mediaId,
  url,
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

export type AddToNotesPayload = {
  content: string;
  dest: FilingDestination;
  folderId: string | null;
  isCorrection: boolean;
};

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
  includeChip,
  onNextChunk,
  wordEnabled = true,
  noteDest = "notes",
  noteFolderId = null,
  folders = [],
  customShelves = [],
  onCreateNoteShelf,
  onCreateFolder,
  onRememberFiling,
  onRegisterBody,
  onListen,
  onTtsWordPick,
  onAddToNotes,
  onApplyToNote,
  onRetry,
  conversationId = null,
  articleId = null,
  schoolEnabled = true,
  onSchoolAssistant,
  onSchoolSavedNote,
  onRunSnippet,
  onOpenArticle,
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
  /** Auto routing, e.g. "4.6 · low". Not inside the Listen body. */
  routeLabel?: string | null;
  includeChip?: string | null;
  onNextChunk?: () => void;
  wordEnabled?: boolean;
  noteDest?: FilingDestination;
  noteFolderId?: string | null;
  folders?: Folder[];
  customShelves?: CustomNoteShelf[];
  onCreateNoteShelf?: () => void | Promise<void>;
  onCreateFolder?: (shelf: FilingDestination) => void;
  onRememberFiling?: (dest: FilingDestination, folderId: string | null) => void;
  onRegisterBody?: (messageId: string, element: HTMLElement | null) => void;
  /** `trigger` is the Listen button, so the reply body is one closest() away. */
  onListen?: (messageId: string, trigger: HTMLElement) => void;
  onTtsWordPick?: (messageId: string, wordIndex: number) => void;
  onAddToNotes: (payload: AddToNotesPayload) => void;
  onApplyToNote?: () => void;
  onRetry?: () => void;
  conversationId?: string | null;
  articleId?: string | null;
  schoolEnabled?: boolean;
  onSchoolAssistant?: (message: GrokMessage) => void;
  onSchoolSavedNote?: (noteId: string) => void;
  onRunSnippet?: (messageId: string, code: string) => void;
  onOpenArticle?: (id: string) => void;
}) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const [savingWord, setSavingWord] = useState(false);
  const [savingText, setSavingText] = useState<"md" | "txt" | null>(null);
  const [filing, setFiling] = useState(false);
  const [draft, setDraft] = useState(content);
  const [dest, setDest] = useState<FilingDestination>(noteDest);
  const [folderId, setFolderId] = useState<string | null>(noteFolderId);
  const [isCorrection, setIsCorrection] = useState(false);
  const [savingNote, setSavingNote] = useState(false);
  const [savingClean, setSavingClean] = useState(false);
  const words = role === "assistant" && content ? wordCount(replyCopyText(content)) : 0;
  const marked = role === "assistant" && hasGrammarMarks(content);
  const hasWordBody = replyHasWordBody(content);
  const showWord =
    wordEnabled &&
    role === "assistant" &&
    hasWordBody &&
    !failed &&
    !waiting &&
    isPersistedMessageId(id);

  async function saveWord(clean = false) {
    if (!showWord) return;
    const setBusy = clean ? setSavingClean : setSavingWord;
    setBusy(true);
    try {
      await downloadChatMessageDocx(id, clean ? { clean: true } : undefined);
      toast.success(clean ? "Saved clean Word file" : "Saved Word file");
    } catch (error) {
      toast.error(wordDownloadToast(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (filing) return;
    setDest(noteDest);
    setFolderId(noteFolderId);
  }, [filing, noteDest, noteFolderId]);

  useEffect(() => {
    if (!filing) return;
    setDraft(replyCopyText(content));
  }, [filing, content]);

  useEffect(() => {
    const root = bodyRef.current;
    if (!root || role !== "assistant" || !content) return;
    root.innerHTML = sanitizeHtml(renderMarkdown(replyCopyText(content)));
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
  const otherFiles = files.filter((file) => file.kind !== "image" && file.media_id);
  const extraAssistantImages = imageFiles.filter(
    (file) => !content.includes(`/api/v1/media/${file.media_id}`),
  );

  return (
    <div
      data-role={role}
      data-message-id={id}
      className={cn(
        "chat-message rounded-lg px-2.5 py-2 text-sm",
        role === "user" ? "ml-6 bg-primary/10" : "larry-reply mr-4 bg-muted/60",
      )}
    >
      <p className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
        {role === "user" ? "You" : content || failed ? `${assistantName} replied` : assistantName}
      </p>
      {role === "assistant" && routeLabel ? (
        <p className="mb-1 text-[11px] text-muted-foreground" data-junior-route="" data-junior-spend="">
          {routeLabel}
        </p>
      ) : null}
      {includeChip ? (
        <p className="mb-1 inline-flex max-w-full items-center rounded-full border bg-background px-2 py-0.5 text-[11px] text-muted-foreground">
          {includeChip}
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
          <div
            ref={bodyRef}
            className="note-md markdown"
            data-larry-reply-body={id}
            onClick={(event) =>
              onReplyBodyClick(
                event,
                (index) => onTtsWordPick?.(id, index),
                (code) => onRunSnippet?.(id, code),
                onOpenArticle,
              )
            }
            onMouseUp={(event) => {
              const index = wordIndexFromSelection(event.currentTarget);
              if (index != null) onTtsWordPick?.(id, index);
            }}
          />
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
        <ul className="mt-2 space-y-2">
          {otherFiles.map((file) => {
            const extract = (file.extract_text || "").trim();
            const failed = /couldn['’]t read that Word file/i.test(extract);
            return (
              <li key={file.media_id} className="space-y-1">
                <div className="inline-flex max-w-full items-center gap-1 rounded-full border bg-background px-2 py-0.5 text-[11px]">
                  <Paperclip className="size-3 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <a href={file.url} target="_blank" rel="noreferrer" className="truncate hover:underline">
                    {file.filename}
                  </a>
                  <span className="shrink-0 font-mono text-[10px] text-muted-foreground" title={file.media_id}>
                    {file.media_id}
                  </span>
                  <span className="shrink-0 text-muted-foreground">{formatFileSize(file.byte_size)}</span>
                </div>
                {extract ? (
                  <div
                    className={
                      failed
                        ? "whitespace-pre-wrap text-sm text-destructive"
                        : "whitespace-pre-wrap text-sm text-foreground"
                    }
                  >
                    {extract}
                  </div>
                ) : null}
              </li>
            );
          })}
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
        <div className="mt-2 flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-1">
            <Button
              type="button"
              size="xs"
              variant={listening ? "secondary" : "outline"}
              disabled={!ttsAvailable}
              onClick={(event) => onListen?.(id, event.currentTarget)}
            >
              <Volume2 className="size-3" />
              {listening ? "Playing…" : "Listen"}
            </Button>
            {onNextChunk ? (
              <Button type="button" size="xs" variant="secondary" disabled={busy} onClick={onNextChunk}>
                Next chunk
              </Button>
            ) : null}
          </div>
          <div className="reply-actions flex flex-wrap items-center gap-1">
            {showWord ? (
              <Button
                type="button"
                size="xs"
                variant="outline"
                aria-busy={savingWord}
                disabled={savingWord}
                onClick={() => void saveWord(false)}
              >
                {savingWord ? <LoaderCircle className="size-3 animate-spin" /> : <FileDown className="size-3" />}
                Word
              </Button>
            ) : null}
            <Button
              type="button"
              size="xs"
              variant="outline"
              onClick={() => {
                void navigator.clipboard.writeText(replyCopyText(content));
                toast.success("Copied full reply");
              }}
            >
              <Copy className="size-3" />
              Copy
            </Button>
            <Button
              type="button"
              size="xs"
              variant={filing ? "secondary" : "outline"}
              onClick={() => {
                setDest(noteDest);
                setFolderId(noteFolderId);
                setIsCorrection(false);
                setFiling((open) => !open);
              }}
            >
              <NotebookPen className="size-3" />
              Add to notes
            </Button>
            {onApplyToNote ? (
              <Button type="button" size="xs" variant="secondary" disabled={busy} onClick={() => onApplyToNote()}>
                Apply to note
              </Button>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-1">
            <Button
              type="button"
              size="xs"
              variant="outline"
              disabled={!content || savingText !== null}
              onClick={() => {
                try {
                  setSavingText("md");
                  downloadReplyText(content, "md");
                  toast.success("Saved Markdown");
                } catch (error) {
                  toast.error(error instanceof Error ? error.message : "Could not save that file.");
                } finally {
                  setSavingText(null);
                }
              }}
            >
              .md
            </Button>
            <Button
              type="button"
              size="xs"
              variant="outline"
              disabled={!content || savingText !== null}
              onClick={() => {
                try {
                  setSavingText("txt");
                  downloadReplyText(content, "txt");
                  toast.success("Saved text file");
                } catch (error) {
                  toast.error(error instanceof Error ? error.message : "Could not save that file.");
                } finally {
                  setSavingText(null);
                }
              }}
            >
              .txt
            </Button>
            {marked && showWord ? (
              <Button
                type="button"
                size="xs"
                variant="outline"
                aria-busy={savingClean}
                disabled={savingClean}
                onClick={() => void saveWord(true)}
              >
                {savingClean ? <LoaderCircle className="size-3 animate-spin" /> : <FileDown className="size-3" />}
                Clean copy
              </Button>
            ) : null}
            {words ? (
              <span className="ml-1 text-[11px] text-muted-foreground" data-word-count={words}>
                {words} words
              </span>
            ) : null}
          </div>
        </div>
      ) : null}
      {content && role === "assistant" && !failed && !waiting && schoolEnabled ? (
        <SchoolToolsBar
          source={{ messageId: id, articleId, conversationId }}
          dest={noteDest}
          folderId={noteFolderId}
          persist={Boolean(conversationId)}
          onAssistant={onSchoolAssistant}
          onSavedNote={onSchoolSavedNote}
        />
      ) : null}
      {content && role === "assistant" ? (
        <MovableWindow open={filing} title="Add to notes" onClose={() => setFiling(false)}>
          <div className="flex flex-col gap-1.5">
            <div className="flex flex-wrap items-center gap-1.5">
              <DestinationSelect
                value={dest}
                onChange={(next) => {
                  if (!next) return;
                  setDest(next);
                  setFolderId(null);
                  onRememberFiling?.(next, null);
                }}
                customShelves={customShelves}
                onCreateShelf={onCreateNoteShelf}
                className="max-w-[8.5rem] text-[11px]"
              />
              <FolderSelect
                shelf={dest}
                folders={folders}
                value={folderId}
                onChange={(next) => {
                  setFolderId(next);
                  onRememberFiling?.(dest, next);
                }}
                onCreateFolder={() => onCreateFolder?.(dest)}
                className="max-w-[8.5rem] text-[11px]"
              />
            </div>
            <textarea
              aria-label="Note text"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              className="min-h-[7rem] w-full resize-y rounded-md border border-input bg-background px-2 py-1.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            />
            <CorrectionCheck checked={isCorrection} onChange={setIsCorrection} />
            <div className="flex flex-wrap gap-1">
              <Button
                size="xs"
                disabled={savingNote || !draft.trim()}
                onClick={() => {
                  setSavingNote(true);
                  onRememberFiling?.(dest, folderId);
                  onAddToNotes({ content: draft, dest, folderId, isCorrection });
                  setFiling(false);
                  setSavingNote(false);
                }}
              >
                Save
              </Button>
              <Button size="xs" variant="outline" onClick={() => setFiling(false)}>
                Cancel
              </Button>
            </div>
          </div>
        </MovableWindow>
      ) : null}
    </div>
  );
}
