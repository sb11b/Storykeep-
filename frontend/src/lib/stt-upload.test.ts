import assert from "node:assert/strict";
import test from "node:test";
import { formatSttBlobHint, sttUploadFilename } from "./stt-upload";

test("sttUploadFilename uses audio.* names", () => {
  assert.equal(sttUploadFilename("audio/webm;codecs=opus"), "audio.webm");
  assert.equal(sttUploadFilename("audio/mp4"), "audio.mp4");
  assert.equal(sttUploadFilename("audio/ogg"), "audio.ogg");
  assert.equal(sttUploadFilename("audio/wav"), "audio.wav");
});

test("formatSttBlobHint shows mime and size", () => {
  const blob = new Blob([new Uint8Array(12_000)], { type: "audio/webm" });
  assert.equal(formatSttBlobHint(blob), "webm 12kb");
});
