import assert from "node:assert/strict";
import test from "node:test";
import { parseCustomNoteShelves, slugifyShelfName, uniqueShelfId } from "@/lib/custom-note-shelves";

test("slugifyShelfName handles punctuation", () => {
  assert.equal(slugifyShelfName("Labs"), "labs");
  assert.equal(slugifyShelfName("Larry (the asparagus)"), "larry-the-aspara");
});

test("parseCustomNoteShelves reads preferences", () => {
  const rows = parseCustomNoteShelves({
    custom_note_shelves: [{ id: "labs", name: "Labs" }],
  });
  assert.equal(rows.length, 1);
  assert.equal(rows[0]!.name, "Labs");
});

test("uniqueShelfId avoids collisions", () => {
  assert.equal(uniqueShelfId("Labs", [{ id: "labs", name: "Labs" }]), "labs2");
});
