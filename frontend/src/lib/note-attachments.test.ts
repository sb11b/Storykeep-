import assert from "node:assert/strict";
import test from "node:test";
import { fileAttachments } from "./note-attachments";

test("fileAttachments parses many media links for the composer strip", () => {
  const lines = Array.from({ length: 10 }, (_, index) => {
    const id = `11111111-1111-1111-1111-${String(index + 1).padStart(12, "0")}`;
    return `[file${index + 1}.pdf](/api/v1/media/${id})`;
  });
  const items = fileAttachments(lines.join("\n"));
  assert.equal(items.length, 10);
  assert.equal(items[0]?.label, "file1.pdf");
  assert.equal(items[9]?.label, "file10.pdf");
});
