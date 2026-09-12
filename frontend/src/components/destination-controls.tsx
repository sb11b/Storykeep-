"use client";

import { DESTINATION_LABEL, NOTE_DESTINATIONS, type NoteDestination } from "@/lib/destinations";
import { foldersForShelf } from "@/lib/folders";
import type { Folder } from "@/lib/types";
import { cn } from "@/lib/utils";

export function DestinationSelect({
  value,
  onChange,
  id,
  className,
}: {
  value: NoteDestination;
  onChange: (next: NoteDestination) => void;
  id?: string;
  className?: string;
}) {
  return (
    <select
      id={id}
      aria-label="Note destination"
      value={value}
      onChange={(event) => onChange(event.target.value as NoteDestination)}
      className={cn(
        "h-7 rounded-md border border-input bg-background px-2 text-[0.8rem] outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
        className,
      )}
    >
      {NOTE_DESTINATIONS.map((item) => (
        <option key={item} value={item}>
          {DESTINATION_LABEL[item]}
        </option>
      ))}
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
}: {
  shelf: NoteDestination;
  folders: Folder[];
  value: string | null;
  onChange: (next: string | null) => void;
  onCreateFolder: () => void;
  id?: string;
  className?: string;
}) {
  const options = foldersForShelf(folders, shelf);
  return (
    <select
      id={id}
      aria-label="Folder"
      value={value ?? ""}
      onChange={(event) => {
        const next = event.target.value;
        if (next === "__new__") {
          onCreateFolder();
          return;
        }
        onChange(next || null);
      }}
      className={cn(
        "h-7 rounded-md border border-input bg-background px-2 text-[0.8rem] outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
        className,
      )}
    >
      <option value="">No folder</option>
      {options.map((folder) => (
        <option key={folder.id} value={folder.id}>
          {folder.name}
        </option>
      ))}
      <option value="__new__">New folder…</option>
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
