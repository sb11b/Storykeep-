import assert from "node:assert/strict";
import test from "node:test";
import { fileAttachments, parseNoteAttachments, removeAttachmentFromMarkdown } from "./note-attachments";

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

test("media links parse whether the URL is relative or carries an origin", () => {
  const id = "22222222-2222-4222-8222-222222222222";
  const origin = "https://storykeep-production.up.railway.app";

  const relative = parseNoteAttachments(`![shot.png](/api/v1/media/${id})`);
  assert.equal(relative.length, 1);
  assert.equal(relative[0]?.url, `/api/v1/media/${id}`);

  // Packaged builds write absolute media URLs into note markdown.
  const absolute = parseNoteAttachments(`![shot.png](${origin}/api/v1/media/${id})`);
  assert.equal(absolute.length, 1);
  assert.equal(absolute[0]?.url, `${origin}/api/v1/media/${id}`);
  assert.equal(absolute[0]?.id, id);

  // An unrelated image URL is still ignored.
  assert.equal(parseNoteAttachments("![x](https://cdn.example/a.png)").length, 0);
});

test("removeAttachmentFromMarkdown strips both relative and absolute media links", () => {
  const id = "33333333-3333-4333-8333-333333333333";
  const origin = "https://storykeep-production.up.railway.app";
  assert.equal(
    removeAttachmentFromMarkdown(`notes\n\n![a.png](/api/v1/media/${id})\n\nmore`, id),
    "notes\n\nmore",
  );
  assert.equal(
    removeAttachmentFromMarkdown(`notes\n\n![a.png](${origin}/api/v1/media/${id})\n\nmore`, id),
    "notes\n\nmore",
  );
});
