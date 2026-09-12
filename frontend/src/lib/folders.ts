import type { Folder, FolderShelfKind, Shelf } from "@/lib/types";
import type { NoteDestination } from "@/lib/destinations";

export const FOLDER_SHELF_KINDS: FolderShelfKind[] = ["vault", "additions", "books", "notes", "schoolwork"];

export function isFolderShelf(shelf: Shelf): shelf is Extract<Shelf, { kind: FolderShelfKind }> {
  return FOLDER_SHELF_KINDS.includes(shelf.kind as FolderShelfKind);
}

export function foldersForShelf(folders: Folder[], shelf: NoteDestination): Folder[] {
  return folders.filter((row) => row.shelf === shelf);
}

export function folderById(folders: Folder[], id: string | null | undefined): Folder | undefined {
  if (!id) return undefined;
  return folders.find((row) => row.id === id);
}

export function matchFolderByName(folders: Folder[], shelf: NoteDestination, name: string | undefined): Folder | undefined {
  if (!name) return undefined;
  return folders.find((row) => row.shelf === shelf && row.name === name);
}

export function shelfFolderId(shelf: Shelf): string | undefined {
  return isFolderShelf(shelf) ? shelf.folderId : undefined;
}
