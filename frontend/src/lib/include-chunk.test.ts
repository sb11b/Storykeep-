import assert from "node:assert/strict";
import test from "node:test";
import {
  INCLUDE_TURN_CHAR_CAP,
  formatIncludeChip,
  parseSections,
  resolveIncludeSlice,
} from "./include-chunk";

const DAT = `# DAT-200 notes

Lead-in paragraph.

## Completeness

Completeness means every fact that belongs on a row is stored on that row.
${"Keep the grade with the enrollment. ".repeat(80)}

## Third normal form

Non-key attributes must depend on the key, the whole key, and nothing but the key.
${"Normalize repeating groups. ".repeat(40)}`;

test("chip shows section sign and char count", () => {
  assert.equal(formatIncludeChip("Completeness", 1842), "§ Completeness (1,842 chars)");
});

test("heading slice is not the whole DAT note", () => {
  const slice = resolveIncludeSlice({ body: DAT, mode: "heading", heading: "Completeness", title: "DAT-200 notes" });
  assert.equal(slice.label, "Completeness");
  assert.match(slice.text, /every fact that belongs/);
  assert.doesNotMatch(slice.text, /nothing but the key/);
  assert.equal(slice.hasMore, true);
  assert.equal(slice.nextHeading, "Third normal form");
  assert.equal(slice.chip, formatIncludeChip("Completeness", slice.chars));
});

test("first chunk then next chunk continues", () => {
  const huge = `# Book\n\n${"chapter text ".repeat(5000)}`;
  const first = resolveIncludeSlice({ body: huge, mode: "chunk", title: "Book" });
  assert.ok(first.chars <= INCLUDE_TURN_CHAR_CAP);
  assert.equal(first.hasMore, true);
  const next = resolveIncludeSlice({ body: huge, mode: "chunk", offset: first.nextOffset || 0, title: "Book" });
  assert.ok(next.text);
  assert.notEqual(next.text.slice(0, 40), first.text.slice(0, 40));
});

test("parses markdown headings", () => {
  assert.deepEqual(
    parseSections(DAT).map((item) => item.title),
    ["DAT-200 notes", "Completeness", "Third normal form"],
  );
});
