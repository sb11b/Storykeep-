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
