import assert from "node:assert/strict";
import test from "node:test";
import {
  isNoteShrinkMessage,
  parseErrorPayload,
  restoreCharsConfirm,
  shrinkConfirmMessage,
} from "@/lib/api-errors";

test("parseErrorPayload reads nested FastAPI detail.message", () => {
  const message = shrinkConfirmMessage(15000, 239);
  assert.equal(
    parseErrorPayload({
      detail: { code: "note_shrink", message, current_chars: 15000, incoming_chars: 239 },
    }),
    message,
  );
});

test("shrink confirm copy matches the composer prompt", () => {
  assert.equal(shrinkConfirmMessage(15000, 239), "This save is much shorter (239 vs 15000). Save anyway?");
  assert.equal(restoreCharsConfirm(15000), "Restore 15000 characters?");
  assert.equal(isNoteShrinkMessage("This save is much shorter (239 vs 15000). Save anyway?"), true);
});
