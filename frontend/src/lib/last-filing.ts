import { asFilingDestination } from "@/lib/destinations";
import { folderValueOnShelf } from "@/lib/folders";
import type { Folder } from "@/lib/types";

export const LAST_FILING_KEY = "storykeep-last-filing";

export type LastFiling = {
  dest: string;
  folderId: string | null;
};

const FOLDER_ID = /^[0-9a-fA-F-]{36}$/;

export function loadLastFiling(fallbackDest = "notes"): LastFiling {
  if (typeof window === "undefined") return { dest: fallbackDest, folderId: null };
  try {
    const raw = window.localStorage.getItem(LAST_FILING_KEY);
    if (!raw) return { dest: fallbackDest, folderId: null };
    const parsed = JSON.parse(raw) as { dest?: string; folderId?: string | null };
    const dest = asFilingDestination(parsed.dest, fallbackDest);
    const folderId =
      typeof parsed.folderId === "string" && FOLDER_ID.test(parsed.folderId) ? parsed.folderId : null;
    return { dest, folderId };
  } catch {
    return { dest: fallbackDest, folderId: null };
  }
}

export function saveLastFiling(dest: string, folderId: string | null): LastFiling {
  const next: LastFiling = {
    dest: asFilingDestination(dest, "notes"),
    folderId: folderId && FOLDER_ID.test(folderId) ? folderId : null,
  };
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(LAST_FILING_KEY, JSON.stringify(next));
    } catch {
      /* ignore */
    }
  }
  return next;
}

/** Shelf + folder from the dropdowns; empty fields fall back to last-used, never Inbox. */
export function filingFromDropdowns(
  dest: string | null | undefined,
  folderId: string | null | undefined,
  folders: Folder[] = [],
  fallbackDest = "notes",
): LastFiling {
  const last = loadLastFiling(fallbackDest);
  const destRaw = (dest || "").trim();
  const shelf = asFilingDestination(destRaw || last.dest, last.dest || fallbackDest);
  const destWasEmpty = !destRaw;
  const folderWasEmpty = folderId === undefined || folderId === "" || (destWasEmpty && folderId == null);
  const rawFolder = folderWasEmpty ? last.folderId : folderId;
  const onShelf = folderValueOnShelf(folders, shelf, rawFolder);
  const resolved = onShelf || (rawFolder && FOLDER_ID.test(rawFolder) ? rawFolder : null);
  return { dest: shelf, folderId: resolved };
}
