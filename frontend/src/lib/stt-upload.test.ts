import assert from "node:assert/strict";
import test from "node:test";
import { formatSttBlobHint, formatSttEmptyHint, prepareSttUpload, sttUploadFilename } from "./stt-upload";

test("sttUploadFilename uses audio.* names", () => {
  assert.equal(sttUploadFilename("audio/webm;codecs=opus"), "audio.webm");
  assert.equal(sttUploadFilename("audio/mp4"), "audio.mp4");
  assert.equal(sttUploadFilename("audio/wav"), "audio.wav");
});

test("prepareSttUpload passes native blob without transcoding", async () => {
  const blob = new Blob([new Uint8Array(1024)], { type: "audio/webm;codecs=opus" });
  const prepared = prepareSttUpload(blob);
  assert.equal(prepared.blob, blob);
  assert.equal(prepared.filename, "audio.webm");
  assert.equal(prepared.mime, "audio/webm");
});

test("formatSttBlobHint shows mime and size", () => {
  const blob = new Blob([new Uint8Array(12_000)], { type: "audio/webm" });
  assert.equal(formatSttBlobHint(blob), "webm 12kb");
});

test("formatSttEmptyHint prefers server mime and bytes", () => {
  assert.equal(formatSttEmptyHint({ mime: "audio/webm", bytes: 28_000 }), "STT empty (webm 27kb)");
});
