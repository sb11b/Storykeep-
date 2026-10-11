import assert from "node:assert/strict";
import test from "node:test";
import { showDictationMic } from "@/lib/composer-dictation";

const BASE = {
  dictationAvailable: true,
  locked: false,
  conversationStatus: "idle" as const,
  busy: false,
  aborting: false,
};

test("the dictation mic shows in an idle composer with the provider mounted", () => {
  assert.equal(showDictationMic(BASE), true);
});

test("the dictation mic is hidden while Talk is active (every non-idle status)", () => {
  // Dictation and Talk both own the mic — the button must not render during a
  // live conversation, which is exactly the flicker/conflict this avoids.
  for (const conversationStatus of ["connecting", "listening", "speaking", "thinking"] as const) {
    assert.equal(
      showDictationMic({ ...BASE, conversationStatus }),
      false,
      `mic must be hidden while Talk is ${conversationStatus}`,
    );
  }
});

test("the dictation mic is hidden while generating or aborting, and on locked accounts", () => {
  assert.equal(showDictationMic({ ...BASE, busy: true }), false);
  assert.equal(showDictationMic({ ...BASE, aborting: true }), false);
  assert.equal(showDictationMic({ ...BASE, locked: true }), false);
});

test("without the DictationProvider there is no mic to render", () => {
  assert.equal(showDictationMic({ ...BASE, dictationAvailable: false }), false);
});
