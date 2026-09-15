import assert from "node:assert/strict";
import test from "node:test";
import { headingFromInstruction } from "@/lib/work-in-junior";
import { WORKING_NOTE_CHAR_CAP, resolveIncludeSlice } from "@/lib/include-chunk";

test("tighten section 2 maps to the second heading", () => {
  const body = "# Lab\n\n## Intro\n\nhi\n\n## Methods\n\nlong\n\n## Results\n\nok\n";
  assert.equal(headingFromInstruction("tighten section 2", body), "Methods");
});

test("working note cap slices instead of pasting the whole note", () => {
  const body = "# Book\n\n" + "chapter text ".repeat(20_000);
  assert.ok(body.length > WORKING_NOTE_CHAR_CAP);
  const slice = resolveIncludeSlice({
    body,
    mode: "chunk",
    title: "Book",
    cap: WORKING_NOTE_CHAR_CAP,
    hardMax: WORKING_NOTE_CHAR_CAP,
  });
  assert.ok(slice.chars <= WORKING_NOTE_CHAR_CAP);
  assert.equal(slice.hasMore, true);
});
