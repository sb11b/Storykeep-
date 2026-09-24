import assert from "node:assert/strict";
import test from "node:test";
import { comparePinned } from "./pin-order";

test("pinned rows stay above unpinned and keep pin-time order", () => {
  const rows = [
    { id: "old", pinned: true, pinned_at: "2026-09-01T00:00:00Z", name: "Zed" },
    { id: "loose", pinned: false, pinned_at: null, name: "Amy" },
    { id: "new", pinned: true, pinned_at: "2026-09-20T00:00:00Z", name: "Hub" },
  ];
  rows.sort((a, b) => comparePinned(a, b, (left, right) => left.name.localeCompare(right.name)));
  assert.deepEqual(
    rows.map((row) => row.id),
    ["new", "old", "loose"],
  );
});
