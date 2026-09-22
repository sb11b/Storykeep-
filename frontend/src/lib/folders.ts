import { isBuiltInDestination, type FilingDestination } from "@/lib/custom-note-shelves";
import type { Folder, FolderShelfKind, Shelf } from "@/lib/types";
import type { NoteDestination } from "@/lib/destinations";

export const FOLDER_SHELF_KINDS: FolderShelfKind[] = ["vault", "additions", "books", "notes", "schoolwork"];

export function isFolderShelf(
  shelf: Shelf,
): shelf is Extract<Shelf, { kind: FolderShelfKind | "custom" }> {
  return shelf.kind === "custom" || FOLDER_SHELF_KINDS.includes(shelf.kind as FolderShelfKind);
}

export function foldersForShelf(folders: Folder[], shelf: FilingDestination): Folder[] {
  return folders
    .filter((row) => row.shelf === shelf)
    .sort((a, b) => Number(Boolean(b.pinned)) - Number(Boolean(a.pinned)) || a.name.localeCompare(b.name));
}

export function folderValueOnShelf(
  folders: Folder[],
  shelf: FilingDestination,
  folderId: string | null | undefined,
): string {
  const selected = folderById(folders, folderId);
  if (!selected) return "";
  if (selected.shelf === shelf) return selected.id;
  return matchFolderByName(folders, shelf, selected.name)?.id ?? "";
}

export function folderById(folders: Folder[], id: string | null | undefined): Folder | undefined {
  if (!id) return undefined;
  return folders.find((row) => row.id === id);
}

export function matchFolderByName(
  folders: Folder[],
  shelf: FilingDestination,
  name: string | undefined,
): Folder | undefined {
  if (!name) return undefined;
  return folders.find((row) => row.shelf === shelf && row.name === name);
}

export function shelfFolderId(shelf: Shelf): string | undefined {
  return isFolderShelf(shelf) ? shelf.folderId : undefined;
}

export function shelfDestinationId(shelf: Shelf): FilingDestination | null {
  if (shelf.kind === "custom") return shelf.id;
  if (FOLDER_SHELF_KINDS.includes(shelf.kind as FolderShelfKind)) return shelf.kind;
  return null;
}

export function shelfFromFilingDestination(dest: FilingDestination, folderId?: string | null): Shelf {
  if (isBuiltInDestination(dest)) {
    return folderId ? { kind: dest, folderId } : { kind: dest };
  }
  return folderId ? { kind: "custom", id: dest, folderId } : { kind: "custom", id: dest };
}
