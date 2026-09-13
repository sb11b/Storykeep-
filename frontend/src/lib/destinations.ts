export const NOTE_DESTINATIONS = ["vault", "additions", "books", "notes", "schoolwork"] as const;

export type NoteDestination = (typeof NOTE_DESTINATIONS)[number];

export const DESTINATION_LABEL: Record<NoteDestination, string> = {
  vault: "Vault",
  additions: "Additions",
  books: "Books",
  notes: "Notes",
  schoolwork: "Schoolwork",
};

export function asDestination(value: string | null | undefined, fallback: NoteDestination = "additions"): NoteDestination {
  return NOTE_DESTINATIONS.includes(value as NoteDestination) ? (value as NoteDestination) : fallback;
}

const CUSTOM_SHELF_ID = /^[a-z0-9][a-z0-9_-]{0,15}$/;

/** Keep custom shelves such as Junior. asDestination() would coerce them to Additions. */
export function asFilingDestination(value: string | null | undefined, fallback: string = "additions"): string {
  const raw = (value || "").trim().toLowerCase();
  if (!raw) return fallback;
  if (NOTE_DESTINATIONS.includes(raw as NoteDestination)) return raw;
  if (CUSTOM_SHELF_ID.test(raw)) return raw;
  return fallback;
}
