import assert from "node:assert/strict";
import test from "node:test";
import {
  attachmentMarkdown,
  formatFileSize,
  isAllowedLarryFile,
  rejectLarryFile,
} from "@/lib/larry-attach";

function fakeFile(name: string, size: number): File {
  return { name, size } as File;
}

test("Larry accepts the documented file types and rejects the rest", () => {
  assert.equal(isAllowedLarryFile(fakeFile("syllabus.pdf", 12)), true);
  assert.equal(isAllowedLarryFile(fakeFile("notes.MD", 12)), true);
  assert.equal(isAllowedLarryFile(fakeFile("photo.jpeg", 12)), true);
  assert.equal(isAllowedLarryFile(fakeFile("old.doc", 12)), false);
  assert.equal(rejectLarryFile(fakeFile("huge.pdf", 11 * 1024 * 1024)), "huge.pdf is larger than 10 MB.");
});

test("formatFileSize is readable on chips", () => {
  assert.equal(formatFileSize(900), "900 B");
  assert.equal(formatFileSize(12_400), "12 KB");
  assert.equal(formatFileSize(2_400_000), "2.3 MB");
});

test("attachmentMarkdown copies the same media ids onto a note", () => {
  const markdown = attachmentMarkdown([
    {
      media_id: "11111111-1111-1111-1111-111111111111",
      filename: "lab.pdf",
      content_type: "application/pdf",
      kind: "file",
      url: "/api/v1/media/11111111-1111-1111-1111-111111111111",
    },
    {
      media_id: "22222222-2222-2222-2222-222222222222",
      filename: "plot.png",
      content_type: "image/png",
      kind: "image",
      url: "/api/v1/media/22222222-2222-2222-2222-222222222222",
    },
  ]);
  assert.match(markdown, /\[lab\.pdf\]\(\/api\/v1\/media\/11111111-1111-1111-1111-111111111111\)/);
  assert.match(markdown, /!\[plot\]\(\/api\/v1\/media\/22222222-2222-2222-2222-222222222222\)/);
});
