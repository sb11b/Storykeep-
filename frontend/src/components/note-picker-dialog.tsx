"use client";

import { Input } from "@/components/ui/input";
import type { NoteChoice } from "@/lib/useNotePicker";

export function NotePickerDialog({
  open,
  query,
  choices,
  loading,
  onQueryChange,
  onSelect,
  onClose,
}: {
  open: boolean;
  query: string;
  choices: NoteChoice[];
  loading: boolean;
  onQueryChange: (value: string) => void;
  onSelect: (noteId: string, noteTitle: string) => void;
  onClose: () => void;
}) {
  if (!open) return null;

  return (
    <div className="rounded-md border bg-background p-1.5">
      <Input
        value={query}
        onChange={(event) => onQueryChange(event.target.value)}
        placeholder="Search notes…"
        className="h-7 text-[12px]"
        aria-label="Search notes to include"
      />
      <ul className="mt-1 max-h-32 overflow-y-auto">
        {loading ? (
          <li className="px-1 py-1 text-[11px] text-muted-foreground">Loading…</li>
        ) : choices.length ? (
          choices.map((note) => (
            <li key={note.id}>
              <button
                type="button"
                className="w-full truncate rounded px-1 py-0.5 text-left text-[12px] hover:bg-muted"
                onClick={() => onSelect(note.id, note.title)}
              >
                {note.title}
              </button>
            </li>
          ))
        ) : (
          <li className="px-1 py-1 text-[11px] text-muted-foreground">No notes match.</li>
        )}
      </ul>
    </div>
  );
}
