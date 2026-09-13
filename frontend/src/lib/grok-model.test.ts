import assert from "node:assert/strict";
import test from "node:test";
import { grokModelLabel } from "./grok-model";

test("grokModelLabel shows resolved model for Auto", () => {
  assert.equal(grokModelLabel("auto", "grok-4-fast"), "Auto · grok-4-fast");
  assert.equal(grokModelLabel("auto"), "Auto");
  assert.equal(grokModelLabel("grok-4"), "grok-4");
});
