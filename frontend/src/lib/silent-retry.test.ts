import assert from "node:assert/strict";
import test from "node:test";

import { EMPTY_REPLY_BODY } from "./grok-pane-name.ts";
import { restoreDraftAfterSilent } from "./silent-retry.ts";

test("silent fallback puts the sent line back when the box is empty", () => {
  assert.equal(
    restoreDraftAfterSilent("", "explain the DAT homework", EMPTY_REPLY_BODY),
    "explain the DAT homework",
  );
});

test("a real reply leaves an empty box empty", () => {
  assert.equal(restoreDraftAfterSilent("", "explain lists", "A list keeps order."), "");
});

test("text already in the box stays", () => {
  assert.equal(restoreDraftAfterSilent("next question", "explain lists", EMPTY_REPLY_BODY), "next question");
});
