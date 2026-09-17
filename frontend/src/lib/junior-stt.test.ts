import assert from "node:assert/strict";
import test from "node:test";
import {
  clipFilename,
  encodeWavPcm16,
  MIC_RESTART_MAX_MS,
  nextMicRestartDelay,
  pickRecorderMime,
  shouldRestartMic,
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

test("composer mic restarts only while listening and the engine dropped", () => {
  assert.equal(shouldRestartMic(true, "engine"), true);
  assert.equal(shouldRestartMic(true, "user"), false);
  assert.equal(shouldRestartMic(true, "permission"), false);
  assert.equal(shouldRestartMic(false, "engine"), false);
});

test("mic restart backoffs on error and tight onend loops, not on a quiet restart", () => {
  assert.equal(
    nextMicRestartDelay({ fromError: false, prevDelayMs: 0, elapsedSinceRestartMs: 5_000 }),
    0,
  );
  assert.equal(
    nextMicRestartDelay({ fromError: true, prevDelayMs: 0, elapsedSinceRestartMs: 5_000 }),
    400,
  );
  assert.equal(
    nextMicRestartDelay({ fromError: false, prevDelayMs: 0, elapsedSinceRestartMs: 50 }),
    400,
  );
  assert.equal(
    nextMicRestartDelay({ fromError: true, prevDelayMs: 4_000, elapsedSinceRestartMs: 10 }),
    8_000,
  );
  assert.equal(
    nextMicRestartDelay({ fromError: true, prevDelayMs: 8_000, elapsedSinceRestartMs: 10 }),
    MIC_RESTART_MAX_MS,
  );
});
