import assert from "node:assert/strict";
import test from "node:test";
import {
  AUTO_LOW_MAX_CHARS,
  autoPostedSpend,
  autoReasoningEffort,
  pickXhighForAuto,
  postedSpendForTurn,
} from "./grok-auto-route";
import { spendChipLabel } from "./grok-model";

test("hello and how was your morning POST 4.6 · low", () => {
  assert.equal(autoReasoningEffort("hello"), "low");
  assert.equal(autoReasoningEffort("how was your morning"), "low");
  assert.equal(pickXhighForAuto("how was your morning"), false);
  const posted = autoPostedSpend("how was your morning");
  assert.equal(spendChipLabel(posted.model, posted.reasoning), "4.6 · low");
});

test("hello never POSTs xhigh even if the dropdown says xhigh", () => {
  const posted = postedSpendForTurn("grok-4.6", "xhigh", "hello");
  assert.equal(spendChipLabel(posted.model, posted.reasoning), "4.6 · low");
});

test("short paste and small talk stay low", () => {
  assert.equal(autoReasoningEffort("please analyze this"), "low");
  assert.equal(autoReasoningEffort("take your time"), "low");
  const ramble = "Hey, just checking in. ".repeat(40);
  assert.ok(ramble.length >= AUTO_LOW_MAX_CHARS);
  assert.equal(autoReasoningEffort(ramble), "low");
});

test("school, code, and long analyze POST xhigh", () => {
  assert.equal(autoReasoningEffort("help with this python homework"), "xhigh");
  assert.equal(
    autoReasoningEffort("Debug this:\n```python\ndef avg(nums):\n    return sum(nums)/len(nums)\n```"),
    "xhigh",
  );
  const longAnalyze = `Please analyze this dataset. ${"notes ".repeat(80)}`;
  assert.ok(longAnalyze.length >= AUTO_LOW_MAX_CHARS);
  assert.equal(autoReasoningEffort(longAnalyze), "xhigh");
  assert.equal(spendChipLabel("grok-4.6", "xhigh"), "4.6 · xhigh");
});
