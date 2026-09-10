import assert from "node:assert/strict";
import test from "node:test";
import { initialListDebug, listRangeLabel } from "./list-range";

test("listRangeLabel shows Showing 1–N on first page", () => {
  assert.equal(listRangeLabel(12, 48, "unread"), "Showing 1–12 of 48");
  assert.equal(listRangeLabel(40, 120, "schoolwork"), "Showing 1–40 of 120");
});

test("listRangeLabel handles empty and zero-loaded shelves", () => {
  assert.equal(listRangeLabel(0, 0, "notes"), "No notes");
  assert.equal(listRangeLabel(0, 5, "inbox"), "5 articles");
});

test("initialListDebug resets shelf list to offset zero", () => {
  assert.deepEqual(initialListDebug, { offset: 0, startIndex: 0, count: 0 });
});
