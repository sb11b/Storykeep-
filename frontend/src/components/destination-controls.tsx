"use client";

import { DESTINATION_LABEL, NOTE_DESTINATIONS, type NoteDestination } from "@/lib/destinations";
import type { CustomNoteShelf, FilingDestination } from "@/lib/custom-note-shelves";
import { foldersForShelf, folderValueOnShelf } from "@/lib/folders";
import type { Folder, RssShelf } from "@/lib/types";
import { cn } from "@/lib/utils";

const NEW_SHELF = "__new_shelf__";

export function DestinationSelect({
  value,
  onChange,
  customShelves = [],
  onCreateShelf,
  id,
  className,
  allowEmpty = false,
  emptyLabel = "Not filed",
}: {
  value: FilingDestination | "";
  onChange: (next: FilingDestination | "") => void;
  customShelves?: CustomNoteShelf[];
  onCreateShelf?: () => void | Promise<void>;
  id?: string;
  className?: string;
  allowEmpty?: boolean;
  emptyLabel?: string;
}) {
  return (
    <select
      id={id}
      aria-label="Shelf"
      value={value}
      onChange={(event) => {
        const next = event.target.value;
        if (next === NEW_SHELF) {
          void onCreateShelf?.();
          return;
        }
        onChange(next ? next : "");
      }}
      className={cn(
        "h-7 rounded-md border border-input bg-background px-2 text-[0.8rem] outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
        className,
      )}
    >
      {allowEmpty ? <option value="">{emptyLabel}</option> : null}
      {NOTE_DESTINATIONS.map((item) => (
        <option key={item} value={item}>
          {DESTINATION_LABEL[item]}
        </option>
      ))}
      {customShelves.map((item) => (
        <option key={item.id} value={item.id}>
          {item.name}
        </option>
      ))}
      {onCreateShelf ? <option value={NEW_SHELF}>+ New shelf…</option> : null}
    </select>
  );
}

export function RssShelfSelect({
  value,
  onChange,
  shelves,
  onCreateShelf,
  id,
  className,
}: {
  value: string;
  onChange: (next: string) => void;
  shelves: RssShelf[];
  onCreateShelf: () => void | Promise<void>;
  id?: string;
  className?: string;
}) {
  return (
    <select
      id={id}
      aria-label="Shelf"
      value={value}
      onChange={(event) => {
        const next = event.target.value;
        if (next === NEW_SHELF) {
          void onCreateShelf();
          return;
        }
        onChange(next);
      }}
      className={cn(
        "h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
        className,
      )}
    >
      {shelves.map((row) => (
        <option key={row.id} value={row.id}>
          {row.name}
        </option>
      ))}
      <option value={NEW_SHELF}>+ New shelf…</option>
    </select>
  );
}

export function FolderSelect({
  shelf,
  folders,
  value,
  onChange,
  onCreateFolder,
  id,
  className,
  disabled = false,
}: {
  shelf: FilingDestination;
  folders: Folder[];
  value: string | null;
  onChange: (next: string | null) => void;
  onCreateFolder: () => void;
  id?: string;
  className?: string;
  disabled?: boolean;
}) {
  const options = foldersForShelf(folders, shelf);
  const valueOnShelf = folderValueOnShelf(folders, shelf, value);
  return (
    <select
      id={id}
      aria-label="Folder"
      disabled={disabled}
      value={valueOnShelf}
      onChange={(event) => {
        const next = event.target.value;
        if (next === "__new__") {
          onCreateFolder();
          return;
        }
        onChange(next || null);
      }}
      className={cn(
        "h-7 rounded-md border border-input bg-background px-2 text-[0.8rem] outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
    >
      <option value="">No folder</option>
      {options.map((folder) => (
        <option key={folder.id} value={folder.id}>
          {folder.name}
        </option>
      ))}
      <option value="__new__">New folder on this shelf…</option>
    </select>
  );
}

export function CorrectionCheck({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <label className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      This is a correction of the source
    </label>
  );
}
