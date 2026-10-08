"use client";

import type { Dispatch, SetStateAction } from "react";
import { ApiError, api } from "@/lib/api";
import type { Folder } from "@/lib/types";
import { filingFromDropdowns, saveLastFiling } from "@/lib/last-filing";
import { folderById, matchFolderByName } from "@/lib/folders";
import {
  destinationLabel,
  type CustomNoteShelf,
  type FilingDestination,
} from "@/lib/custom-note-shelves";
import { folderNameForFinishedChat, shelfForFinishedChat } from "@/lib/chat-filing";

type NoteFile = {
  media_id: string;
  filename: string;
  content_type: string;
  kind: "image" | "file";
  url: string;
  byte_size?: number | null;
  extract_text?: string | null;
};

type FilingMessage = {
  id: string;
  role: string;
  content: string;
  files?: NoteFile[];
  includeMode?: string | null;
  includeHeading?: string | null;
  includeOffset?: number;
};

type NoteFilingPane = {
  displayName: string;
  conversationId: string | null;
  messages: FilingMessage[];
  includeMode: string;
  includeHeading: string | null;
  includeOffset: number;
  workingNoteId: string | null;
  savedNoteId: string | null;
  noteDest: FilingDestination;
  noteFolderId: string | null;
  conversationTitle: string | null;
};

type NoteFilingPatch = {
  noteDest: FilingDestination;
  noteFolderId: string | null;
  savedNoteId: string | null;
  conversationTitle: string | null;
};

type AddToNotesPayload = {
  content: string;
  dest: FilingDestination;
  folderId: string | null;
  isCorrection: boolean;
};

type ThreadTurn = { role: string; content: string };

type NoteToast = {
  success: (message: string) => void;
  error: (message: string) => void;
};

type UseNoteFilingOptions = {
  folders: Folder[];
  setFolders: Dispatch<SetStateAction<Folder[]>>;
  patch: (partial: Partial<NoteFilingPatch>) => void;
  onSavedNote: (noteId?: string, destination?: FilingDestination, folderId?: string | null) => Promise<void>;
  pane: NoteFilingPane;
  articleTitle: string | null;
  sourceRef?: string | null;
  label: string;
  customShelves: CustomNoteShelf[];
  shelfSelectId: string;
  savingChat: boolean;
  setSavingChat: Dispatch<SetStateAction<boolean>>;
  busy: boolean;
  persist: boolean;
  toast: NoteToast;
  attachmentMarkdown: (files: NoteFile[]) => string;
  saveableThreadTurns: (turns: ThreadTurn[]) => ThreadTurn[];
  threadNoteTitle: (opts: { conversationTitle?: string | null; firstUserLine?: string | null }) => string;
  threadNoteMarkdown: (
    turns: ThreadTurn[],
    opts?: { title?: string; userName?: string; assistantName?: string },
  ) => string;
  isNoteShrinkMessage: (message: string) => boolean;
  toastErrorFromUnknown: (error: unknown, fallback: string) => void;
};

