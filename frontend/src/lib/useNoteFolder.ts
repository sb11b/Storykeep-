"use client";

import { toast } from "sonner";
import { ApiError, api } from "@/lib/api";
import type { Folder } from "@/lib/types";

type Shelf = { id: string; name: string };

type UseNoteFolderOptions = {
  pane: { noteDest: string };
  customShelves: Shelf[];
  destinationLabel: (value: string, customShelves: Shelf[], fallback?: string) => string;
  setFolders: (update: Folder[] | ((current: Folder[]) => Folder[])) => void;
  patch: (partial: { noteDest?: string; noteFolderId?: string | null }) => void;
  saveLastFiling: (dest: string, folderId: string | null) => void;
};

export function useNoteFolder({
  pane,
  customShelves,
  destinationLabel,
  setFolders,
  patch,
  saveLastFiling,
}: UseNoteFolderOptions) {
  async function createNoteFolder(shelf: string = pane.noteDest) {
    const name = window.prompt(`New folder on ${destinationLabel(shelf, customShelves)}`);
    if (!name?.trim()) return;
    try {
      const row = await api.createFolder(shelf, name.trim());
      setFolders((current) => [...current, row]);
      patch({ noteDest: shelf, noteFolderId: row.id });
      saveLastFiling(shelf, row.id);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not create folder");
    }
  }

  function handleNoteDestChange(next: string) {
    if (!next) return;
    patch({ noteDest: next, noteFolderId: null });
    saveLastFiling(next, null);
  }

  return { createNoteFolder, handleNoteDestChange };
}
