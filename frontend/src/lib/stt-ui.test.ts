import assert from "node:assert/strict";
import test from "node:test";
import { MIC_DENIED_TOAST, MIC_DROPPED_TOAST, MIC_IDLE, MIC_LIVE, micDeniedMessage } from "./stt-ui";

test("mic chrome copy is listening, idle, dropped, denied", () => {
  assert.equal(MIC_LIVE, "Listening…");
  assert.equal(MIC_IDLE, "Mic");
  assert.equal(MIC_DROPPED_TOAST, "Mic dropped — tap to resume.");
  assert.equal(MIC_DENIED_TOAST, "Microphone blocked");
});

test("denied mic copy is Microphone blocked", () => {
  const denied = new DOMException("Permission denied", "NotAllowedError");
  assert.equal(micDeniedMessage(denied), "Microphone blocked");
});
