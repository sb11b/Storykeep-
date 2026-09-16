import assert from "node:assert/strict";
import test from "node:test";
import {
  clipFilename,
  encodeWavPcm16,
  pickRecorderMime,
  sttFailToast,
} from "./junior-stt";

test("pickRecorderMime prefers webm then wav", () => {
  assert.equal(
    pickRecorderMime((type) => type === "audio/webm" || type === "audio/wav"),
    "audio/webm",
  );
  assert.equal(pickRecorderMime((type) => type === "audio/wav"), "audio/wav");
  assert.equal(pickRecorderMime(() => false), "");
});

test("clipFilename matches content type", () => {
  assert.equal(clipFilename("audio/webm;codecs=opus"), "clip.webm");
  assert.equal(clipFilename("audio/wav"), "clip.wav");
  assert.equal(clipFilename("audio/ogg;codecs=opus"), "clip.ogg");
});

test("sttFailToast always includes a status", () => {
  assert.equal(sttFailToast(401, "Not authenticated"), "STT failed (401)");
  assert.equal(sttFailToast(400, "empty blob"), "STT failed (empty blob)");
  assert.equal(sttFailToast(422, "STT failed (422)"), "STT failed (422)");
});

test("encodeWavPcm16 writes a RIFF header", () => {
  const pcm = new ArrayBuffer(320);
  const blob = encodeWavPcm16(pcm, 16000);
  assert.equal(blob.type, "audio/wav");
  assert.equal(blob.size, 44 + 320);
});
