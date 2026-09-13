import assert from "node:assert/strict";
import test from "node:test";
import {
  attachmentMarkdown,
  formatFileSize,
  isAllowedLarryFile,
  rejectLarryFile,
  snapshotFiles,
  uploadLarryAttachment,
} from "@/lib/larry-attach";
import { ApiError } from "@/lib/api";

function fakeFile(name: string, size: number): File {
  return { name, size } as File;
}

test("Larry accepts the documented file types and rejects the rest", () => {
  assert.equal(isAllowedLarryFile(fakeFile("syllabus.pdf", 12)), true);
  assert.equal(isAllowedLarryFile(fakeFile("notes.MD", 12)), true);
  assert.equal(isAllowedLarryFile(fakeFile("photo.jpeg", 12)), true);
  assert.equal(isAllowedLarryFile(fakeFile("shot.webp", 12)), true);
  assert.equal(isAllowedLarryFile(fakeFile("old.doc", 12)), false);
  assert.equal(rejectLarryFile(fakeFile("huge.pdf", 11 * 1024 * 1024)), "huge.pdf is larger than 10 MB.");
});

test("formatFileSize is readable on chips", () => {
  assert.equal(formatFileSize(900), "900 B");
  assert.equal(formatFileSize(12_400), "12 KB");
  assert.equal(formatFileSize(2_400_000), "2.3 MB");
});

test("snapshotFiles copies File objects before a live list is emptied", () => {
  const store: File[] = [fakeFile("notes.txt", 12)];
  const list = {
    get length() {
      return store.length;
    },
    item(index: number) {
      return store[index] ?? null;
    },
    *[Symbol.iterator]() {
      yield* store;
    },
  };
  const copied = snapshotFiles(list as unknown as FileList);
  store.splice(0, store.length);
  assert.equal(copied.length, 1);
  assert.equal(copied[0]!.name, "notes.txt");
});

test("uploadLarryAttachment posts FormData and returns {id, name, size}", async () => {
  const previous = globalThis.fetch;
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    return {
      ok: true,
      status: 201,
      json: async () => ({
        id: "media-1",
        filename: "notes.txt",
        url: "/api/v1/media/media-1",
        kind: "file",
        byte_size: 12,
      }),
    } as unknown as Response;
  }) as typeof fetch;
  try {
    const result = await uploadLarryAttachment(fakeFile("notes.txt", 12) as File);
    assert.equal(calls[0]?.url, "/api/v1/media");
    assert.equal(calls[0]?.init?.method, "POST");
    assert.equal(calls[0]?.init?.credentials, "include");
    assert.ok(calls[0]?.init?.body instanceof FormData);
    assert.deepEqual(
      { id: result.id, name: result.name, size: result.size },
      { id: "media-1", name: "notes.txt", size: 12 },
    );
  } finally {
    globalThis.fetch = previous;
  }
});

test("uploadLarryAttachment throws an ApiError with the HTTP status on failure", async () => {
  const previous = globalThis.fetch;
  globalThis.fetch = (async () =>
    ({
      ok: false,
      status: 413,
      json: async () => ({ detail: "Attachments must be 10 MB or smaller." }),
    }) as unknown as Response) as typeof fetch;
  try {
    const error = await uploadLarryAttachment(fakeFile("notes.txt", 12) as File).catch((err) => err);
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 413);
    assert.match(error.message, /10 MB/);
  } finally {
    globalThis.fetch = previous;
  }
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
