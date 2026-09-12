import assert from "node:assert/strict";
import test from "node:test";
import { foldersForShelf, isFolderShelf, matchFolderByName, shelfFolderId } from "./folders";
import type { Folder } from "./types";

const sample: Folder[] = [
  { id: "a", shelf: "schoolwork", name: "DAT-325", item_count: 2, created_at: "2026-01-01T00:00:00Z" },
  { id: "b", shelf: "notes", name: "Ideas", item_count: 1, created_at: "2026-01-01T00:00:00Z" },
];

test("foldersForShelf returns only matching rows", () => {
  assert.equal(foldersForShelf(sample, "schoolwork").length, 1);
  assert.equal(foldersForShelf(sample, "schoolwork")[0]?.name, "DAT-325");
});

test("matchFolderByName finds same-named folder on another shelf", () => {
  const rows: Folder[] = [
    ...sample,
    { id: "c", shelf: "vault", name: "DAT-325", item_count: 0, created_at: "2026-01-01T00:00:00Z" },
  ];
  assert.equal(matchFolderByName(rows, "vault", "DAT-325")?.id, "c");
});

test("shelfFolderId reads optional folderId", () => {
  assert.equal(shelfFolderId({ kind: "schoolwork", folderId: "a" }), "a");
  assert.equal(shelfFolderId({ kind: "schoolwork" }), undefined);
  assert.equal(isFolderShelf({ kind: "schoolwork" }), true);
  assert.equal(isFolderShelf({ kind: "unread" }), false);
});
