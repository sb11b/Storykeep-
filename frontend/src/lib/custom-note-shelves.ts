import { DESTINATION_LABEL, NOTE_DESTINATIONS, type NoteDestination } from "@/lib/destinations";

export type CustomNoteShelf = {
  id: string;
  name: string;
};

export type FilingDestination = NoteDestination | string;

const SLUG_RE = /^[a-z0-9][a-z0-9_-]{0,15}$/;

export function parseCustomNoteShelves(preferences: Record<string, unknown> | undefined): CustomNoteShelf[] {
  const raw = preferences?.custom_note_shelves;
  if (!Array.isArray(raw)) return [];
  const out: CustomNoteShelf[] = [];
  for (const row of raw) {
    if (!row || typeof row !== "object") continue;
    const id = String((row as { id?: string }).id || "")
      .trim()
      .toLowerCase();
    const name = String((row as { name?: string }).name || "").trim();
    if (SLUG_RE.test(id) && name) out.push({ id, name });
  }
  return out;
}

export function slugifyShelfName(name: string): string {
  const base = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 16);
  return base || "shelf";
}

export function isBuiltInDestination(value: string): value is NoteDestination {
  return NOTE_DESTINATIONS.includes(value as NoteDestination);
}

export function isCustomDestination(value: string, customShelves: CustomNoteShelf[]): boolean {
  return customShelves.some((row) => row.id === value);
}

export function destinationLabel(
  value: FilingDestination,
  customShelves: CustomNoteShelf[],
  fallback = "Shelf",
): string {
  if (isBuiltInDestination(value)) return DESTINATION_LABEL[value];
  return customShelves.find((row) => row.id === value)?.name || fallback;
}

export function uniqueShelfId(name: string, customShelves: CustomNoteShelf[]): string {
  const base = slugifyShelfName(name);
  if (!customShelves.some((row) => row.id === base) && !isBuiltInDestination(base)) return base;
  for (let index = 2; index < 100; index += 1) {
    const candidate = `${base.slice(0, Math.max(1, 16 - String(index).length))}${index}`;
    if (!customShelves.some((row) => row.id === candidate) && !isBuiltInDestination(candidate)) {
      return candidate;
    }
  }
  return `${base.slice(0, 12)}-${Date.now().toString(36).slice(-3)}`;
}
