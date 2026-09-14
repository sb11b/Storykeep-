import assert from "node:assert/strict";
import test from "node:test";
import { autoRouteLabel, grokModelLabel, spendChipLabel } from "./grok-model";

test("grokModelLabel shows resolved model and reasoning for Auto", () => {
  assert.equal(grokModelLabel("auto", "grok-4.6", "low"), "Auto → 4.6 · low");
  assert.equal(grokModelLabel("auto", "grok-4.6"), "Auto → 4.6");
  assert.equal(grokModelLabel("auto"), "Auto");
  assert.equal(grokModelLabel("grok-4.6", null, "high"), "grok-4.6 · high");
  assert.equal(grokModelLabel("grok-4.6"), "grok-4.6");
});

test("autoRouteLabel is the reply badge", () => {
  assert.equal(autoRouteLabel("auto", "grok-4.6", "low"), "Auto → 4.6 · low");
  assert.equal(autoRouteLabel("auto", "grok-4.6", "xhigh"), "Auto → 4.6 · xhigh");
  assert.equal(autoRouteLabel("grok-4.6", "grok-4.6", "low"), null);
});

test("spendChipLabel is the POSTed model · reasoning", () => {
  assert.equal(spendChipLabel("grok-4.6", "low"), "4.6 · low");
  assert.equal(spendChipLabel("grok-4.6", "xhigh"), "4.6 · xhigh");
  assert.equal(spendChipLabel(null, null), "4.6 · low");
});
