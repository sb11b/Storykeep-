import assert from "node:assert/strict";
import test from "node:test";
import { grokModelLabel } from "./grok-model";

test("grokModelLabel shows resolved model and reasoning for Auto", () => {
  assert.equal(grokModelLabel("auto", "grok-4.6", "low"), "Auto · grok-4.6 · low");
  assert.equal(grokModelLabel("auto", "grok-4.6"), "Auto · grok-4.6");
  assert.equal(grokModelLabel("auto"), "Auto");
  assert.equal(grokModelLabel("grok-4.6", null, "high"), "grok-4.6 · high");
  assert.equal(grokModelLabel("grok-4.6"), "grok-4.6");
});
