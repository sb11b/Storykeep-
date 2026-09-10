import assert from "node:assert/strict";
import test from "node:test";
import { EXTRACT_MESSAGES, extractFailureMessage } from "./extract-toast";
import { nonEmptyMessage } from "./toast-message";

test("extractFailureMessage never returns empty text", () => {
  assert.equal(extractFailureMessage(""), EXTRACT_MESSAGES.failed);
  assert.equal(extractFailureMessage("   "), EXTRACT_MESSAGES.failed);
  assert.equal(extractFailureMessage(undefined), EXTRACT_MESSAGES.failed);
  assert.equal(extractFailureMessage("Site blocked the fetch."), "Site blocked the fetch.");
});

test("nonEmptyMessage guards blank API errors for extract toasts", () => {
  assert.ok(nonEmptyMessage("", EXTRACT_MESSAGES.failed).length > 0);
  assert.ok(nonEmptyMessage(undefined, EXTRACT_MESSAGES.failed).length > 0);
});
