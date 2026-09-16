import assert from "node:assert/strict";
import test from "node:test";
import { MIC_DENIED_TOAST, MIC_DROPPED_TOAST, MIC_IDLE, MIC_LIVE } from "./stt-ui";

test("mic chrome copy is live, idle, dropped, denied", () => {
  assert.equal(MIC_LIVE, "Mic live");
  assert.equal(MIC_IDLE, "Mic idle");
  assert.equal(MIC_DROPPED_TOAST, "Mic dropped — tap to resume.");
  assert.equal(MIC_DENIED_TOAST, "Microphone blocked");
});
