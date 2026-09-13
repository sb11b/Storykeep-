import assert from "node:assert/strict";
import test from "node:test";
import {
  mediaDownloadUrl,
  mediaIdFromUrl,
  storykeepDownloadFilename,
} from "./chat-media-download";

test("download names use storykeep-{id} plus a real extension", () => {
  const id = "7b0b925c-1111-4111-8111-111111111111";
  assert.equal(storykeepDownloadFilename(id, "image/jpeg"), `storykeep-${id}.jpg`);
  assert.equal(storykeepDownloadFilename(id, "image/png"), `storykeep-${id}.png`);
  assert.equal(storykeepDownloadFilename(id, "image/webp"), `storykeep-${id}.webp`);
  assert.notEqual(storykeepDownloadFilename(id, "image/jpeg"), "download");
});

test("media ids come from the stable /media URL", () => {
  const id = "11111111-1111-4111-8111-111111111111";
  assert.equal(mediaIdFromUrl(`/api/v1/media/${id}`), id);
  assert.equal(mediaDownloadUrl(id), `/api/v1/media/${id}`);
});