function titleFromReply(reply: string, assistantName: string) {
  const fallback = `${assistantName} note`;
  const line = reply.trim().split("\n").find((item) => item.trim()) || fallback;
  return line.replace(/^#+\s*/, "").replace(/^["“]+|["”]+$/g, "").slice(0, 80) || fallback;
}

function noteMarkdown(reply: string, articleTitle: string | null, sourceRef: string | null, assistantName: string) {
  const heading = titleFromReply(reply, assistantName);
  const source = articleTitle || sourceRef;
  if (!source) return `# ${heading}\n\n${reply.trim()}`;
  return `# ${heading}\n\nAbout: ${source}${sourceRef ? `\nPath: ${sourceRef}` : ""}\n\n${reply.trim()}`;
}

export function useNoteFiling({
  folders,
  setFolders,
  patch,
  onSavedNote,
  pane,
  articleTitle,
  sourceRef,
  label,
  customShelves,
  shelfSelectId,
  savingChat,
  setSavingChat,
  busy,
  persist,
  toast,
  attachmentMarkdown,
  saveableThreadTurns,
  threadNoteTitle,
  threadNoteMarkdown,
  isNoteShrinkMessage,
  toastErrorFromUnknown,
}: UseNoteFilingOptions) {
  async function addToNotes(payload: AddToNotesPayload, assistantId?: string) {
    const body = payload.content.trim();
    if (!body) return;
    const filing = filingFromDropdowns(payload.dest, payload.folderId, folders);
    const dest = filing.dest;
    const folderId = filing.folderId;
    saveLastFiling(dest, folderId);
    patch({ noteDest: dest, noteFolderId: folderId });
    const fromUser =
      assistantId != null
        ? (() => {
            const index = pane.messages.findIndex((item) => item.id === assistantId);
            const prior = index > 0 ? pane.messages[index - 1] : null;
            return prior?.role === "user" ? prior.files || [] : [];
          })()
        : [];
    const extra = attachmentMarkdown(fromUser);
    try {
      const markdown = extra
        ? `${noteMarkdown(body, articleTitle, sourceRef || null, label)}\n\n${extra}`
        : noteMarkdown(body, articleTitle, sourceRef || null, label);
      const existingId = pane.workingNoteId || pane.savedNoteId;
      const existing = existingId ? await api.article(existingId) : null;
      const article = existing
        ? await api.updateComposedNote(
            existing.id,
            existing.title || titleFromReply(body, label),
            markdown,
            dest,
            payload.isCorrection,
            folderId,
            false,
            true,
          )
        : await api.composeVaultNote(
            titleFromReply(body, label),
            markdown,
            ["grok"],
            dest,
            payload.isCorrection,
            folderId,
          );
      const filedDest = (article.destination as FilingDestination) || dest;
      const filedFolder = article.folder_id ?? folderId;
      saveLastFiling(filedDest, filedFolder);
      patch({ noteDest: filedDest, noteFolderId: filedFolder, savedNoteId: article.id });
      const folderName = folderById(folders, filedFolder)?.name;
      toast.success(
        folderName
          ? `Saved to StoryKeep/${destinationLabel(filedDest, customShelves)}/${folderName}.`
          : `Saved to StoryKeep/${destinationLabel(filedDest, customShelves)}.`,
      );
      await onSavedNote(article.id, filedDest, filedFolder);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not save that note");
    }
  }

  async function applyToWorkingNote(content: string, assistantId?: string) {
    const noteId = pane.workingNoteId;
    if (!noteId) return;
    const index = assistantId ? pane.messages.findIndex((item) => item.id === assistantId) : -1;
    const prior = index > 0 ? pane.messages[index - 1] : null;
    const save = async (confirmShort = false) => {
      try {
        const next = await api.applyJuniorReply(noteId, {
          markdown: content,
          confirm_short: confirmShort,
          mode: prior?.includeMode || pane.includeMode,
          heading: prior?.includeHeading || pane.includeHeading,
          offset: prior?.includeOffset ?? pane.includeOffset,
        });
        patch({ savedNoteId: next.id });
        toast.success("Applied to the note. Previous save is in History.");
        await onSavedNote(next.id, (next.destination as FilingDestination) || pane.noteDest, next.folder_id);
      } catch (error) {
        if (
          !confirmShort &&
          error instanceof ApiError &&
          error.status === 409 &&
          isNoteShrinkMessage(error.message)
        ) {
          if (window.confirm(error.message)) await save(true);
          return;
        }
        toast.error(error instanceof ApiError ? error.message : "Could not apply that reply");
      }
    };
    await save(false);
  }

  async function saveChat() {
    if (savingChat) return;
    if (busy) {
      toast.error("Wait until Junior finishes this reply, then save the chat.");
      return;
    }
    const turns = saveableThreadTurns(pane.messages);
    if (!turns.length) {
      toast.error("Nothing to save — this thread is empty.");
      return;
    }
    const filing = filingFromDropdowns(pane.noteDest, pane.noteFolderId, folders);
    let dest = filing.dest;
    let folderId = filing.folderId;
    if (!dest) {
      toast.error("Pick a shelf before saving this chat.");
      document.getElementById(shelfSelectId)?.focus();
      return;
    }
    if (!folderId) {
      dest = shelfForFinishedChat(pane.displayName, dest);
      const folderName = folderNameForFinishedChat(pane.displayName);
      const existing = matchFolderByName(folders, dest, folderName);
      try {
        const row = existing ?? (await api.createFolder(dest, folderName));
        if (!existing) setFolders((current) => [...current, row]);
        folderId = row.id;
      } catch (error) {
        toastErrorFromUnknown(error, "Could not create a folder for this chat");
        return;
      }
    }
    saveLastFiling(dest, folderId);
    patch({ noteDest: dest, noteFolderId: folderId });
    const title = threadNoteTitle({
      conversationTitle: pane.conversationTitle,
      firstUserLine: turns.find((item) => item.role === "user")?.content,
    });
    const markdown = threadNoteMarkdown(turns, { title, userName: "Steve", assistantName: "Junior" });
    setSavingChat(true);
    try {
      let article: Awaited<ReturnType<typeof api.composeVaultNote>> | null = null;
      let updated = false;
      if (pane.savedNoteId) {
        try {
          article = await api.updateComposedNote(
            pane.savedNoteId,
            title,
            markdown,
            dest,
            false,
            folderId,
          );
          updated = true;
        } catch (error) {
          if (!(error instanceof ApiError && error.status === 404)) {
            throw error;
          }
        }
      }
      if (!article) {
        article = await api.composeVaultNote(title, markdown, ["grok"], dest, false, folderId);
      }
      const filedDest = (article.destination as FilingDestination) || dest;
      const filedFolder = article.folder_id ?? folderId;
      saveLastFiling(filedDest, filedFolder);
      patch({ savedNoteId: article.id, conversationTitle: title, noteDest: filedDest, noteFolderId: filedFolder });
      if (pane.conversationId && persist) {
        try {
          await api.patchChatConversation(pane.conversationId, { saved_note_id: article.id });
        } catch {
          /* note is saved; linking it to the thread is best-effort */
        }
      }
      const folderName = folderById(folders, filedFolder)?.name;
      const where = folderName
        ? `${destinationLabel(filedDest, customShelves)} / ${folderName}`
        : destinationLabel(filedDest, customShelves);
      toast.success(updated ? `Updated “${title}” on ${where}.` : `Saved “${title}” to ${where}.`);
      await onSavedNote(article.id, filedDest, filedFolder);
    } catch (error) {
      toastErrorFromUnknown(error, "Could not save this chat");
    } finally {
      setSavingChat(false);
    }
  }

  return { addToNotes, applyToWorkingNote, saveChat };
}
